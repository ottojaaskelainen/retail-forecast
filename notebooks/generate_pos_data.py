# Databricks notebook source

%pip install faker

# COMMAND ----------

import random
import pandas as pd
from datetime import date, timedelta
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DateType, DoubleType

dbutils.widgets.text("catalog", "gdai_test_dev")
CATALOG     = dbutils.widgets.get("catalog")
LANDING     = "landing"
POS_VOLUME  = f"/Volumes/{CATALOG}/{LANDING}/raw_pos_data"

# --- Reference data (must match generate_promo_data.py exactly) ---
STORES = [str(i) for i in range(1001, 1021)]
STORE_REGIONS = {
    **{str(i): "North"   for i in range(1001, 1005)},
    **{str(i): "South"   for i in range(1005, 1009)},
    **{str(i): "East"    for i in range(1009, 1013)},
    **{str(i): "West"    for i in range(1013, 1017)},
    **{str(i): "Central" for i in range(1017, 1021)},
}
STORE_TYPES = {s: (["flagship", "standard", "express"][int(s) % 3]) for s in STORES}
CATEGORIES = ["Electronics", "Grocery", "Apparel", "Home", "Outdoor"]
SKU_PREFIXES = {"Electronics": "EL", "Grocery": "GR", "Apparel": "AP", "Home": "HM", "Outdoor": "OD"}
SKUS_BY_CAT = {cat: [f"{SKU_PREFIXES[cat]}-{i:03d}" for i in range(1, 21)] for cat in CATEGORIES}
ALL_SKUS = [sku for skus in SKUS_BY_CAT.values() for sku in skus]
REGIONS = ["North", "South", "East", "West", "Central"]
CHANNELS = ["in_store", "online", "both"]
UNIT_PRICES = {
    "Electronics": (80, 500), "Grocery": (2, 30),
    "Apparel": (20, 120), "Home": (15, 200), "Outdoor": (25, 300),
}

DATA_START = date(2024, 7, 1)
DATA_END   = date(2026, 6, 29)
TODAY      = DATA_END

# Copy build_promotion_schedule verbatim from generate_promo_data.py
def build_promotion_schedule(seed=42):
    rng = random.Random(seed)
    promos = []

    def random_date_range(start, end, min_days=7, max_days=60):
        span = (end - start).days
        s = start + timedelta(days=rng.randint(0, max(0, span - max_days)))
        e = s + timedelta(days=rng.randint(min_days, max_days))
        if e > end:
            e = end
        return s, e

    def random_target():
        if rng.random() < 0.5:
            return rng.choice(ALL_SKUS)
        return rng.choice(CATEGORIES)

    def random_scope():
        if rng.random() < 0.5:
            return f"store_{rng.choice(STORES)}"
        return rng.choice(REGIONS)

    def make_promo(idx, start, end):
        return {
            "promo_id": f"PROMO-{idx:08X}",
            "sku_or_category": random_target(),
            "store_id_or_region": random_scope(),
            "discount_pct": f"{rng.choice([5, 10, 15, 20, 25, 30])}%",
            "channel": rng.choice(CHANNELS),
            "promo_start_date": start,
            "promo_end_date": end,
        }

    hist_end = TODAY - timedelta(days=1)
    for i in range(80):
        s, e = random_date_range(DATA_START, hist_end)
        promos.append(make_promo(i, s, e))

    for i in range(80, 100):
        duration = rng.randint(7, 30)
        s = TODAY - timedelta(days=rng.randint(1, duration - 1))
        e = TODAY + timedelta(days=rng.randint(1, 30))
        promos.append(make_promo(i, s, e))

    future_start = TODAY + timedelta(days=1)
    future_end = TODAY + timedelta(days=180)
    for i in range(100, 150):
        s, e = random_date_range(future_start, future_end, min_days=7, max_days=45)
        promos.append(make_promo(i, s, e))

    return promos


promos = build_promotion_schedule()

# -----------------------------------------------------------------------
# --- Stores (pandas — 20 rows) ---
# -----------------------------------------------------------------------
import faker
fake = faker.Faker()
fake.seed_instance(42)

