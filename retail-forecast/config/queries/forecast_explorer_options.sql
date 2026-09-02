SELECT DISTINCT
    ds.store_name,
    ds.region,
    fd.sku,
    dp.product_name,
    dp.category
FROM retail_forecast.gold.forecast_demand fd
JOIN retail_forecast.gold.dim_store ds  ON fd.store_id = ds.store_id
JOIN retail_forecast.gold.dim_product dp ON fd.sku = dp.sku
WHERE fd.is_stockout_risk OR fd.is_overstock_risk
ORDER BY ds.store_name, fd.sku
