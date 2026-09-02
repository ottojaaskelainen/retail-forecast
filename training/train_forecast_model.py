# Databricks notebook source

%pip install mlflow scikit-learn

# COMMAND ----------

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from datetime import date, timedelta
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from pyspark.sql import functions as F
from pyspark.sql.window import Window

dbutils.widgets.text("catalog", "retail_forecast")
CATALOG           = dbutils.widgets.get("catalog")
GOLD_SCHEMA       = "gold"
MODEL_NAME        = f"{CATALOG}.{GOLD_SCHEMA}.retail_forecast_rf"
MIN_HISTORY_WEEKS = 12
FEATURES          = ["week_of_year", "is_promoted", "discount_pct_feat", "rolling_4wk_avg"]
TARGET            = "total_quantity"
DATA_END          = date(2026, 6, 29)

_current_user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(f"/Users/{_current_user}/retail_forecast_demand")
mlflow.sklearn.autolog(log_models=False)  # params/metrics auto-logged; model logged manually with signature

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

# --- Rolling 4-week average and week_of_year in Spark ---
week_window = Window.partitionBy("sku", "store_id").orderBy("week").rowsBetween(-4, -1)
weekly = (
    weekly
    .withColumn("rolling_4wk_avg",
                F.coalesce(F.avg("total_quantity").over(week_window), F.lit(0.0)))
    .withColumn("week_of_year", F.weekofyear("week"))
)

# COMMAND ----------

# --- Convert to pandas for sklearn ---
weekly_pd = weekly.toPandas().sort_values(["sku", "store_id", "week"])

all_weeks = sorted(weekly_pd["week"].unique())
cutoff    = all_weeks[-8]
train_pd  = weekly_pd[weekly_pd["week"] < cutoff]
test_pd   = weekly_pd[weekly_pd["week"] >= cutoff]

X_train, y_train = train_pd[FEATURES], train_pd[TARGET]
X_test,  y_test  = test_pd[FEATURES],  test_pd[TARGET]

# COMMAND ----------

# --- Train and register to Unity Catalog ---
with mlflow.start_run() as run:
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    mae = mean_absolute_error(y_test, model.predict(X_test))
    mlflow.log_metric("mae_holdout", mae)
    print(f"MAE on held-out 8 weeks: {mae:.2f}")

    signature = infer_signature(X_train, model.predict(X_train))
    info = mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        signature=signature,
        input_example=X_train.iloc[:5],
        registered_model_name=MODEL_NAME,
    )

client = MlflowClient(registry_uri="databricks-uc")
versions = client.search_model_versions(f"name='{MODEL_NAME}'")
latest_version = max(versions, key=lambda v: int(v.version)).version
client.set_registered_model_alias(MODEL_NAME, "prod", latest_version)
print(f"Registered {MODEL_NAME} v{latest_version} as @prod")

# COMMAND ----------

# --- Build scoring dataset: next 8 weeks ---
forecast_weeks = [DATA_END + timedelta(weeks=i) for i in range(1, 9)]
forecast_weeks = [w - timedelta(days=w.weekday()) for w in forecast_weeks]

valid_pairs_pd = weekly_pd[["sku", "store_id"]].drop_duplicates()
avg_last_12w = (
    weekly_pd.sort_values("week")
    .groupby(["sku", "store_id"])["total_quantity"]
    .apply(lambda g: g.tail(12).mean())
    .reset_index(name="avg_demand_last_12w")
)
rolling_last_4w = (
    weekly_pd.sort_values("week")
    .groupby(["sku", "store_id"])["total_quantity"]
    .apply(lambda g: g.tail(4).mean())
    .reset_index(name="rolling_4wk_avg")
)

score_pd = pd.concat(
    [valid_pairs_pd.assign(week=fw, week_of_year=int(pd.Timestamp(fw).isocalendar().week))
     for fw in forecast_weeks],
    ignore_index=True,
)
score_pd = (
    score_pd
    .merge(avg_last_12w,  on=["sku", "store_id"])
    .merge(rolling_last_4w, on=["sku", "store_id"])
)

# COMMAND ----------

# --- Add promotion features to scoring data via Spark ---
score_spark = (
    spark.createDataFrame(score_pd)
    .join(F.broadcast(dim_store),   on="store_id")
    .join(F.broadcast(dim_product), on="sku")
    .withColumn("total_quantity", F.lit(0))  # placeholder — not used in scoring
)

all_promos = fact_promo.select(
    "target_sku", "target_category", "target_store_id", "target_region",
    "discount_pct", "promo_start_date", "promo_end_date",
)

score_group_cols = [
    "sku", "store_id", "week", "week_of_year",
    "avg_demand_last_12w", "rolling_4wk_avg",
    "region", "category", "total_quantity",
]
score_pd = (
    add_promo_features(score_spark, all_promos, score_group_cols)
    .drop("total_quantity", "region", "category")
    .toPandas()
)

# COMMAND ----------

# --- Batch score and write forecast_demand ---
score_pd["predicted_demand"] = (
    np.maximum(0, np.round(model.predict(score_pd[FEATURES]))).astype(int)
)
score_pd["is_stockout_risk"] = (
    (score_pd["predicted_demand"] > score_pd["avg_demand_last_12w"] * 1.3) &
    (score_pd["avg_demand_last_12w"] > 0)
)
score_pd["is_overstock_risk"] = (
    (score_pd["predicted_demand"] < score_pd["avg_demand_last_12w"] * 0.7) &
    (score_pd["avg_demand_last_12w"] > 0)
)
score_pd["model_version"] = f"rf_v{latest_version}"

output_cols = [
    "sku", "store_id", "week", "predicted_demand",
    "avg_demand_last_12w", "is_stockout_risk", "is_overstock_risk", "model_version",
]
spark.createDataFrame(score_pd[output_cols]).write.mode("overwrite").saveAsTable(
    f"{CATALOG}.{GOLD_SCHEMA}.forecast_demand"
)
print(f"Wrote {len(score_pd):,} rows to {CATALOG}.{GOLD_SCHEMA}.forecast_demand")
