# Databricks notebook source

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from datetime import date, timedelta
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

CATALOG = "gdai_test_dev"
SCHEMA  = "retail_forecast"
MIN_HISTORY_WEEKS = 12

mlflow.set_experiment("retail_forecast_demand")
mlflow.sklearn.autolog()

# --- Load data ---
fact_txn = spark.read.table(f"{CATALOG}.{SCHEMA}.fact_transactions").toPandas()
fact_promo = spark.read.table(f"{CATALOG}.{SCHEMA}.fact_promotions").toPandas()
dim_store = spark.read.table(f"{CATALOG}.{SCHEMA}.dim_store").toPandas()

fact_txn["transaction_date"] = pd.to_datetime(fact_txn["date_id"])
fact_txn["week"] = fact_txn["transaction_date"].dt.to_period("W-MON").apply(
    lambda p: p.start_time.date()
)

# --- Weekly aggregation ---
weekly = (
    fact_txn.groupby(["sku", "store_id", "week"])["quantity_sold"]
    .sum()
    .reset_index()
    .rename(columns={"quantity_sold": "total_quantity"})
)

# --- Filter to pairs with >= MIN_HISTORY_WEEKS of data ---
pair_counts = weekly.groupby(["sku", "store_id"])["week"].nunique()
valid_pairs = pair_counts[pair_counts >= MIN_HISTORY_WEEKS].reset_index()[["sku", "store_id"]]
weekly = weekly.merge(valid_pairs, on=["sku", "store_id"])

# --- Promotion helper ---
# Build lookup: for a (sku_or_cat, store_or_region, week) -> (is_promoted, discount_pct)
store_region = dict(zip(dim_store["store_id"], dim_store["region"]))

sku_to_cat = {}
for _, row in spark.read.table(f"{CATALOG}.{SCHEMA}.dim_product").toPandas().iterrows():
    sku_to_cat[row["sku"]] = row["category"]

fact_promo["promo_start_date"] = pd.to_datetime(fact_promo["promo_start_date"]).dt.date
fact_promo["promo_end_date"]   = pd.to_datetime(fact_promo["promo_end_date"]).dt.date

def get_promo_info(sku, store_id, week_date, promos_df):
    cat = sku_to_cat.get(sku)
    region = store_region.get(store_id)
    week_end = week_date + timedelta(days=6)
    for _, p in promos_df.iterrows():
        if p["promo_start_date"] > week_end or p["promo_end_date"] < week_date:
            continue
        # scope check
        store_match = (p["target_store_id"] == store_id) or (p["target_region"] == region)
        sku_match = (p["target_sku"] == sku) or (p["target_category"] == cat)
        if store_match and sku_match:
            return 1, float(p["discount_pct"])
    return 0, 0.0

# Apply promotion features (use only historical/active promos for training features)
past_promos = fact_promo[~fact_promo["is_future"]].copy()

print("Applying promotion features to training data...")
promo_cols = weekly.apply(
    lambda r: pd.Series(get_promo_info(r["sku"], r["store_id"], r["week"], past_promos)),
    axis=1
)
weekly[["is_promoted", "discount_pct_feat"]] = promo_cols

# --- Rolling 4-week average ---
weekly = weekly.sort_values(["sku", "store_id", "week"])
weekly["rolling_4wk_avg"] = (
    weekly.groupby(["sku", "store_id"])["total_quantity"]
    .transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean())
    .fillna(0)
)
weekly["week_of_year"] = pd.to_datetime(weekly["week"]).dt.isocalendar().week.astype(int)

# --- Train / test split (hold out last 8 weeks) ---
all_weeks = sorted(weekly["week"].unique())
cutoff = all_weeks[-8]
train = weekly[weekly["week"] < cutoff]
test  = weekly[weekly["week"] >= cutoff]

FEATURES = ["week_of_year", "is_promoted", "discount_pct_feat", "rolling_4wk_avg"]
TARGET   = "total_quantity"

X_train, y_train = train[FEATURES], train[TARGET]
X_test,  y_test  = test[FEATURES],  test[TARGET]

# --- Train ---
with mlflow.start_run():
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    mlflow.log_metric("mae_holdout", mae)
    print(f"MAE on held-out 8 weeks: {mae:.2f}")

# --- Build scoring dataset: next 8 weeks from DATA_END ---
DATA_END = date(2026, 6, 29)
forecast_weeks = [DATA_END + timedelta(weeks=i) for i in range(1, 9)]
# Align to ISO Monday
forecast_weeks = [
    w - timedelta(days=w.weekday()) for w in forecast_weeks
]

pairs = valid_pairs.copy()
score_rows = []
for _, pair in pairs.iterrows():
    sku, store_id = pair["sku"], pair["store_id"]
    # avg_demand_last_12w: last 12 weeks of training data
    pair_hist = weekly[(weekly["sku"] == sku) & (weekly["store_id"] == store_id)]
    avg_actual = pair_hist.sort_values("week").tail(12)["total_quantity"].mean()

    for week in forecast_weeks:
        week_of_year = pd.Timestamp(week).isocalendar().week
        # use future promos for scoring
        is_promo, disc = get_promo_info(sku, store_id, week, fact_promo)
        rolling_avg = pair_hist.sort_values("week").tail(4)["total_quantity"].mean()
        score_rows.append({
            "sku": sku,
            "store_id": store_id,
            "week": week,
            "week_of_year": int(week_of_year),
            "is_promoted": is_promo,
            "discount_pct_feat": disc,
            "rolling_4wk_avg": rolling_avg,
            "avg_demand_last_12w": avg_actual,
        })

score_df = pd.DataFrame(score_rows)
X_score = score_df[FEATURES]
score_df["predicted_demand"] = np.maximum(0, np.round(model.predict(X_score))).astype(int)

score_df["is_stockout_risk"]  = (
    (score_df["predicted_demand"] > score_df["avg_demand_last_12w"] * 1.3) &
    (score_df["avg_demand_last_12w"] > 0)
)
score_df["is_overstock_risk"] = (
    (score_df["predicted_demand"] < score_df["avg_demand_last_12w"] * 0.7) &
    (score_df["avg_demand_last_12w"] > 0)
)
score_df["model_version"] = "rf_v1"

output = score_df[[
    "sku", "store_id", "week", "predicted_demand",
    "avg_demand_last_12w", "is_stockout_risk", "is_overstock_risk", "model_version"
]]

spark.createDataFrame(output).write.mode("overwrite").saveAsTable(
    f"{CATALOG}.{SCHEMA}.forecast_demand"
)
print(f"Wrote {len(output):,} rows to forecast_demand")
