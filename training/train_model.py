# Databricks notebook source
# Standalone training step — reads labels from gold.fact_transactions, looks up features
# from the feature table via point-in-time FeatureLookup, trains a LightGBM (Poisson) demand
# model, logs it alongside the naive trailing-average baselines, and registers @prod.

# COMMAND ----------

import json
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.tracking import MlflowClient
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error
from pyspark.sql import functions as F
from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup

dbutils.widgets.text("catalog", "retail_forecast")
CATALOG           = dbutils.widgets.get("catalog")
GOLD_SCHEMA       = "gold"
FEATURE_SCHEMA    = "feature"
MODEL_NAME        = f"{CATALOG}.{GOLD_SCHEMA}.retail_forecast_demand"
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
# LightGBM with a Poisson objective fits non-negative count demand better than squared-error
# RF, and is a much lighter artifact than a deep RF forest (so the score_batch UDF stays well
# within memory — the earlier RF depth bound is no longer needed).
mlflow.set_experiment(f"/Users/{_current_user}/retail_forecast_demand")
with mlflow.start_run() as run:
    model = LGBMRegressor(
        objective="poisson", n_estimators=400, learning_rate=0.05, num_leaves=31,
        min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, verbose=-1,
    )
    model.fit(X_train, y_train)

    test_set = fe.create_training_set(
        df=test_labels,
        feature_lookups=lookups,
        label="total_quantity",
        exclude_columns=["week", "sku", "store_id"],
    )
    test_pd = test_set.load_df().toPandas()
    preds = model.predict(test_pd[FEATURES]).clip(min=0)
    mae = mean_absolute_error(test_pd[TARGET], preds)

    # Naive trailing-average baselines on the identical holdout — the bar the model must beat.
    mae_naive_avg12w   = mean_absolute_error(test_pd[TARGET], test_pd["avg_demand_last_12w"])
    mae_naive_rolling4w = mean_absolute_error(test_pd[TARGET], test_pd["rolling_4wk_avg"])
    mlflow.log_metric("mae_holdout", mae)
    mlflow.log_metric("mae_naive_avg12w", mae_naive_avg12w)
    mlflow.log_metric("mae_naive_rolling4w", mae_naive_rolling4w)
    print(f"MAE holdout: {mae:.2f}  |  naive avg12w: {mae_naive_avg12w:.2f}  |  "
          f"naive rolling4w: {mae_naive_rolling4w:.2f}")

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

dbutils.notebook.exit(json.dumps({
    "mae_holdout": float(mae),
    "mae_naive_avg12w": float(mae_naive_avg12w),
    "mae_naive_rolling4w": float(mae_naive_rolling4w),
    "model_version": int(latest),
}))
