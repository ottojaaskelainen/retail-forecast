from pyspark import pipelines as dp

_CATALOG = spark.conf.get("pipelines.catalog")
_SILVER  = spark.conf.get("silver_schema")
_GOLD    = spark.conf.get("gold_schema")

@dp.materialized_view(name=f"{_GOLD}.dim_store", comment="Store dimension — 20 stores with region and type")
def dim_store():
    return spark.read.table(f"{_CATALOG}.{_SILVER}.silver_stores").select(
        "store_id", "store_name", "region", "store_type"
    )
