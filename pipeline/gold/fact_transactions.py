from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(comment="Transaction fact — ~2.2M rows, revenue computed")
def fact_transactions():
    return (
        spark.read.table("silver_transactions")
        .withColumn("date_id", F.col("transaction_date"))
        .withColumn("revenue", F.round(F.col("quantity_sold") * F.col("unit_price_at_sale"), 2))
        .select("transaction_id", "sku", "store_id", "date_id",
                "quantity_sold", "unit_price_at_sale", "revenue")
    )
