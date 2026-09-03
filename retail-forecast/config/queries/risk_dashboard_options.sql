-- Distinct forecast weeks that have at-risk pairs, for the Risk Dashboard week selector.
-- Tiny result (one row per week) so it never approaches the SSE event-size limit.
SELECT DISTINCT fd.week
FROM retail_forecast.gold.forecast_demand fd
WHERE fd.is_stockout_risk OR fd.is_overstock_risk
ORDER BY fd.week ASC
