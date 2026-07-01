WITH weekly_actuals AS (
  SELECT
    DATE_TRUNC('week', CAST(t.date_id AS DATE)) AS week,
    ds.store_name,
    ds.region,
    t.sku,
    dp.product_name,
    dp.category,
    CAST(SUM(t.quantity_sold) AS DOUBLE) AS actual_demand,
    CAST(NULL AS DOUBLE)  AS predicted_demand,
    CAST(NULL AS DOUBLE)  AS avg_demand_last_12w,
    CAST(NULL AS BOOLEAN) AS is_stockout_risk,
    CAST(NULL AS BOOLEAN) AS is_overstock_risk
  FROM gdai_test_dev.gold.fact_transactions t
  JOIN gdai_test_dev.gold.dim_store ds  ON t.store_id = ds.store_id
  JOIN gdai_test_dev.gold.dim_product dp ON t.sku = dp.sku
  WHERE CAST(t.date_id AS DATE) >= (
      SELECT MAX(CAST(date_id AS DATE)) FROM gdai_test_dev.gold.fact_transactions
    ) - INTERVAL 12 WEEKS
    AND ds.store_name = :store_name
    AND t.sku = :sku
  GROUP BY 1, 2, 3, 4, 5, 6
),
forecast AS (
  SELECT
    fd.week,
    ds.store_name,
    ds.region,
    fd.sku,
    dp.product_name,
    dp.category,
    CAST(NULL AS DOUBLE)                    AS actual_demand,
    CAST(fd.predicted_demand AS DOUBLE)     AS predicted_demand,
    CAST(fd.avg_demand_last_12w AS DOUBLE)  AS avg_demand_last_12w,
    fd.is_stockout_risk,
    fd.is_overstock_risk
  FROM gdai_test_dev.gold.forecast_demand fd
  JOIN gdai_test_dev.gold.dim_store ds  ON fd.store_id = ds.store_id
  JOIN gdai_test_dev.gold.dim_product dp ON fd.sku = dp.sku
  WHERE ds.store_name = :store_name
    AND fd.sku = :sku
)
SELECT * FROM weekly_actuals
UNION ALL
SELECT * FROM forecast
ORDER BY week ASC