stores_rows = []
for sid in STORES:
    stores_rows.append({
        "store_id": sid,
        "store_name": fake.company(),
        "region": STORE_REGIONS[sid],
        "store_type": STORE_TYPES[sid],
        "manager_name": fake.name(),
        "manager_email": fake.email(),
        "manager_phone": f"+1-555-{fake.numerify('###-####')}",
        "manager_since": fake.date_between(
            start_date=date(2015, 1, 1), end_date=date(2022, 12, 31)
        ).strftime("%Y-%m-%d"),
    })
stores_df = pd.DataFrame(stores_rows)
spark.createDataFrame(stores_df).write.mode("overwrite").parquet(f"{POS_VOLUME}/stores/")
print(f"stores: {len(stores_df)} rows written to {POS_VOLUME}/stores/")

# -----------------------------------------------------------------------
# --- Products (pandas — 100 rows) ---
# -----------------------------------------------------------------------
products_rows = []
for cat in CATEGORIES:
    pfx = SKU_PREFIXES[cat]
    subcats = [f"{cat[:3]}-A", f"{cat[:3]}-B", f"{cat[:3]}-C", f"{cat[:3]}-D"]
    lo, hi = UNIT_PRICES[cat]
    for i in range(1, 21):
        cost  = round(random.uniform(lo * 0.5, hi * 0.7), 2)
        price = round(cost * random.uniform(1.2, 2.0), 2)
        products_rows.append({
            "sku":          f"{pfx}-{i:03d}",
            "product_name": f"{cat} Product {i}",
            "category":     cat,
            "subcategory":  subcats[(i - 1) % 4],
            "unit_cost":    str(cost),
            "unit_price":   str(price),
        })
products_df = pd.DataFrame(products_rows)
spark.createDataFrame(products_df).write.mode("overwrite").parquet(f"{POS_VOLUME}/products/")
print(f"products: {len(products_df)} rows written to {POS_VOLUME}/products/")

# -----------------------------------------------------------------------
# --- Transactions (Spark-native, distributed — ~2.2M rows) ---
# -----------------------------------------------------------------------

# Step 1: Promotion schedule → Spark DataFrame, explode to daily grain
# Only historical + active promos affect generated demand; future promos do not.
promo_rows_spark = [
    (p["sku_or_category"], p["store_id_or_region"],
     int(p["discount_pct"].replace("%", "")) / 100.0,
     p["promo_start_date"], p["promo_end_date"])
    for p in promos
    if p["promo_start_date"] <= TODAY   # exclude future promos from demand generation
]

promo_schema = StructType([
    StructField("sku_or_category",    StringType()),
    StructField("store_id_or_region", StringType()),
    StructField("discount_float",     DoubleType()),
    StructField("promo_start",        DateType()),
    StructField("promo_end",          DateType()),
])

promo_daily = (
    spark.createDataFrame(promo_rows_spark, schema=promo_schema)
    .select(
        "sku_or_category", "store_id_or_region", "discount_float",
        F.explode(F.sequence("promo_start", "promo_end", F.expr("interval 1 day"))).alias("promo_date"),
    )
    # Split sku_or_category into target_sku (nullable) and target_category (nullable)
    .withColumn(
        "target_sku",
        F.when(F.col("sku_or_category").rlike("^[A-Z]{2}-\\d{3}$"), F.col("sku_or_category")),
    )
    .withColumn(
        "target_category",
        F.when(~F.col("sku_or_category").rlike("^[A-Z]{2}-\\d{3}$"), F.col("sku_or_category")),
    )
    # Split store_id_or_region into target_store_id (nullable) and target_region (nullable)
    .withColumn(
        "target_store_id",
        F.when(F.col("store_id_or_region").startswith("store_"),
               F.regexp_replace("store_id_or_region", "^store_", "")),
    )
    .withColumn(
        "target_region",
        F.when(~F.col("store_id_or_region").startswith("store_"), F.col("store_id_or_region")),
    )
    .drop("sku_or_category", "store_id_or_region")
)
print(f"Promotion daily rows (for demand generation): {promo_daily.count()}")

