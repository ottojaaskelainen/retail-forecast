# Databricks notebook source
# Standalone training step — reads labels from gold.fact_transactions, looks up features
# from the feature table via point-in-time FeatureLookup, trains bounded RF, registers @prod.

# COMMAND ----------

import json
import mlflow
import mlflow.sklearn
import pandas as pd
from datetime import date
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
FEATURES          = ["week_of_year", "is_promoted", "discount_pct_feat", "rolling_4wk_avg", "avg_demand_last_12w"]
TARGET            = "total_quantity"

mlflow.set_registry_uri("databricks-uc")
mlflow.sklearn.autolog(log_models=False)  # params/metrics auto-logged; model logged manually via fe.log_model

_current_user = spark.sql("SELECT current_user()").first()[0]
fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")

# COMMAND ----------

# --- Build labels: weekly total_quantity per sku/store, valid pairs only ---
fact_txn = spark.read.table(f"{CATALOG}.{GOLD_SCHEMA}.fact_transactions")

weekly = (
    fact_txn
    .withColumn("week", F.date_trunc("WEEK", F.col("date_id")).cast("date"))
    .groupBy("sku", "store_id", "week")
    .agg(F.sum("quantity_sold").alias("total_quantity"))
)

# Keep only (sku, store_id) pairs with at least MIN_HISTORY_WEEKS distinct weeks
valid_pairs = (
    weekly
    .groupBy("sku", "store_id")
    .agg(F.countDistinct("week").alias("week_count"))
    .filter(F.col("week_count") >= MIN_HISTORY_WEEKS)
    .select("sku", "store_id")
)

labels_df = weekly.join(valid_pairs, on=["sku", "store_id"]).select(
    "sku", "store_id", "week", "total_quantity"
)

# COMMAND ----------

# --- Holdout split: hold out last 8 weeks as test set ---
all_weeks = [r.week for r in labels_df.select("week").distinct().orderBy("week").collect()]
cutoff = all_weeks[-8]  # hold out last 8 weeks

train_labels = labels_df.filter(F.col("week") < cutoff)
test_labels  = labels_df.filter(F.col("week") >= cutoff)

print(f"Cutoff week: {cutoff}")
print(f"Train label rows: {train_labels.count()}, Test label rows: {test_labels.count()}")

# COMMAND ----------

# --- Build point-in-time training set via FeatureLookup ---
# FeatureLookup with no feature_names returns all feature columns from the table (the 5 FEATURES).
# exclude_columns drops the 3 join keys so the training schema is exactly FEATURES.
lookups = [FeatureLookup(
    table_name=FEATURE_TABLE,
    lookup_key=["sku", "store_id"],
    timestamp_lookup_key="week",  # point-in-time: feature.week <= label.week
)]

training_set = fe.create_training_set(
    df=train_labels,
    feature_lookups=lookups,
    label="total_quantity",
    exclude_columns=["week", "sku", "store_id"],
)
train_pd = training_set.load_df().toPandas()
X_train, y_train = train_pd[FEATURES], train_pd[TARGET]

# COMMAND ----------

# --- Train, compute holdout MAE, and register with fe.log_model ---
# IMPORTANT: n_estimators=50, max_depth=12 are mandatory bounds (prior OOM ruling:
# unbounded depth blows up the score_batch UDF).
mlflow.set_experiment(f"/Users/{_current_user}/retail_forecast_demand")
with mlflow.start_run() as run:
    model = RandomForestRegressor(n_estimators=50, max_depth=12, random_state=42)
    model.fit(X_train, y_train)

    test_set = fe.create_training_set(
        df=test_labels,
        feature_lookups=lookups,
        label="total_quantity",
        exclude_columns=["week", "sku", "store_id"],
    )
    test_pd = test_set.load_df().toPandas()
    mae = mean_absolute_error(test_pd[TARGET], model.predict(test_pd[FEATURES]))
    mlflow.log_metric("mae_holdout", mae)
    print(f"MAE holdout: {mae:.2f}")

    fe.log_model(
        model=model,
        artifact_path="model",
        flavor=mlflow.sklearn,
        training_set=training_set,
        registered_model_name=MODEL_NAME,
    )

# COMMAND ----------

# --- Set @prod alias to the newest registered version ---
client = MlflowClient(registry_uri="databricks-uc")
latest = max(
    client.search_model_versions(f"name='{MODEL_NAME}'"),
    key=lambda v: int(v.version),
).version
client.set_registered_model_alias(MODEL_NAME, "prod", latest)
print(f"Registered {MODEL_NAME} v{latest} @prod")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"mae_holdout": float(mae), "model_version": int(latest)}))
