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
  const [selectedRegion, setSelectedRegion] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  const regions = useMemo(
    () => ['all', ...Array.from(new Set((data ?? []).map((r) => r.region))).sort()],
    [data],
  );
  const categories = useMemo(
    () => ['all', ...Array.from(new Set((data ?? []).map((r) => r.category))).sort()],
    [data],
  );

  const filtered = useMemo(
    () =>
      (data ?? []).filter(
        (r) =>
          (selectedRegion === 'all' || r.region === selectedRegion) &&
          (categoryFilter === 'all' || r.category === categoryFilter),
      ),
    [data, selectedRegion, categoryFilter],
  );

  const stockoutCount = filtered.filter((r) => toBool(r.is_stockout_risk)).length;
  const overstockCount = filtered.filter((r) => toBool(r.is_overstock_risk)).length;

  if (loading) return <div className="p-8"><Skeleton className="h-64 w-full" /></div>;
  if (error) return <div className="p-8 text-destructive">Error: {error}</div>;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-foreground">Demand Risk Dashboard</h1>

      <div className="grid grid-cols-2 gap-4">
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20">
          <CardHeader><CardTitle className="text-red-700 dark:text-red-400">Stockout Risk</CardTitle></CardHeader>
          <CardContent>
            <p className="text-4xl font-bold text-red-700 dark:text-red-400">{stockoutCount}</p>
            <p className="text-sm text-red-600 dark:text-red-500">SKU–store pairs</p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/20">
          <CardHeader><CardTitle className="text-amber-700 dark:text-amber-400">Overstock Risk</CardTitle></CardHeader>
          <CardContent>
            <p className="text-4xl font-bold text-amber-700 dark:text-amber-400">{overstockCount}</p>
            <p className="text-sm text-amber-600 dark:text-amber-500">SKU–store pairs</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-4">
        <Select value={selectedRegion} onValueChange={setSelectedRegion}>
          <SelectTrigger className="w-48"><SelectValue placeholder="All regions" /></SelectTrigger>
          <SelectContent>
            {regions.map((r) => (
              <SelectItem key={r} value={r}>{r === 'all' ? 'All regions' : r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="All categories" /></SelectTrigger>
          <SelectContent>
            {categories.map((c) => (
              <SelectItem key={c} value={c}>{c === 'all' ? 'All categories' : c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              {['Store', 'Region', 'SKU', 'Product', 'Category', 'Forecast Demand', 'Avg Actual (12w)', 'Risk'].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const isStockout = toBool(r.is_stockout_risk);
              const isOverstock = toBool(r.is_overstock_risk);
              const rowBg = isStockout
                ? 'bg-red-50 dark:bg-red-950/10'
                : isOverstock
                  ? 'bg-amber-50 dark:bg-amber-950/10'
                  : '';
              return (
                <tr key={`${r.store_name}-${r.sku}`} className={`border-t ${rowBg}`}>
                  <td className="px-3 py-1.5">{r.store_name}</td>
                  <td className="px-3 py-1.5">{r.region}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.sku}</td>
                  <td className="px-3 py-1.5">{r.product_name}</td>
                  <td className="px-3 py-1.5">{r.category}</td>
                  <td className="px-3 py-1.5 text-right">{r.predicted_demand}</td>
                  <td className="px-3 py-1.5 text-right">{Number(r.avg_demand_last_12w).toFixed(1)}</td>
                  <td className="px-3 py-1.5">
                    {isStockout && <span className="text-red-600 font-medium">Stockout</span>}
                    {isOverstock && <span className="text-amber-600 font-medium">Overstock</span>}
                    {!isStockout && !isOverstock && <span className="text-muted-foreground">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
