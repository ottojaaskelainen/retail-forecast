SELECT
    ds.store_name,
    ds.region,
    fd.sku,
    dp.product_name,
    dp.category,
    fd.predicted_demand,
    ROUND(fd.avg_demand_last_12w, 1) AS avg_demand_last_12w,
    CASE
        WHEN fd.is_stockout_risk AND fd.is_overstock_risk THEN 'Both'
        WHEN fd.is_stockout_risk THEN 'Stockout'
        WHEN fd.is_overstock_risk THEN 'Overstock'
    END AS risk_type,
    ROUND(fd.predicted_demand - fd.avg_demand_last_12w, 0) AS demand_delta
FROM retail_forecast.gold.forecast_demand fd
JOIN retail_forecast.gold.dim_store ds
    ON fd.store_id = ds.store_id
JOIN retail_forecast.gold.dim_product dp
    ON fd.sku = dp.sku
WHERE fd.week = (SELECT MAX(week) FROM retail_forecast.gold.forecast_demand)
  AND (fd.is_stockout_risk OR fd.is_overstock_risk)
ORDER BY fd.is_stockout_risk DESC, ABS(fd.predicted_demand - fd.avg_demand_last_12w) DESC
LIMIT 500
