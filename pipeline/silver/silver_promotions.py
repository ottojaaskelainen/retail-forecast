from pyspark import pipelines as dp
from pyspark.sql import functions as F

_CATALOG = spark.conf.get("pipelines.catalog")
_BRONZE  = spark.conf.get("bronze_schema")
_SILVER  = spark.conf.get("silver_schema")


@dp.temporary_view()
def bronze_promotions_typed():
    return (
        spark.readStream.table(f"{_CATALOG}.{_BRONZE}.bronze_promotions")
        .withColumn("promo_start_date", F.to_date("promo_start_date", "MM/dd/yyyy"))
        .withColumn("promo_end_date",   F.to_date("promo_end_date",   "MM/dd/yyyy"))
        .withColumn(
            "discount_pct",
            F.regexp_replace("discount_pct", "%", "").cast("double") / 100.0,
        )
        .withColumn(
            "target_sku",
            F.when(F.col("sku_or_category").rlike("^[A-Z]{2}-\\d{3}$"),
                   F.col("sku_or_category")),
        )
        .withColumn(
            "target_category",
            F.when(~F.col("sku_or_category").rlike("^[A-Z]{2}-\\d{3}$"),
                   F.col("sku_or_category")),
        )
        .withColumn(
            "target_store_id",
            F.when(F.col("store_id_or_region").startswith("store_"),
                   F.regexp_replace("store_id_or_region", "^store_", "")),
        )
        .withColumn(
            "target_region",
            F.when(~F.col("store_id_or_region").startswith("store_"),
                   F.col("store_id_or_region")),
        )
        .withColumn("_updated_at", F.col("_ingested_at"))
        .drop("sku_or_category", "store_id_or_region")
    )


dp.create_streaming_table(
    name=f"{_SILVER}.silver_promotions",
    comment="Conformed promotions — dates MM/DD/YYYY->DATE, discount %->DOUBLE, ids split",
    expect_all_or_drop={
        "valid_discount":   "discount_pct > 0 AND discount_pct < 1",
        "valid_date_range": "promo_end_date >= promo_start_date",
    },
)

dp.create_auto_cdc_flow(
    target=f"{_SILVER}.silver_promotions",
    source="bronze_promotions_typed",
    keys=["promo_id"],
    sequence_by=F.col("_updated_at"),
    stored_as_scd_type=1,
)
