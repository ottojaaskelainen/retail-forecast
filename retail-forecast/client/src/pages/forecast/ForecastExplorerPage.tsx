import {
  useAnalyticsQuery,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ChartContainer,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const chartConfig = {
  actual_demand: { label: 'Actual Demand', color: '#2272B4' },
  predicted_demand: { label: 'Forecast', color: '#FF7054' },
  avg_demand_last_12w: { label: '12w Avg', color: '#6B7280' },
};

export function ForecastExplorerPage() {
  const [region, setRegion] = useState('all');
  const [store, setStore] = useState('');
  const [category, setCategory] = useState('all');
  const [sku, setSku] = useState('');

  // Small query — only at-risk distinct store+sku combinations for dropdowns
  const { data: options, loading: optionsLoading } = useAnalyticsQuery(
    'forecast_explorer_options',
    {},
  );

  // Parameterized query — memoized so the hook only re-fires when store/sku actually change
  const forecastParams = useMemo(
    () => ({
      store_name: sql.string(store || '__none__'),
      sku: sql.string(sku || '__none__'),
    }),
    [store, sku],
  );
  const { data: trendData, loading: trendLoading } = useAnalyticsQuery(
    'forecast_explorer',
    forecastParams,
  );

  const opts = options ?? [];

  const regions = useMemo(
    () => ['all', ...Array.from(new Set(opts.map((r) => r.region))).sort()],
    [opts],
  );
  const stores = useMemo(() => {
    const filtered = region === 'all' ? opts : opts.filter((r) => r.region === region);
    return Array.from(new Set(filtered.map((r) => r.store_name))).sort();
  }, [opts, region]);
  const categories = useMemo(() => {
    const filtered = store ? opts.filter((r) => r.store_name === store) : opts;
    return ['all', ...Array.from(new Set(filtered.map((r) => r.category))).sort()];
  }, [opts, store]);
  const skus = useMemo(() => {
    return opts
      .filter(
        (r) =>
          r.store_name === store && (category === 'all' || r.category === category),
      )
      .sort((a, b) => a.product_name.localeCompare(b.product_name));
  }, [opts, store, category]);

  const selectedProduct = opts.find((r) => r.store_name === store && r.sku === sku);

  const chartData = useMemo(
    () =>
      (trendData ?? []).map((r) => ({
        week: String(r.week).slice(0, 10),
        actual_demand: r.actual_demand != null ? Number(r.actual_demand) : null,
        predicted_demand: r.predicted_demand != null ? Number(r.predicted_demand) : null,
        avg_demand_last_12w: r.avg_demand_last_12w != null ? Number(r.avg_demand_last_12w) : null,
        is_stockout_risk: r.is_stockout_risk,
        is_overstock_risk: r.is_overstock_risk,
      })),
    [trendData],
  );

  const forecastRow = chartData.find((r) => r.predicted_demand != null);
  const forecastWeek = forecastRow?.week ?? null;
  const avgDemand =
    forecastRow?.avg_demand_last_12w != null ? Number(forecastRow.avg_demand_last_12w) : null;

  if (optionsLoading)
    return (
      <div className="p-8 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Forecast Explorer</h1>
        <p className="text-sm text-muted-foreground mt-1">
          12-week demand history + forecast for at-risk products
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select
          value={region}
          onValueChange={(v) => {
            setRegion(v);
            setStore('');
            setSku('');
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

        <Select
          value={store}
          onValueChange={(v) => {
            setStore(v);
            setSku('');
          }}
        >
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Select store" />
          </SelectTrigger>
          <SelectContent>
            {stores.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={category}
          onValueChange={(v) => {
            setCategory(v);
            setSku('');
          }}
        >
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

        <Select value={sku} onValueChange={setSku} disabled={!store}>
          <SelectTrigger className="w-64">
            <SelectValue placeholder={!store ? 'Select a store first' : 'Select product'} />
          </SelectTrigger>
          <SelectContent>
            {skus.map((s) => (
              <SelectItem key={s.sku} value={s.sku}>
                {s.product_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {!store || !sku ? (
        <div className="flex items-center justify-center h-64 border rounded-lg bg-muted/30">
          <p className="text-muted-foreground">
            Select a store and product to see the demand trend
          </p>
        </div>
      ) : trendLoading ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <>
          {forecastRow && (
            <div className="flex gap-3 flex-wrap">
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  forecastRow.is_stockout_risk
                    ? 'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400'
                    : 'bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-400'
                }`}
              >
                {forecastRow.is_stockout_risk ? '⚠ Stockout risk' : '✓ No stockout risk'}
              </span>
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  forecastRow.is_overstock_risk
                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400'
                    : 'bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-400'
                }`}
              >
                {forecastRow.is_overstock_risk ? '⚠ Overstock risk' : '✓ No overstock risk'}
              </span>
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>
                {selectedProduct?.product_name ?? sku} @ {store}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ChartContainer config={chartConfig} className="h-72 w-full">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  {forecastWeek && (
                    <ReferenceLine
                      x={forecastWeek}
                      stroke="#94a3b8"
                      strokeDasharray="4 4"
                      label={{
                        value: 'Forecast →',
                        position: 'top',
                        fontSize: 11,
                        fill: '#94a3b8',
                      }}
                    />
                  )}
                  {avgDemand != null && (
                    <ReferenceLine
                      y={avgDemand}
                      stroke="#6B7280"
                      strokeDasharray="6 3"
                      label={{
                        value: `12w avg: ${avgDemand.toFixed(0)}`,
                        position: 'insideTopRight',
                        fontSize: 11,
                        fill: '#6B7280',
                      }}
                    />
                  )}
                  <Line
                    type="monotone"
                    dataKey="actual_demand"
                    stroke="var(--color-actual_demand)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls={false}
                    name="Actual Demand"
                  />
                  <Line
                    type="monotone"
                    dataKey="predicted_demand"
                    stroke="var(--color-predicted_demand)"
                    strokeWidth={2}
                    strokeDasharray="6 3"
                    dot={{ r: 5 }}
                    connectNulls={false}
                    name="Forecast"
                  />
                </LineChart>
              </ChartContainer>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
