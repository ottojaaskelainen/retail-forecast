from pyspark import pipelines as dp
from pyspark.sql import functions as F

_CATALOG = spark.conf.get("pipelines.catalog")
_SILVER  = spark.conf.get("silver_schema")
_GOLD    = spark.conf.get("gold_schema")

@dp.materialized_view(name=f"{_GOLD}.fact_promotions", comment="Promotion fact — 150 rows, active/future flags set at refresh time")
def fact_promotions():
    return (
        spark.read.table(f"{_CATALOG}.{_SILVER}.silver_promotions")
        .withColumn(
            "is_active",
            (F.col("promo_start_date") <= F.current_date()) &
            (F.col("promo_end_date")   >= F.current_date()),
        )
        .withColumn("is_future", F.col("promo_start_date") > F.current_date())
        .select(
            "promo_id", "target_sku", "target_category",
            "target_store_id", "target_region",
            "discount_pct", "channel",
            "promo_start_date", "promo_end_date", "is_active", "is_future",
        )
    )
