from pyspark import pipelines as dp
from pyspark.sql import functions as F

_CATALOG = spark.conf.get("pipelines.catalog")
_BRONZE  = spark.conf.get("bronze_schema")
_SILVER  = spark.conf.get("silver_schema")


@dp.temporary_view()
def bronze_stores_typed():
    return (
        spark.readStream.table(f"{_CATALOG}.{_BRONZE}.bronze_stores")
        .withColumn("manager_since", F.to_date("manager_since", "yyyy-MM-dd"))
        .withColumn("_updated_at", F.col("_ingested_at"))
    )


dp.create_streaming_table(
    name=f"{_SILVER}.silver_stores",
    comment="Deduplicated stores — upserted on store_id, manager_since cast to DATE",
)

dp.create_auto_cdc_flow(
    target=f"{_SILVER}.silver_stores",
    source="bronze_stores_typed",
    keys=["store_id"],
    sequence_by=F.col("_updated_at"),
    stored_as_scd_type=1,
)
