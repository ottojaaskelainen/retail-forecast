from pyspark import pipelines as dp
from pyspark.sql import functions as F

_CATALOG = spark.conf.get("pipelines.catalog")
_BRONZE  = spark.conf.get("bronze_schema")
_SILVER  = spark.conf.get("silver_schema")


@dp.temporary_view()
def bronze_products_typed():
    return (
        spark.readStream.table(f"{_CATALOG}.{_BRONZE}.bronze_products")
        .withColumn("unit_cost",  F.col("unit_cost").cast("double"))
        .withColumn("unit_price", F.col("unit_price").cast("double"))
        .withColumn("_updated_at", F.col("_ingested_at"))
    )


dp.create_streaming_table(
    name=f"{_SILVER}.silver_products",
    comment="Deduplicated products — unit_cost and unit_price cast to DOUBLE",
    expect_all_or_drop={"valid_price_margin": "unit_price > unit_cost"},
)

dp.create_auto_cdc_flow(
    target=f"{_SILVER}.silver_products",
    source="bronze_products_typed",
    keys=["sku"],
    sequence_by=F.col("_updated_at"),
    stored_as_scd_type=1,
)
