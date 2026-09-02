# Databricks notebook source

# COMMAND ----------

import json
import mlflow
import mlflow.sklearn
import pandas as pd
from datetime import date, timedelta
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup

dbutils.widgets.text("catalog", "retail_forecast")
CATALOG           = dbutils.widgets.get("catalog")
GOLD_SCHEMA       = "gold"
FEATURE_SCHEMA    = "feature"
MODEL_NAME        = f"{CATALOG}.{GOLD_SCHEMA}.retail_forecast_rf"
FEATURE_TABLE     = f"{CATALOG}.{FEATURE_SCHEMA}.weekly_demand_features"
MIN_HISTORY_WEEKS = 12
FEATURES          = ["week_of_year", "is_promoted", "discount_pct_feat", "rolling_4wk_avg"]
TARGET            = "total_quantity"
DATA_END          = date(2026, 6, 29)

_current_user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_registry_uri("databricks-uc")
mlflow.sklearn.autolog(log_models=False)  # params/metrics auto-logged; model logged manually via fe.log_model

fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")

# COMMAND ----------

# --- Load tables (stay in Spark until sklearn needs pandas) ---
fact_txn    = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.fact_transactions")
fact_promo  = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.fact_promotions")
dim_store   = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_store").select("store_id", "region")
dim_product = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_product").select("sku", "category")

# Full dim tables for forecast_action_list enrichment (store_name, product_name)
dim_store_full   = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_store")
dim_product_full = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_product")

# COMMAND ----------

# --- Weekly aggregation in Spark ---
weekly = (
    fact_txn
    .withColumn("week", F.date_trunc("WEEK", F.col("date_id")).cast("date"))
    .groupBy("sku", "store_id", "week")
    .agg(F.sum("quantity_sold").alias("total_quantity"))
)

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

# Split into feature table rows (no label) and labels (no features)
features_df = weekly.select(
    "sku", "store_id", "week",
    "week_of_year", "is_promoted", "discount_pct_feat",
    "rolling_4wk_avg", "avg_demand_last_12w",
)
labels_df = weekly.select("sku", "store_id", "week", "total_quantity")

# COMMAND ----------

# --- Build forward-dated feature rows for the 8 forecast weeks ---
# These are written to the feature table so fe.score_batch can do point-in-time lookup
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
print("feature rows:", spark.table(FEATURE_TABLE).count())

# COMMAND ----------

# --- Build the point-in-time training set ---
all_weeks = [r.week for r in labels_df.select("week").distinct().orderBy("week").collect()]
cutoff = all_weeks[-8]                       # hold out last 8 weeks
train_labels = labels_df.filter(F.col("week") < cutoff)
test_labels  = labels_df.filter(F.col("week") >= cutoff)

lookups = [FeatureLookup(
    table_name=FEATURE_TABLE,
    lookup_key=["sku", "store_id"],
    timestamp_lookup_key="week",             # point-in-time: feature.week <= label.week
)]
training_set = fe.create_training_set(
    df=train_labels, feature_lookups=lookups,
    label="total_quantity", exclude_columns=["week", "sku", "store_id"],
)
train_pd = training_set.load_df().toPandas()
X_train, y_train = train_pd[FEATURES], train_pd[TARGET]

# COMMAND ----------

# --- Train, compute holdout MAE, and register with fe.log_model ---
mlflow.set_experiment(f"/Users/{_current_user}/retail_forecast_demand")
with mlflow.start_run() as run:
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    test_set = fe.create_training_set(
        df=test_labels, feature_lookups=lookups,
        label="total_quantity", exclude_columns=["week", "sku", "store_id"],
    )
    test_pd = test_set.load_df().toPandas()
    mae = mean_absolute_error(test_pd[TARGET], model.predict(test_pd[FEATURES]))
    mlflow.log_metric("mae_holdout", mae)
    print(f"MAE holdout: {mae:.2f}")

    fe.log_model(
        model=model, artifact_path="model", flavor=mlflow.sklearn,
        training_set=training_set, registered_model_name=MODEL_NAME,
    )

client = MlflowClient(registry_uri="databricks-uc")
latest = max(client.search_model_versions(f"name='{MODEL_NAME}'"), key=lambda v: int(v.version)).version
client.set_registered_model_alias(MODEL_NAME, "prod", latest)
print(f"Registered {MODEL_NAME} v{latest} @prod")

# COMMAND ----------

# --- Score the next 8 weeks with fe.score_batch (keys-only df) ---
score_keys = (
    valid_pairs.crossJoin(forecast_weeks_spark)
    .select("sku", "store_id", "week")
)

scored = fe.score_batch(
    model_uri=f"models:/{MODEL_NAME}@prod",
    df=score_keys,
    result_type="double",   # column: "prediction"
)
scored = (
    scored
    .withColumnRenamed("prediction", "predicted_demand_raw")
    .withColumn("predicted_demand",
                F.greatest(F.lit(0), F.round("predicted_demand_raw")).cast("int"))
)

# Join avg_demand_last_12w from feature table for risk flags
feat = spark.table(FEATURE_TABLE).select("sku", "store_id", "week", "avg_demand_last_12w")
out = (
    scored.join(feat, ["sku", "store_id", "week"])
    .withColumn("is_stockout_risk",
                (F.col("predicted_demand") > F.col("avg_demand_last_12w") * 1.3) &
                (F.col("avg_demand_last_12w") > 0))
    .withColumn("is_overstock_risk",
                (F.col("predicted_demand") < F.col("avg_demand_last_12w") * 0.7) &
                (F.col("avg_demand_last_12w") > 0))
    .withColumn("model_version", F.lit(f"rf_v{latest}"))
    .select("sku", "store_id", "week", "predicted_demand", "avg_demand_last_12w",
            "is_stockout_risk", "is_overstock_risk", "model_version")
)
out.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.gold.forecast_demand"
)
print("forecast_demand rows:", out.count())

# COMMAND ----------

# --- Materialize gold.forecast_action_list (synced-table source) ---
# Implements action_list.sql logic as a persistent gold table keyed by sku, store_id, week.
# Includes all 8 forecast weeks (not capped to a single week) for Task-4 Lakebase sync.
# Column names are Postgres-friendly (A-Za-z0-9_ only).
action_list = (
    out
    .filter(F.col("is_stockout_risk") | F.col("is_overstock_risk"))
    .join(F.broadcast(dim_store_full.select("store_id", "store_name", "region")),
          on="store_id")
    .join(F.broadcast(dim_product_full.select("sku", "product_name", "category")),
          on="sku")
    .withColumn("risk_type",
                F.when(F.col("is_stockout_risk") & F.col("is_overstock_risk"), F.lit("Both"))
                 .when(F.col("is_stockout_risk"), F.lit("Stockout"))
                 .otherwise(F.lit("Overstock")))
    .withColumn("demand_delta",
                F.round(F.col("predicted_demand") - F.col("avg_demand_last_12w"), 0).cast("int"))
    .withColumn("avg_demand_last_12w", F.round(F.col("avg_demand_last_12w"), 1))
    .select(
        "sku", "store_id", "week",
        "store_name", "region",
        "product_name", "category",
        "predicted_demand", "avg_demand_last_12w",
        "risk_type", "demand_delta", "model_version",
    )
)
action_list.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.gold.forecast_action_list"
)

dbutils.notebook.exit(json.dumps({
    "mae_holdout": float(mae),
    "model_version": int(latest),
    "forecast_rows": out.count(),
    "action_rows": spark.table(f"{CATALOG}.gold.forecast_action_list").count(),
}))
