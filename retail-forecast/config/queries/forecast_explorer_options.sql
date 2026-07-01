SELECT DISTINCT
    ds.store_name,
    ds.region,
    fd.sku,
    dp.product_name,
    dp.category
FROM gdai_test_dev.gold.forecast_demand fd
JOIN gdai_test_dev.gold.dim_store ds  ON fd.store_id = ds.store_id
JOIN gdai_test_dev.gold.dim_product dp ON fd.sku = dp.sku
WHERE fd.is_stockout_risk OR fd.is_overstock_risk
ORDER BY ds.store_name, fd.sku
