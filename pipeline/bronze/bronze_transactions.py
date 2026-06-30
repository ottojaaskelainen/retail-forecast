from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType

_CATALOG = spark.conf.get("pipelines.catalog")
_LANDING = spark.conf.get("landing_schema")
_BRONZE  = spark.conf.get("bronze_schema")

_SCHEMA = StructType([
    StructField("transaction_id",     StringType()),
    StructField("sku",                StringType()),
    StructField("store_id",           StringType()),
    StructField("transaction_date",   StringType()),
    StructField("quantity_sold",      StringType()),
    StructField("unit_price_at_sale", StringType()),
])

@dp.table(name=f"{_BRONZE}.bronze_transactions", comment="Raw transactions — append-only ingest from POS Parquet Volume")
def bronze_transactions():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .schema(_SCHEMA)
        .load(f"/Volumes/{_CATALOG}/{_LANDING}/raw_pos_data/transactions/")
        .withColumn("_source_file",   F.col("_metadata.file_path"))
        .withColumn("_ingested_at",   F.current_timestamp())
        .withColumn("_source_system", F.lit("pos_system"))
    )
