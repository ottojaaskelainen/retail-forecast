import {
  useAnalyticsQuery,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { useState, useMemo } from 'react';

const toBool = (v: unknown) => v === true || v === 'true';

export function RiskDashboardPage() {
  // Tiny query: the list of forecast weeks that have at-risk pairs (for the selector).
  const { data: weekOptions, loading: weeksLoading } = useAnalyticsQuery(
    'risk_dashboard_options',
    {},
  );
  const weeks = useMemo(
    () => Array.from(new Set((weekOptions ?? []).map((r) => String(r.week).slice(0, 10)))).sort(),
    [weekOptions],
  );

  const [weekFilter, setWeekFilter] = useState('');
  const [regionFilter, setRegionFilter] = useState('all');
  const [storeFilter, setStoreFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');

  // Default to the earliest (next) forecast week once the options load.
  const week = weekFilter || weeks[0] || '';

  // Load ONE week at a time — keeps the streamed payload well under the 1 MiB SSE cap.
  const riskParams = useMemo(() => ({ week: sql.string(week || '__none__') }), [week]);
  const { data, loading: dataLoading, error } = useAnalyticsQuery('risk_dashboard', riskParams);

  const rows = data ?? [];
  const loading = weeksLoading || (!!week && dataLoading);

  const regions = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => r.region))).sort()],
    [rows],
  );
  const stores = useMemo(() => {
    const f = regionFilter === 'all' ? rows : rows.filter((r) => r.region === regionFilter);
    return ['all', ...Array.from(new Set(f.map((r) => r.store_name))).sort()];
  }, [rows, regionFilter]);
  const categories = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => r.category))).sort()],
    [rows],
  );

  // The query is already scoped to `week`; only region/store/category filter client-side.
  const filtered = useMemo(
    () =>
      rows.filter(
        (r) =>
          (regionFilter === 'all' || r.region === regionFilter) &&
          (storeFilter === 'all' || r.store_name === storeFilter) &&
          (categoryFilter === 'all' || r.category === categoryFilter),
      ),
    [rows, regionFilter, storeFilter, categoryFilter],
  );

  const stockoutCount = filtered.filter((r) => toBool(r.is_stockout_risk)).length;
  const overstockCount = filtered.filter((r) => toBool(r.is_overstock_risk)).length;
  const atRiskRows = filtered;

  if (loading)
    return (
      <div className="p-8 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  if (error) return <div className="p-8 text-destructive">Error: {error}</div>;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Demand Risk Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">
          At-risk SKU–store pairs for the selected forecast week
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20">
          <CardHeader>
            <CardTitle className="text-red-700 dark:text-red-400">Stockout Risk</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold text-red-700 dark:text-red-400">{stockoutCount}</p>
            <p className="text-sm text-red-600 dark:text-red-500">
              SKU–store pairs · {week || '—'}
            </p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/20">
          <CardHeader>
            <CardTitle className="text-amber-700 dark:text-amber-400">Overstock Risk</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold text-amber-700 dark:text-amber-400">
              {overstockCount}
            </p>
            <p className="text-sm text-amber-600 dark:text-amber-500">
              SKU–store pairs · {week || '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-3 flex-wrap">
        <Select value={week} onValueChange={setWeekFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Select week" />
          </SelectTrigger>
          <SelectContent>
            {weeks.map((w) => (
              <SelectItem key={w} value={w}>
                {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={regionFilter}
          onValueChange={(v) => {
            setRegionFilter(v);
            setStoreFilter('all');
          }}
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All regions" />
          </SelectTrigger>
          <SelectContent>
            {regions.map((r) => (
              <SelectItem key={r} value={r}>
                {r === 'all' ? 'All regions' : r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={storeFilter} onValueChange={setStoreFilter}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="All stores" />
          </SelectTrigger>
          <SelectContent>
            {stores.map((s) => (
              <SelectItem key={s} value={s}>
                {s === 'all' ? 'All stores' : s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            {categories.map((c) => (
              <SelectItem key={c} value={c}>
                {c === 'all' ? 'All categories' : c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              {['Week', 'Store', 'Region', 'SKU', 'Product', 'Category', 'Forecast', 'Avg (12w)', 'Risk'].map(
                (h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {atRiskRows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-muted-foreground">
                  No at-risk pairs for the current filters
                </td>
              </tr>
            ) : (
              atRiskRows.map((r) => {
                const isStockout = toBool(r.is_stockout_risk);
                const isOverstock = toBool(r.is_overstock_risk);
                return (
                  <tr
                    key={`${r.week}-${r.store_name}-${r.sku}`}
                    className={`border-t ${
                      isStockout
                        ? 'bg-red-50 dark:bg-red-950/10'
                        : 'bg-amber-50 dark:bg-amber-950/10'
                    }`}
                  >
                    <td className="px-3 py-1.5 font-mono text-xs tabular-nums">
                      {String(r.week).slice(0, 10)}
                    </td>
                    <td className="px-3 py-1.5 font-medium">{r.store_name}</td>
                    <td className="px-3 py-1.5 text-muted-foreground">{r.region}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{r.sku}</td>
                    <td className="px-3 py-1.5">{r.product_name}</td>
                    <td className="px-3 py-1.5 text-muted-foreground">{r.category}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{r.predicted_demand}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                      {Number(r.avg_demand_last_12w).toFixed(1)}
                    </td>
                    <td className="px-3 py-1.5">
                      {isStockout && (
                        <span className="text-red-600 dark:text-red-400 font-medium">Stockout</span>
                      )}
                      {isOverstock && !isStockout && (
                        <span className="text-amber-600 dark:text-amber-400 font-medium">
                          Overstock
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
