# Databricks notebook source

# COMMAND ----------

# Standalone scoring step for the retail-forecast MLOps pipeline.
#
# Computes DATA_END identically to build_features (max week of fact_transactions
# weekly agg); scores next 8 future weeks via fe.score_batch on @prod; writes
# forecast_demand + forecast_action_list (schema unchanged for Lakebase sync).
#
# This notebook does NOT train a model.  It resolves the @prod alias at runtime
# so it is safe to run independently of any training session variable state.

import json
import mlflow
from datetime import date, timedelta
from mlflow.tracking import MlflowClient
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from databricks.feature_engineering import FeatureEngineeringClient

dbutils.widgets.text("catalog", "retail_forecast")
CATALOG           = dbutils.widgets.get("catalog")
GOLD_SCHEMA       = "gold"
FEATURE_SCHEMA    = "feature"
MODEL_NAME        = f"{CATALOG}.{GOLD_SCHEMA}.retail_forecast_demand"
MIN_HISTORY_WEEKS = 12

mlflow.set_registry_uri("databricks-uc")
fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")

# COMMAND ----------

# --- Load tables ---
fact_txn         = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.fact_transactions")
dim_store_full   = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_store")
dim_product_full = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.dim_product")

# COMMAND ----------

# --- Weekly aggregation (MUST match build_features.py exactly) ---
weekly = (
    fact_txn
    .withColumn("week", F.date_trunc("WEEK", F.col("date_id")).cast("date"))
    .groupBy("sku", "store_id", "week")
    .agg(F.sum("quantity_sold").alias("total_quantity"))
)

# Dynamic DATA_END: max week observed in fact_transactions — never hardcoded.
# Identical to build_features.py so forward-dated score keys align with feature rows.
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

# COMMAND ----------

# --- Build 8 forward-dated forecast weeks ---
forecast_weeks_list = [DATA_END + timedelta(weeks=i) for i in range(1, 9)]
# Monday-snap: ensure each week starts on Monday (ISO weekday 0)
forecast_weeks_list = [w - timedelta(days=w.weekday()) for w in forecast_weeks_list]

forecast_weeks_spark = spark.createDataFrame(
    [(w,) for w in forecast_weeks_list], ["week"]
).withColumn("week", F.col("week").cast("date"))

# COMMAND ----------

# --- Resolve @prod model version for labeling ---
latest = (
    MlflowClient(registry_uri="databricks-uc")
    .get_model_version_by_alias(MODEL_NAME, "prod")
    .version
)
print(f"Scoring with {MODEL_NAME} @prod (version {latest})")

# COMMAND ----------

# --- Build score keys (sku, store_id, week) — keys only ---
score_keys = (
    valid_pairs.crossJoin(forecast_weeks_spark)
    .select("sku", "store_id", "week")
)

# --- Score via FeatureEngineeringClient (feature lookup happens server-side) ---
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

# avg_demand_last_12w is already present on scored via FeatureLookup — do NOT join again.

# COMMAND ----------

# --- Derive risk flags and write gold.forecast_demand ---
out = (
    scored
    .withColumn("is_stockout_risk",
                (F.col("predicted_demand") > F.col("avg_demand_last_12w") * 1.3) &
                (F.col("avg_demand_last_12w") > 0))
    .withColumn("is_overstock_risk",
                (F.col("predicted_demand") < F.col("avg_demand_last_12w") * 0.7) &
                (F.col("avg_demand_last_12w") > 0))
    .withColumn("model_version", F.lit(f"lgbm_poisson_v{latest}"))
    .select("sku", "store_id", "week", "predicted_demand", "avg_demand_last_12w",
            "is_stockout_risk", "is_overstock_risk", "model_version")
)
out.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.{GOLD_SCHEMA}.forecast_demand"
)
forecast_rows = out.count()
print(f"forecast_demand rows: {forecast_rows}")

# COMMAND ----------

# --- Materialize gold.forecast_action_list (synced-table source) ---
# Schema is frozen — Lakebase synced table depends on it.
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
    f"{CATALOG}.{GOLD_SCHEMA}.forecast_action_list"
)
action_rows = spark.table(f"{CATALOG}.{GOLD_SCHEMA}.forecast_action_list").count()
print(f"forecast_action_list rows: {action_rows}")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({
    "forecast_rows": forecast_rows,
    "action_rows": action_rows,
    "forecast_weeks": [str(w) for w in forecast_weeks_list],
}))
