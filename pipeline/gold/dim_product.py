from pyspark import pipelines as dp

_CATALOG = spark.conf.get("pipelines.catalog")
_SILVER  = spark.conf.get("silver_schema")
_GOLD    = spark.conf.get("gold_schema")

@dp.materialized_view(name=f"{_GOLD}.dim_product", comment="Product dimension — 100 SKUs across 5 categories")
def dim_product():
    return spark.read.table(f"{_CATALOG}.{_SILVER}.silver_products").select(
        "sku", "product_name", "category", "subcategory", "unit_cost", "unit_price"
    )
