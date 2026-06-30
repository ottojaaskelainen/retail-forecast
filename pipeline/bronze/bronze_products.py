from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType

_SCHEMA = StructType([
    StructField("sku",          StringType()),
    StructField("product_name", StringType()),
    StructField("category",     StringType()),
    StructField("subcategory",  StringType()),
    StructField("unit_cost",    StringType()),
    StructField("unit_price",   StringType()),
])

@dp.table(comment="Raw products — append-only ingest from POS Parquet Volume")
def bronze_products():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .schema(_SCHEMA)
        .load("/Volumes/gdai_test_dev/retail_forecast/raw_pos_data/products/")
        .withColumn("_source_file",   F.col("_metadata.file_path"))
        .withColumn("_ingested_at",   F.current_timestamp())
        .withColumn("_source_system", F.lit("pos_system"))
    )
