from pyspark import pipelines as dp
from pyspark.sql import functions as F

_CATALOG = spark.conf.get("pipelines.catalog")
_BRONZE  = spark.conf.get("bronze_schema")
_SILVER  = spark.conf.get("silver_schema")


@dp.temporary_view()
def bronze_transactions_typed():
    return (
        spark.readStream.table(f"{_CATALOG}.{_BRONZE}.bronze_transactions")
        .withColumn("transaction_date",   F.to_date("transaction_date", "yyyy-MM-dd"))
        .withColumn("quantity_sold",      F.col("quantity_sold").cast("int"))
        .withColumn("unit_price_at_sale", F.col("unit_price_at_sale").cast("double"))
        .withColumn("_updated_at", F.col("_ingested_at"))
    )


dp.create_streaming_table(
    name=f"{_SILVER}.silver_transactions",
    comment="Deduplicated transactions — types cast, DQ: qty > 0 and price > 0",
    expect_all_or_drop={
        "valid_quantity": "quantity_sold > 0",
        "valid_revenue":  "unit_price_at_sale > 0",
    },
)

dp.create_auto_cdc_flow(
    target=f"{_SILVER}.silver_transactions",
    source="bronze_transactions_typed",
    keys=["transaction_id"],
    sequence_by=F.col("_updated_at"),
    stored_as_scd_type=1,
)
