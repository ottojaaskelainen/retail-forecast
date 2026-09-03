# Databricks notebook source

%pip install faker

# COMMAND ----------

import random
import csv
import io
from datetime import date, timedelta

dbutils.widgets.text("catalog", "retail_forecast")
CATALOG      = dbutils.widgets.get("catalog")
LANDING      = "landing"
PROMO_VOLUME = f"/Volumes/{CATALOG}/{LANDING}/raw_promo_data"

# --- Reference data (must match generate_pos_data.py exactly) ---
STORES = [str(i) for i in range(1001, 1021)]
STORE_REGIONS = {
    **{str(i): "North"   for i in range(1001, 1005)},
    **{str(i): "South"   for i in range(1005, 1009)},
    **{str(i): "East"    for i in range(1009, 1013)},
    **{str(i): "West"    for i in range(1013, 1017)},
    **{str(i): "Central" for i in range(1017, 1021)},
}
CATEGORIES = ["Electronics", "Grocery", "Apparel", "Home", "Outdoor"]
SKU_PREFIXES = {"Electronics": "EL", "Grocery": "GR", "Apparel": "AP", "Home": "HM", "Outdoor": "OD"}
SKUS_BY_CAT = {cat: [f"{SKU_PREFIXES[cat]}-{i:03d}" for i in range(1, 21)] for cat in CATEGORIES}
ALL_SKUS = [sku for skus in SKUS_BY_CAT.values() for sku in skus]
REGIONS = ["North", "South", "East", "West", "Central"]
CHANNELS = ["in_store", "online", "both"]

DATA_START = date(2024, 7, 1)
today      = date.today()
DATA_END   = today - timedelta(days=today.weekday())  # most recent Monday on/before today
TODAY      = DATA_END  # treat last data date as "today" for historical/future split


def build_promotion_schedule(seed=42):
    """
    Returns list of dicts matching the promotions CSV schema.
    MUST use the same seed and logic as generate_pos_data.py.
    """
    rng = random.Random(seed)
    promos = []

    def random_date_range(start, end, min_days=7, max_days=60):
        span = (end - start).days
        s = start + timedelta(days=rng.randint(0, max(0, span - max_days)))
        e = s + timedelta(days=rng.randint(min_days, max_days))
        if e > end:
            e = end
        return s, e

    def fmt(d):
        return d.strftime("%m/%d/%Y")

    def random_target():
        # Bias toward category-wide promos (broader coverage so the promo signal is learnable)
        if rng.random() < 0.4:
            return rng.choice(ALL_SKUS)
        return rng.choice(CATEGORIES)

    def random_scope():
        # Bias toward region-wide scope (broader coverage)
        if rng.random() < 0.4:
            return f"store_{rng.choice(STORES)}"
        return rng.choice(REGIONS)

    def snap_to_weeks(start, end):
        # Align every promo to whole Mon-Sun weeks so a "promoted week" is fully promoted and
        # the weekly is_promoted/discount features exactly describe the week's demand lift.
        start = start - timedelta(days=start.weekday())        # back to Monday
        end = end + timedelta(days=(6 - end.weekday()))        # forward to Sunday
        return start, end

    def make_promo(idx, start, end):
        start, end = snap_to_weeks(start, end)
        return {
            "promo_id": f"PROMO-{idx:08X}",
            "sku_or_category": random_target(),
            "store_id_or_region": random_scope(),
            "discount_pct": f"{rng.choice([10, 15, 20, 25, 30, 40])}%",
            "channel": rng.choice(CHANNELS),
            "promo_start_date": fmt(start),
            "promo_end_date": fmt(end),
        }

    # 250 historical (fully before TODAY)
    hist_end = TODAY - timedelta(days=1)
    for i in range(250):
        s, e = random_date_range(DATA_START, hist_end)
        promos.append(make_promo(i, s, e))

    # 20 active (spanning TODAY)
    for i in range(250, 270):
        duration = rng.randint(7, 30)
        s = TODAY - timedelta(days=rng.randint(1, duration - 1))
        e = TODAY + timedelta(days=rng.randint(1, 30))
        promos.append(make_promo(i, s, e))

    # 70 future (start after TODAY)
    future_start = TODAY + timedelta(days=1)
    future_end = TODAY + timedelta(days=180)
    for i in range(270, 340):
        s, e = random_date_range(future_start, future_end, min_days=7, max_days=45)
        promos.append(make_promo(i, s, e))

    return promos


promos = build_promotion_schedule()

# Write CSV to Volume
csv_buffer = io.StringIO()
writer = csv.DictWriter(csv_buffer, fieldnames=[
    "promo_id", "sku_or_category", "store_id_or_region",
    "discount_pct", "channel", "promo_start_date", "promo_end_date"
])
writer.writeheader()
writer.writerows(promos)

dbutils.fs.put(f"{PROMO_VOLUME}/promotions.csv", csv_buffer.getvalue(), overwrite=True)
print(f"Wrote {len(promos)} promotions to {PROMO_VOLUME}/promotions.csv")

# Verify split
hist  = sum(1 for p in promos if p["promo_start_date"] < TODAY.strftime("%m/%d/%Y"))
fut   = sum(1 for p in promos if p["promo_start_date"] > TODAY.strftime("%m/%d/%Y"))
print(f"Historical: {hist}, Future: {fut}")
