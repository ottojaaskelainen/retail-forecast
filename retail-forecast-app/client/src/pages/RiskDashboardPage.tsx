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

type RiskRow = {
  store_name: string;
  region: string;
  sku: string;
  product_name: string;
  category: string;
  predicted_demand: number;
  avg_weekly_actual: number;
  stockout_risk_flag: boolean;
  overstock_risk_flag: boolean;
};

export function RiskDashboardPage() {
  const { data, loading, error } = useAnalyticsQuery<RiskRow>('risk_dashboard', {});
  const [storeFilter, setStoreFilter]       = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  const stores     = useMemo(() => ['all', ...Array.from(new Set((data ?? []).map(r => r.store_name))).sort()], [data]);
  const categories = useMemo(() => ['all', ...Array.from(new Set((data ?? []).map(r => r.category))).sort()], [data]);

  const filtered = useMemo(() =>
    (data ?? []).filter(r =>
      (storeFilter     === 'all' || r.store_name === storeFilter) &&
      (categoryFilter  === 'all' || r.category   === categoryFilter)
    ),
    [data, storeFilter, categoryFilter]
  );

  const stockoutCount  = filtered.filter(r => r.stockout_risk_flag).length;
  const overstockCount = filtered.filter(r => r.overstock_risk_flag).length;

  if (loading) return <div className="p-8"><Skeleton className="h-64 w-full" /></div>;
  if (error)   return <div className="p-8 text-destructive">Error: {error}</div>;

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold">Demand Risk Dashboard</h1>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="border-red-200 bg-red-50">
          <CardHeader><CardTitle className="text-red-700">Stockout Risk</CardTitle></CardHeader>
          <CardContent><p className="text-4xl font-bold text-red-700">{stockoutCount}</p><p className="text-sm text-red-600">SKU–store pairs</p></CardContent>
        </Card>
        <Card className="border-amber-200 bg-amber-50">
          <CardHeader><CardTitle className="text-amber-700">Overstock Risk</CardTitle></CardHeader>
          <CardContent><p className="text-4xl font-bold text-amber-700">{overstockCount}</p><p className="text-sm text-amber-600">SKU–store pairs</p></CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <Select value={storeFilter} onValueChange={setStoreFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="All stores" /></SelectTrigger>
          <SelectContent>
            {stores.map(s => <SelectItem key={s} value={s}>{s === 'all' ? 'All stores' : s}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="All categories" /></SelectTrigger>
          <SelectContent>
            {categories.map(c => <SelectItem key={c} value={c}>{c === 'all' ? 'All categories' : c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              {['Store', 'Region', 'SKU', 'Product', 'Category', 'Forecast Demand', 'Avg Actual', 'Risk'].map(h => (
                <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const rowBg = r.stockout_risk_flag
                ? 'bg-red-50'
                : r.overstock_risk_flag
                ? 'bg-amber-50'
                : '';
              return (
                <tr key={`${r.store_name}-${r.sku}`} className={`border-t ${rowBg}`}>
                  <td className="px-3 py-1.5">{r.store_name}</td>
                  <td className="px-3 py-1.5">{r.region}</td>
                  <td className="px-3 py-1.5 font-mono">{r.sku}</td>
                  <td className="px-3 py-1.5">{r.product_name}</td>
                  <td className="px-3 py-1.5">{r.category}</td>
                  <td className="px-3 py-1.5 text-right">{r.predicted_demand}</td>
                  <td className="px-3 py-1.5 text-right">{r.avg_weekly_actual.toFixed(1)}</td>
                  <td className="px-3 py-1.5">
                    {r.stockout_risk_flag  && <span className="text-red-600 font-medium">Stockout</span>}
                    {r.overstock_risk_flag && <span className="text-amber-600 font-medium">Overstock</span>}
                    {!r.stockout_risk_flag && !r.overstock_risk_flag && <span className="text-muted-foreground">—</span>}
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
