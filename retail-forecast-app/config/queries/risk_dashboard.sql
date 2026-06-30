SELECT
    ds.store_name,
    ds.region,
    fd.sku,
    dp.product_name,
    dp.category,
    fd.predicted_demand,
    ROUND(fd.avg_weekly_actual, 1) AS avg_weekly_actual,
    fd.stockout_risk_flag,
    fd.overstock_risk_flag
FROM gdai_test_dev.retail_forecast.forecast_demand fd
JOIN gdai_test_dev.retail_forecast.dim_store ds
    ON fd.store_id = ds.store_id
JOIN gdai_test_dev.retail_forecast.dim_product dp
    ON fd.sku = dp.sku
WHERE fd.week = (
    SELECT MIN(week) FROM gdai_test_dev.retail_forecast.forecast_demand
)
ORDER BY fd.stockout_risk_flag DESC, fd.overstock_risk_flag DESC, ds.store_name
LIMIT 500
