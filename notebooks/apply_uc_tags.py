# Databricks notebook source
# MAGIC %md
# MAGIC # Unity Catalog Governance Tags
# MAGIC
# MAGIC Applies table- and column-level tags across all layers of the retail forecast pipeline.
# MAGIC Tags are used by Unity Catalog for data discovery, lineage classification, and governance reporting.
# MAGIC
# MAGIC **Layers covered**: bronze → silver → gold + ML model table
# MAGIC
# MAGIC Run this notebook after the pipeline has completed at least one successful update.

# COMMAND ----------

catalog = dbutils.widgets.get("catalog") if "catalog" in [w.name for w in dbutils.widgets.getAll()] else "gdai_test_dev"

# COMMAND ----------
# MAGIC %md
# MAGIC ## Bronze — raw ingest layer

# COMMAND ----------

spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_transactions SET TAGS ('layer' = 'bronze', 'domain' = 'retail', 'source_system' = 'pos_system', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_transactions ALTER COLUMN transaction_id SET TAGS ('semantic_type' = 'identifier')")
spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_transactions ALTER COLUMN quantity_sold SET TAGS ('semantic_type' = 'measure', 'classification' = 'operational')")
spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_transactions ALTER COLUMN unit_price_at_sale SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")

spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_products SET TAGS ('layer' = 'bronze', 'domain' = 'retail', 'source_system' = 'product_catalog', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_products ALTER COLUMN unit_cost SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")
spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_products ALTER COLUMN unit_price SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")

spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_stores SET TAGS ('layer' = 'bronze', 'domain' = 'retail', 'source_system' = 'store_master', 'data_product' = 'retail_forecast')")

spark.sql(f"ALTER TABLE {catalog}.bronze.bronze_promotions SET TAGS ('layer' = 'bronze', 'domain' = 'retail', 'source_system' = 'promo_system', 'data_product' = 'retail_forecast')")

print("Bronze tags applied.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Silver — validated & deduplicated layer

# COMMAND ----------

spark.sql(f"ALTER TABLE {catalog}.silver.silver_transactions SET TAGS ('layer' = 'silver', 'domain' = 'retail', 'data_quality' = 'validated', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.silver.silver_transactions ALTER COLUMN transaction_id SET TAGS ('semantic_type' = 'identifier')")
spark.sql(f"ALTER TABLE {catalog}.silver.silver_transactions ALTER COLUMN quantity_sold SET TAGS ('semantic_type' = 'measure', 'classification' = 'operational')")
spark.sql(f"ALTER TABLE {catalog}.silver.silver_transactions ALTER COLUMN unit_price_at_sale SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")

spark.sql(f"ALTER TABLE {catalog}.silver.silver_products SET TAGS ('layer' = 'silver', 'domain' = 'retail', 'data_quality' = 'validated', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.silver.silver_products ALTER COLUMN unit_cost SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")
spark.sql(f"ALTER TABLE {catalog}.silver.silver_products ALTER COLUMN unit_price SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")

spark.sql(f"ALTER TABLE {catalog}.silver.silver_stores SET TAGS ('layer' = 'silver', 'domain' = 'retail', 'data_quality' = 'validated', 'data_product' = 'retail_forecast')")

spark.sql(f"ALTER TABLE {catalog}.silver.silver_promotions SET TAGS ('layer' = 'silver', 'domain' = 'retail', 'data_quality' = 'validated', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.silver.silver_promotions ALTER COLUMN discount_pct SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")

print("Silver tags applied.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Gold — consumption-ready layer

# COMMAND ----------

spark.sql(f"ALTER TABLE {catalog}.gold.dim_product SET TAGS ('layer' = 'gold', 'domain' = 'retail', 'table_type' = 'dimension', 'consumption' = 'dashboard,genie', 'data_product' = 'retail_forecast')")

spark.sql(f"ALTER TABLE {catalog}.gold.dim_store SET TAGS ('layer' = 'gold', 'domain' = 'retail', 'table_type' = 'dimension', 'consumption' = 'dashboard,genie', 'data_product' = 'retail_forecast')")

spark.sql(f"ALTER TABLE {catalog}.gold.dim_date SET TAGS ('layer' = 'gold', 'domain' = 'retail', 'table_type' = 'dimension', 'consumption' = 'dashboard,genie', 'data_product' = 'retail_forecast')")

spark.sql(f"ALTER TABLE {catalog}.gold.fact_transactions SET TAGS ('layer' = 'gold', 'domain' = 'retail', 'table_type' = 'fact', 'consumption' = 'dashboard,genie', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.gold.fact_transactions ALTER COLUMN total_revenue SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")
spark.sql(f"ALTER TABLE {catalog}.gold.fact_transactions ALTER COLUMN unit_price_at_sale SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")
spark.sql(f"ALTER TABLE {catalog}.gold.fact_transactions ALTER COLUMN transaction_id SET TAGS ('semantic_type' = 'identifier')")

spark.sql(f"ALTER TABLE {catalog}.gold.fact_promotions SET TAGS ('layer' = 'gold', 'domain' = 'retail', 'table_type' = 'fact', 'consumption' = 'dashboard,genie', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.gold.fact_promotions ALTER COLUMN discount_pct SET TAGS ('semantic_type' = 'measure', 'classification' = 'financial')")

spark.sql(f"ALTER TABLE {catalog}.gold.forecast_demand SET TAGS ('layer' = 'gold', 'domain' = 'retail', 'table_type' = 'ml_output', 'consumption' = 'dashboard,genie,app', 'data_product' = 'retail_forecast')")
spark.sql(f"ALTER TABLE {catalog}.gold.forecast_demand ALTER COLUMN predicted_demand SET TAGS ('semantic_type' = 'ml_prediction', 'model' = 'retail_forecast_rf')")
spark.sql(f"ALTER TABLE {catalog}.gold.forecast_demand ALTER COLUMN is_stockout_risk SET TAGS ('semantic_type' = 'ml_prediction', 'model' = 'retail_forecast_rf')")
spark.sql(f"ALTER TABLE {catalog}.gold.forecast_demand ALTER COLUMN is_overstock_risk SET TAGS ('semantic_type' = 'ml_prediction', 'model' = 'retail_forecast_rf')")

print("Gold tags applied.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Column masking
# MAGIC
# MAGIC Creates a masking policy for financial columns so that only members of `T3-U-GDAI-All-Developers`
# MAGIC see actual values. Users outside the group get NULL automatically — no query changes required.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE FUNCTION {catalog}.gold.mask_financial(col DOUBLE)
  RETURN IF(is_account_group_member('T3-U-GDAI-All-Developers'), col, NULL)
""")

# Column masking must target a Delta table, not a view.
# fact_transactions is a Materialized View — the mask is applied to the
# underlying silver_transactions streaming table where unit_price_at_sale originates.
spark.sql(f"""
ALTER TABLE {catalog}.silver.silver_transactions
  ALTER COLUMN unit_price_at_sale SET MASK {catalog}.gold.mask_financial
""")

print("Column mask applied to silver_transactions.unit_price_at_sale.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Verify tags are visible

# COMMAND ----------

display(spark.sql(f"""
SELECT
  schema_name,
  table_name,
  tag_name,
  tag_value
FROM {catalog}.information_schema.table_tags
WHERE tag_name IN ('layer', 'table_type', 'data_product')
ORDER BY schema_name, table_name, tag_name
"""))
