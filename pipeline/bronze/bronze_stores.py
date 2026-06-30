from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType

_SCHEMA = StructType([
    StructField("store_id",      StringType()),
    StructField("store_name",    StringType()),
    StructField("region",        StringType()),
    StructField("store_type",    StringType()),
    StructField("manager_name",  StringType()),
    StructField("manager_email", StringType()),
    StructField("manager_phone", StringType()),
    StructField("manager_since", StringType()),
])

@dp.table(comment="Raw stores — append-only ingest from POS Parquet Volume")
def bronze_stores():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .schema(_SCHEMA)
        .load("/Volumes/gdai_test_dev/retail_forecast/raw_pos_data/stores/")
        .withColumn("_source_file",  F.col("_metadata.file_path"))
        .withColumn("_ingested_at",  F.current_timestamp())
        .withColumn("_source_system", F.lit("pos_system"))
    )
