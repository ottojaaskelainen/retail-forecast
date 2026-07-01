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
import { useState, useMemo } from 'react';

const toBool = (v: unknown) => v === true || v === 'true';

export function RiskDashboardPage() {
  const { data, loading, error } = useAnalyticsQuery('risk_dashboard', {});
  const [weekFilter, setWeekFilter] = useState('all');
  const [regionFilter, setRegionFilter] = useState('all');
  const [storeFilter, setStoreFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');

  const rows = data ?? [];

  const weeks = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => String(r.week).slice(0, 10)))).sort()],
    [rows],
  );
  const regions = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => r.region))).sort()],
    [rows],
  );
  const stores = useMemo(() => {
    const filtered = regionFilter === 'all' ? rows : rows.filter((r) => r.region === regionFilter);
    return ['all', ...Array.from(new Set(filtered.map((r) => r.store_name))).sort()];
  }, [rows, regionFilter]);
  const categories = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => r.category))).sort()],
    [rows],
  );

  const filtered = useMemo(
    () =>
      rows.filter(
        (r) =>
          (weekFilter === 'all' || String(r.week).slice(0, 10) === weekFilter) &&
          (regionFilter === 'all' || r.region === regionFilter) &&
          (storeFilter === 'all' || r.store_name === storeFilter) &&
          (categoryFilter === 'all' || r.category === categoryFilter),
      ),
    [rows, weekFilter, regionFilter, storeFilter, categoryFilter],
  );

  // KPIs based on the next (earliest) forecast week in the filtered set
  const nextWeek = useMemo(
    () => filtered.map((r) => r.week).sort()[0] ?? null,
    [filtered],
  );
  const nextWeekRows = useMemo(
    () => (nextWeek ? filtered.filter((r) => r.week === nextWeek) : []),
    [filtered, nextWeek],
  );
  const stockoutCount = nextWeekRows.filter((r) => toBool(r.is_stockout_risk)).length;
  const overstockCount = nextWeekRows.filter((r) => toBool(r.is_overstock_risk)).length;

  // Only show at-risk rows in the table
  const atRiskRows = useMemo(
    () => filtered.filter((r) => toBool(r.is_stockout_risk) || toBool(r.is_overstock_risk)),
    [filtered],
  );

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
          Upcoming forecast weeks — all at-risk SKU–store pairs
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
              SKU–store pairs · {nextWeek ?? '—'}
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
              SKU–store pairs · {nextWeek ?? '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-3 flex-wrap">
        <Select value={weekFilter} onValueChange={setWeekFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All weeks" />
          </SelectTrigger>
          <SelectContent>
            {weeks.map((w) => (
              <SelectItem key={w} value={w}>
                {w === 'all' ? 'All weeks' : w}
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
