from pyspark import pipelines as dp

@dp.materialized_view(comment="Store dimension — 20 stores with region and type")
def dim_store():
    return spark.read.table("silver_stores").select(
        "store_id", "store_name", "region", "store_type"
    )
