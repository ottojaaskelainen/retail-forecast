from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType

_SCHEMA = StructType([
    StructField("promo_id",           StringType()),
    StructField("sku_or_category",    StringType()),
    StructField("store_id_or_region", StringType()),
    StructField("discount_pct",       StringType()),
    StructField("channel",            StringType()),
    StructField("promo_start_date",   StringType()),
    StructField("promo_end_date",     StringType()),
])

@dp.table(comment="Raw promotions — append-only ingest from SaaS CSV Volume")
def bronze_promotions():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("pathGlobFilter", "promotions.csv")
        .schema(_SCHEMA)
        .load("/Volumes/gdai_test_dev/retail_forecast/raw_promo_data/")
        .withColumn("_source_file",   F.col("_metadata.file_path"))
        .withColumn("_ingested_at",   F.current_timestamp())
        .withColumn("_source_system", F.lit("promo_platform"))
    )
