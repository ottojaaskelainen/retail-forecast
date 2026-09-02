import {
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
import { useCallback, useEffect, useMemo, useState } from 'react';

// ── Types ────────────────────────────────────────────────────────────────────

type ActionRow = {
  sku: string;
  store_id: string;
  week: string;
  store_name: string;
  region: string;
  product_name: string;
  category: string;
  predicted_demand: number;
  avg_demand_last_12w: number;
  risk_type: string;
  demand_delta: number;
  status: string;
  note: string | null;
  updated_by: string | null;
  updated_at: string | null;
};

type ActionStatus = 'open' | 'acknowledged' | 'reorder_placed' | 'resolved';

// ── Data-fetching hook ───────────────────────────────────────────────────────

function useActions() {
  const [data, setData] = useState<ActionRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    setLoading(true);
    fetch('/api/actions')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<ActionRow[]>;
      })
      .then((rows) => {
        setData(rows);
        setError(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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

const statusBadge = (s: string) => {
  switch (s) {
    case 'open':
      return (
        <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          Open
        </span>
      );
    case 'acknowledged':
      return (
        <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400">
          Acknowledged
        </span>
      );
    case 'reorder_placed':
      return (
        <span className="px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-400">
          Reorder Placed
        </span>
      );
    case 'resolved':
      return (
        <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-400">
          Resolved
        </span>
      );
    default:
      return <span className="text-xs text-muted-foreground">{s}</span>;
  }
};

// ── Status-update cell ───────────────────────────────────────────────────────

function StatusCell({
  row,
  onUpdate,
}: {
  row: ActionRow;
  onUpdate: (sku: string, store_id: string, week: string, status: ActionStatus) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      {statusBadge(row.status)}
      <Select
        value={row.status as ActionStatus}
        onValueChange={(v) => onUpdate(row.sku, row.store_id, row.week, v as ActionStatus)}
      >
        <SelectTrigger className="h-6 w-32 text-xs px-2">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="open">Open</SelectItem>
          <SelectItem value="acknowledged">Acknowledged</SelectItem>
          <SelectItem value="reorder_placed">Reorder Placed</SelectItem>
          <SelectItem value="resolved">Resolved</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function ActionListPage() {
  const { data, loading, error, refetch } = useActions();
  const [region, setRegion] = useState('all');
  const [store, setStore] = useState('all');
  const [category, setCategory] = useState('all');
  const [riskType, setRiskType] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [updating, setUpdating] = useState<string | null>(null);

  const rows = data ?? [];

  const regions = useMemo(
    () => ['all', ...Array.from(new Set(rows.map((r) => r.region))).sort()],
    [rows],
  );
  const stores = useMemo(() => {
    const base = region === 'all' ? rows : rows.filter((r) => r.region === region);
    return ['all', ...Array.from(new Set(base.map((r) => r.store_name))).sort()];
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
          (riskType === 'all' || r.risk_type === riskType) &&
          (statusFilter === 'all' || r.status === statusFilter),
      ),
    [rows, region, store, category, riskType, statusFilter],
  );

  const stockoutCount = rows.filter((r) => r.risk_type === 'Stockout').length;
  const overstockCount = rows.filter((r) => r.risk_type === 'Overstock').length;
  const bothCount = rows.filter((r) => r.risk_type === 'Both').length;

  const handleStatusUpdate = useCallback(
    async (sku: string, store_id: string, week: string, status: ActionStatus) => {
      const key = `${sku}::${store_id}::${week}`;
      setUpdating(key);
      try {
        const res = await fetch('/api/actions/status', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sku, store_id, week, status }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { error?: string };
          console.error('Status update failed:', body.error ?? res.status);
        } else {
          await refetch();
        }
      } catch (e) {
        console.error('Status update error', e);
      } finally {
        setUpdating(null);
      }
    },
    [refetch],
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
        <h1 className="text-2xl font-bold text-foreground">Inventory Action List</h1>
        <p className="text-sm text-muted-foreground mt-1">
          At-risk SKU–store pairs · status synced from Lakebase
        </p>
      </div>

      {/* KPI cards */}
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

      {/* Filters */}
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

        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="acknowledged">Acknowledged</SelectItem>
            <SelectItem value="reorder_placed">Reorder Placed</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              {[
                'Store',
                'Region',
                'SKU',
                'Product',
                'Category',
                'Risk',
                'Forecast',
                'Avg (12w)',
                'Δ Demand',
                'Status',
              ].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-3 py-8 text-center text-muted-foreground">
                  No at-risk pairs match the current filters
                </td>
              </tr>
            ) : (
              filtered.map((r) => {
                const rowKey = `${r.sku}::${r.store_id}::${r.week}`;
                const isUpdating = updating === rowKey;
                return (
                  <tr
                    key={`${r.store_name}-${r.sku}`}
                    className={`border-t transition-colors ${
                      isUpdating ? 'opacity-50' : 'hover:bg-muted/30'
                    }`}
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
                    <td className="px-3 py-1.5 min-w-[220px]">
                      <StatusCell
                        row={r}
                        onUpdate={(sku, store_id, week, status) =>
                          void handleStatusUpdate(sku, store_id, week, status)
                        }
                      />
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
