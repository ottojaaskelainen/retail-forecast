from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.temporary_view()
def bronze_stores_typed():
    return (
        spark.readStream.table("bronze_stores")
        .withColumn("manager_since", F.to_date("manager_since", "yyyy-MM-dd"))
        .withColumn("_updated_at", F.col("_ingested_at"))
    )


dp.create_streaming_table(
    name="silver_stores",
    comment="Deduplicated stores — upserted on store_id, manager_since cast to DATE",
)

dp.create_auto_cdc_flow(
    target="silver_stores",
    source="bronze_stores_typed",
    keys=["store_id"],
    sequence_by=F.col("_updated_at"),
    stored_as_scd_type=1,
    stored_as_scd_type_1_with_deletion_vector=False,
)