# Step 2: Store and SKU reference DataFrames for joins (both tiny — broadcast)
stores_spark = spark.createDataFrame(
    [(sid, STORE_REGIONS[sid]) for sid in STORES], ["store_id", "region"]
)
sku_spark = spark.createDataFrame(
    [(r["sku"], r["category"], float(r["unit_price"])) for _, r in products_df.iterrows()],
    ["sku", "category", "unit_price"],
)

# Step 3: Store × date cross join → 20 × 729 = 14,580 rows
#         Each row gets a random txn_count (100–200)
dates_spark = spark.sql(
    "SELECT explode(sequence(date('2024-07-01'), date('2026-06-29'), interval 1 day)) AS txn_date"
)
store_dates = (
    stores_spark.crossJoin(dates_spark)
    .withColumn("txn_count", (F.rand(seed=42) * 100 + 100).cast("int"))
)

# Step 4: posexplode → one row per transaction (~2.2M rows, distributed)
ALL_SKUS_ARRAY = F.array(*[F.lit(s) for s in ALL_SKUS])  # 100-element literal array

txns = (
    store_dates
    .select(
        "store_id", "region", "txn_date",
        F.posexplode(F.sequence(F.lit(1), F.col("txn_count"))).alias("txn_idx", "_"),
    )
    .drop("_")
    # Randomly assign a SKU (element_at is 1-indexed)
    .withColumn("sku", F.element_at(ALL_SKUS_ARRAY, (F.rand() * 100).cast("int") + 1))
)

# Step 5: Join with SKU reference for category and unit_price (broadcast — 100 rows)
txns = txns.join(F.broadcast(sku_spark), on="sku", how="left")

# Step 6: Left join with daily promotions (broadcast — ~4,500 rows)
txns_with_promo = txns.join(
    F.broadcast(promo_daily),
    on=(
        (F.col("txn_date") == F.col("promo_date")) &
        (
            (F.col("sku")      == F.col("target_sku")) |
            (F.col("category") == F.col("target_category"))
        ) &
        (
            (F.col("store_id") == F.col("target_store_id")) |
            (F.col("region")   == F.col("target_region"))
        )
    ),
    how="left",
)

# Step 7: Deduplicate — a transaction may match multiple promotions; keep max discount
txns_deduped = (
    txns_with_promo
    .groupBy("store_id", "region", "txn_date", "txn_idx", "sku", "category", "unit_price")
    .agg(F.max("discount_float").alias("discount_float"))
)

# Step 8: Apply demand multiplier and sale price, then cast all columns to STRING
txns_final = (
    txns_deduped
    .withColumn("discount_float", F.coalesce("discount_float", F.lit(0.0)))
    .withColumn("is_promoted", (F.col("discount_float") > 0).cast("int"))
    .withColumn(
        "quantity_sold",
        F.when(
            F.col("is_promoted") == 1,
            F.ceil((F.rand() * 6 + 2) * (1 + F.col("discount_float") * 3)).cast("int"),
        ).otherwise(
            (F.rand() * 5 + 1).cast("int"),
        ),
    )
    .withColumn(
        "unit_price_at_sale",
        F.when(
            F.col("is_promoted") == 1,
            F.round(F.col("unit_price") * (1 - F.col("discount_float")), 2),
        ).otherwise(F.col("unit_price")),
    )
    .withColumn("transaction_id", F.monotonically_increasing_id().cast("string"))
    .select(
        "transaction_id",
        "sku",
        "store_id",
        F.col("txn_date").cast("string").alias("transaction_date"),
        F.col("quantity_sold").cast("string"),
        F.col("unit_price_at_sale").cast("string"),
    )
)

# Step 9: Write to Volume subdirectory — Auto Loader reads the part files natively
txns_final.write.mode("overwrite").parquet(f"{POS_VOLUME}/transactions/")
actual_count = spark.read.parquet(f"{POS_VOLUME}/transactions/").count()
print(f"transactions: {actual_count:,} rows written to {POS_VOLUME}/transactions/")
