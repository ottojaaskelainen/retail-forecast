import {
  useAnalyticsQuery,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from '@databricks/appkit-ui/react';
import { useMemo, useState } from 'react';

const riskBadge = (type: string) => {
  switch (type) {
    case 'Stockout':
      return (
        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400">
          Stockout
        </span>
      );
    case 'Overstock':
      return (
        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400">
          Overstock
        </span>
      );
    case 'Both':
      return (
        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-400">
          Both
        </span>
      );
    default:
      return null;
  }
};

export function ActionListPage() {
  const { data, loading, error } = useAnalyticsQuery('action_list', {});
  const [region, setRegion] = useState('all');
  const [store, setStore] = useState('all');
  const [category, setCategory] = useState('all');
  const [riskType, setRiskType] = useState('all');

  const rows = data ?? [];

  const regions = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => r.region))).sort()],
    [rows],
  );
  const stores = useMemo(() => {
    const filtered = region === 'all' ? rows : rows.filter((r) => r.region === region);
    return ['all', ...Array.from(new Set(filtered.map((r) => r.store_name))).sort()];
  }, [rows, region]);
  const categories = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => r.category))).sort()],
    [rows],
  );

  const filtered = useMemo(
    () =>
      rows.filter(
        (r) =>
          (region === 'all' || r.region === region) &&
          (store === 'all' || r.store_name === store) &&
          (category === 'all' || r.category === category) &&
          (riskType === 'all' || r.risk_type === riskType),
      ),
    [rows, region, store, category, riskType],
  );

  const stockoutCount = rows.filter((r) => r.risk_type === 'Stockout').length;
  const overstockCount = rows.filter((r) => r.risk_type === 'Overstock').length;
  const bothCount = rows.filter((r) => r.risk_type === 'Both').length;

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
        <h1 className="text-2xl font-bold text-foreground">Inventory Action List</h1>
        <p className="text-sm text-muted-foreground mt-1">
          At-risk SKU–store pairs for the current forecast week
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm text-red-700 dark:text-red-400">Stockout Risk</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-red-700 dark:text-red-400">{stockoutCount}</p>
            <p className="text-xs text-red-600 dark:text-red-500 mt-0.5">SKU–store pairs</p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/20">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm text-amber-700 dark:text-amber-400">
              Overstock Risk
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-amber-700 dark:text-amber-400">
              {overstockCount}
            </p>
            <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">SKU–store pairs</p>
          </CardContent>
        </Card>
        <Card className="border-purple-200 bg-purple-50 dark:bg-purple-950/20">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm text-purple-700 dark:text-purple-400">
              Both Risks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-purple-700 dark:text-purple-400">{bothCount}</p>
            <p className="text-xs text-purple-600 dark:text-purple-500 mt-0.5">SKU–store pairs</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-3 flex-wrap">
        <Select
          value={region}
          onValueChange={(v) => {
            setRegion(v);
            setStore('all');
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

        <Select value={store} onValueChange={setStore}>
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

        <Select value={category} onValueChange={setCategory}>
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

        <Select value={riskType} onValueChange={setRiskType}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="All risk types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All risk types</SelectItem>
            <SelectItem value="Stockout">Stockout</SelectItem>
            <SelectItem value="Overstock">Overstock</SelectItem>
            <SelectItem value="Both">Both</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              {['Store', 'Region', 'SKU', 'Product', 'Category', 'Risk', 'Forecast', 'Avg (12w)', 'Δ Demand'].map(
                (h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-muted-foreground">
                  No at-risk pairs match the current filters
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <tr
                  key={`${r.store_name}-${r.sku}`}
                  className="border-t hover:bg-muted/30 transition-colors"
                >
                  <td className="px-3 py-1.5 font-medium">{r.store_name}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{r.region}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.sku}</td>
                  <td className="px-3 py-1.5">{r.product_name}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{r.category}</td>
                  <td className="px-3 py-1.5">{riskBadge(r.risk_type)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{r.predicted_demand}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                    {Number(r.avg_demand_last_12w).toFixed(1)}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right tabular-nums font-medium ${
                      Number(r.demand_delta) > 0 ? 'text-red-600' : 'text-amber-600'
                    }`}
                  >
                    {Number(r.demand_delta) > 0 ? '+' : ''}
                    {Number(r.demand_delta).toFixed(0)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
