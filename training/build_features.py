# Databricks notebook source

# COMMAND ----------

# Standalone feature-build step for the retail-forecast MLOps pipeline.
#
# This notebook reads gold.fact_transactions, gold.fact_promotions, gold.dim_store,
# and gold.dim_product; performs the full weekly aggregation, valid-pairs filtering,
# promo date-overlap feature engineering, and rolling-window features; then writes the
# result to the UC Feature Store table retail_forecast.feature.weekly_demand_features.
#
# KEY DESIGN DECISIONS:
#   1. DATA_END is DYNAMIC — it equals the MAX weekly `week` in the fact_transactions
#      weekly aggregation.  It is NEVER hardcoded.  The scoring notebook
#      (score_forecast.py) computes DATA_END identically so that its forward-dated
#      score keys align exactly with the future feature rows written here.
#   2. The feature table holds FEATURES ONLY — no label / no total_quantity column.
#      The training notebook (train_model.py) recomputes labels independently from
#      gold.fact_transactions, keeping the feature table clean and reusable.

import json
import mlflow
from datetime import date, timedelta
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from databricks.feature_engineering import FeatureEngineeringClient

dbutils.widgets.text("catalog", "retail_forecast")
CATALOG           = dbutils.widgets.get("catalog")
GOLD_SCHEMA       = "gold"
FEATURE_SCHEMA    = "feature"
FEATURE_TABLE     = f"{CATALOG}.{FEATURE_SCHEMA}.weekly_demand_features"
MIN_HISTORY_WEEKS = 12

mlflow.set_registry_uri("databricks-uc")
fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")

# COMMAND ----------

# --- Load tables (stay in Spark until sklearn needs pandas) ---
fact_txn    = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.fact_transactions")
fact_promo  = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.fact_promotions")
dim_store   = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_store").select("store_id", "region")
dim_product = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_product").select("sku", "category")

# COMMAND ----------

# --- Weekly aggregation in Spark ---
weekly = (
    fact_txn
    .withColumn("week", F.date_trunc("WEEK", F.col("date_id")).cast("date"))
    .groupBy("sku", "store_id", "week")
    .agg(F.sum("quantity_sold").alias("total_quantity"))
)

# Dynamic DATA_END: max week observed in fact_transactions — never hardcoded.
# score_forecast.py must compute DATA_END identically for score-key alignment.
DATA_END = weekly.agg(F.max("week")).first()[0]
print(f"DATA_END (max week): {DATA_END}")

# Keep only pairs with enough history
valid_pairs = (
    weekly
    .groupBy("sku", "store_id")
    .agg(F.countDistinct("week").alias("week_count"))
    .filter(F.col("week_count") >= MIN_HISTORY_WEEKS)
    .select("sku", "store_id")
)
weekly = weekly.join(valid_pairs, on=["sku", "store_id"])

# Enrich with region and category for promotion matching
weekly = (
    weekly
    .join(F.broadcast(dim_store), on="store_id")
    .join(F.broadcast(dim_product), on="sku")
)

# COMMAND ----------

# --- Promotion features via Spark date-range join (replaces pandas apply) ---
def add_promo_features(df, promos, group_cols):
    """
    Left-join df with promos on date overlap + store/SKU scope.
    Returns df with is_promoted and discount_pct_feat columns added.
    group_cols must include all columns to preserve through the aggregation.
    """
    week_end = F.date_add(F.col("week"), 6)
    joined = df.join(
        F.broadcast(promos),
        on=(
            (F.col("promo_start_date") <= week_end) &
            (F.col("promo_end_date")   >= F.col("week")) &
            (
                (F.col("target_store_id") == F.col("store_id")) |
                (F.col("target_region")   == F.col("region"))
            ) &
            (
                (F.col("target_sku")      == F.col("sku")) |
                (F.col("target_category") == F.col("category"))
            )
        ),
        how="left",
    )
    return (
        joined
        .groupBy(group_cols)
        .agg(F.max("discount_pct").alias("discount_pct_feat"))
        .withColumn("is_promoted",
                    F.when(F.col("discount_pct_feat").isNotNull(), 1).otherwise(0))
        .withColumn("discount_pct_feat",
                    F.coalesce(F.col("discount_pct_feat"), F.lit(0.0)))
    )

