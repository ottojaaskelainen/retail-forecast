from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType

_SCHEMA = StructType([
    StructField("transaction_id",     StringType()),
    StructField("sku",                StringType()),
    StructField("store_id",           StringType()),
    StructField("transaction_date",   StringType()),
    StructField("quantity_sold",      StringType()),
    StructField("unit_price_at_sale", StringType()),
])

@dp.table(comment="Raw transactions — append-only ingest from POS Parquet Volume")
def bronze_transactions():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .schema(_SCHEMA)
        .load("/Volumes/gdai_test_dev/retail_forecast/raw_pos_data/transactions/")
        .withColumn("_source_file",   F.col("_metadata.file_path"))
        .withColumn("_ingested_at",   F.current_timestamp())
        .withColumn("_source_system", F.lit("pos_system"))
    )
