-- Lakebase (Postgres) read query for the Action List page.
-- Executed via AppKit.lakebase.query() in server/server.ts (GET /api/actions).
-- NOT an analytics-plugin query — do not call via useAnalyticsQuery().
SELECT
  f.sku,
  f.store_id,
  f.store_name,
  f.region,
  f.product_name,
  f.category,
  f.predicted_demand,
  f.avg_demand_last_12w,
  f.risk_type,
  f.demand_delta,
  COALESCE(s.status, 'open') AS status,
  s.note,
  s.updated_by,
  s.updated_at
FROM public.forecast_action_list f
LEFT JOIN app.action_status s
  ON s.sku = f.sku AND s.store_id = f.store_id AND s.week = f.week
WHERE f.week = (SELECT MIN(week) FROM public.forecast_action_list)
ORDER BY (f.risk_type = 'Stockout') DESC, ABS(f.demand_delta) DESC
LIMIT 500;