past_promos = fact_promo.filter(~F.col("is_future")).select(
    "target_sku", "target_category", "target_store_id", "target_region",
    "discount_pct", "promo_start_date", "promo_end_date",
)

print("Applying promotion features to training data...")
train_group_cols = ["sku", "store_id", "week", "total_quantity", "region", "category"]
weekly = add_promo_features(weekly, past_promos, train_group_cols)

# COMMAND ----------

# --- Rolling windows and week_of_year in Spark ---
week_window    = Window.partitionBy("sku", "store_id").orderBy("week").rowsBetween(-4, -1)
week_12_window = Window.partitionBy("sku", "store_id").orderBy("week").rowsBetween(-12, -1)
weekly = (
    weekly
    .withColumn("rolling_4wk_avg",
                F.coalesce(F.avg("total_quantity").over(week_window), F.lit(0.0)))
    .withColumn("avg_demand_last_12w",
                F.coalesce(F.avg("total_quantity").over(week_12_window), F.lit(0.0)))
    .withColumn("week_of_year", F.weekofyear("week"))
)

# Feature table rows — features only, no label (total_quantity intentionally excluded).
# The training notebook recomputes labels from gold.fact_transactions.
features_df = weekly.select(
    "sku", "store_id", "week",
    "week_of_year", "is_promoted", "discount_pct_feat",
    "rolling_4wk_avg", "avg_demand_last_12w",
)

# COMMAND ----------

# --- Build forward-dated feature rows for the 8 forecast weeks ---
# These are written to the feature table so fe.score_batch can do point-in-time lookup.
# forecast weeks start from DATA_END + 1 week (dynamic; already Monday-truncated).
forecast_weeks_list = [DATA_END + timedelta(weeks=i) for i in range(1, 9)]
forecast_weeks_list = [w - timedelta(days=w.weekday()) for w in forecast_weeks_list]

forecast_weeks_spark = spark.createDataFrame(
    [(w,) for w in forecast_weeks_list], ["week"]
).withColumn("week", F.col("week").cast("date"))

# Carry rolling averages from the last known week for each (sku, store_id)
last_window = Window.partitionBy("sku", "store_id").orderBy(F.desc("week"))
latest_feat = (
    features_df
    .withColumn("_rn", F.row_number().over(last_window))
    .filter(F.col("_rn") == 1)
    .select("sku", "store_id", "avg_demand_last_12w", "rolling_4wk_avg")
)

future_base = (
    valid_pairs.crossJoin(forecast_weeks_spark)
    .join(latest_feat, on=["sku", "store_id"])
    .join(F.broadcast(dim_store), on="store_id")
    .join(F.broadcast(dim_product), on="sku")
    .withColumn("week_of_year", F.weekofyear("week"))
    .withColumn("total_quantity", F.lit(0))  # placeholder for group_cols parity
)

all_promos = fact_promo.select(
    "target_sku", "target_category", "target_store_id", "target_region",
    "discount_pct", "promo_start_date", "promo_end_date",
)

future_group_cols = [
    "sku", "store_id", "week", "week_of_year",
    "avg_demand_last_12w", "rolling_4wk_avg",
    "region", "category", "total_quantity",
]
future_features_df = (
    add_promo_features(future_base, all_promos, future_group_cols)
    .drop("total_quantity", "region", "category")
    .select(
        "sku", "store_id", "week", "week_of_year",
        "is_promoted", "discount_pct_feat",
        "rolling_4wk_avg", "avg_demand_last_12w",
    )
)

# Union historical + forward-dated rows for a single feature table write
features_all_df = features_df.union(future_features_df)

# COMMAND ----------

# --- Create + write the feature table ---
try:
    fe.create_table(
        name=FEATURE_TABLE,
        primary_keys=["sku", "store_id", "week"],
        timeseries_column="week",          # singular — canonical in >=0.16.0
        schema=features_all_df.schema,
        description="Weekly per-SKU/store demand features (point-in-time)",
    )
except Exception as e:
    if "already exists" not in str(e).lower():
        raise
fe.write_table(name=FEATURE_TABLE, df=features_all_df, mode="merge")
feature_rows = spark.table(FEATURE_TABLE).count()
print("feature rows:", feature_rows)

# COMMAND ----------

dbutils.notebook.exit(json.dumps({
    "feature_rows": feature_rows,
    "data_end": str(DATA_END),
}))
