from pyspark import pipelines as dp

@dp.materialized_view(comment="Product dimension — 100 SKUs across 5 categories")
def dim_product():
    return spark.read.table("silver_products").select(
        "sku", "product_name", "category", "subcategory", "unit_cost", "unit_price"
    )
