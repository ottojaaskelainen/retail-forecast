-- @param week string
SELECT
    fd.week,
    ds.store_name,
    ds.region,
    fd.sku,
    dp.product_name,
    dp.category,
    fd.predicted_demand,
    ROUND(fd.avg_demand_last_12w, 1) AS avg_demand_last_12w,
    fd.is_stockout_risk,
    fd.is_overstock_risk
FROM retail_forecast.gold.forecast_demand fd
JOIN retail_forecast.gold.dim_store ds
    ON fd.store_id = ds.store_id
JOIN retail_forecast.gold.dim_product dp
    ON fd.sku = dp.sku
WHERE (fd.is_stockout_risk OR fd.is_overstock_risk)
  AND fd.week = CAST(:week AS DATE)
ORDER BY fd.is_stockout_risk DESC, fd.is_overstock_risk DESC, ds.store_name
