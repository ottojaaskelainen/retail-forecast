from pyspark import pipelines as dp
from pyspark.sql import functions as F

_CATALOG = spark.conf.get("pipelines.catalog")
_SILVER  = spark.conf.get("silver_schema")
_GOLD    = spark.conf.get("gold_schema")

@dp.materialized_view(name=f"{_GOLD}.fact_transactions", comment="Transaction fact — ~2.2M rows, revenue computed")
def fact_transactions():
    silver = spark.read.table(f"{_CATALOG}.{_SILVER}.silver_transactions")
    dim_product = spark.read.table(f"{_CATALOG}.{_GOLD}.dim_product").alias("dp")
    return (
        silver.alias("ft")
        .join(dim_product, F.col("ft.sku") == F.col("dp.sku"), "left")
        .withColumn("date_id", F.col("ft.transaction_date"))
        .withColumn("total_revenue", F.round(F.col("ft.quantity_sold") * F.col("ft.unit_price_at_sale"), 2))
        .withColumn(
            "is_promoted",
            F.when(F.col("ft.unit_price_at_sale") < F.col("dp.unit_price"), F.lit(1)).otherwise(F.lit(0))
        )
        .select("ft.transaction_id", "ft.sku", "ft.store_id", "date_id",
                "ft.quantity_sold", "ft.unit_price_at_sale", "total_revenue", "is_promoted")
    )
