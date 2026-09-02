import { createApp, analytics, genie, lakebase, server } from '@databricks/appkit';

createApp({
  plugins: [
    analytics(),
    genie(),
    server(),
    // Provide fallback pool config so the plugin initialises without
    // throwing when PGHOST/PGDATABASE/LAKEBASE_ENDPOINT are absent
    // (local smoke tests, CI without a live Lakebase).  Actual
    // query failures are caught in onPluginsReady and in the route
    // handlers below.
    lakebase({
      pool: {
        host: process.env.PGHOST ?? 'localhost',
        database: process.env.PGDATABASE ?? 'databricks_postgres',
        endpoint:
          process.env.LAKEBASE_ENDPOINT ??
          'projects/dummy/branches/dummy/endpoints/dummy',
      },
    }),
  ],
  async onPluginsReady(appkit) {
    // Startup migration — SP owns the `app` schema and the write-back table.
    // Wrapped in try/catch so the server still starts when Lakebase is not
    // reachable (e.g. during local typecheck / smoke tests without a DB).
    try {
      await appkit.lakebase.query(`CREATE SCHEMA IF NOT EXISTS app`);
      await appkit.lakebase.query(`
        CREATE TABLE IF NOT EXISTS app.action_status (
          action_id  text        PRIMARY KEY,
          sku        text,
          store_id   text,
          week       date,
          status     text,
          note       text,
          updated_by text,
          updated_at timestamptz DEFAULT now()
        )
      `);
      console.log('[lakebase] migration complete');
    } catch (err) {
      console.warn(
        '[lakebase] migration skipped (Lakebase not reachable):',
        err instanceof Error ? err.message : err,
      );
    }

    // Custom API routes backed by Lakebase
    appkit.server.extend((app) => {
      // GET /api/actions — join forecast_action_list with action_status
      app.get('/api/actions', async (_req, res) => {
        try {
          const result = await appkit.lakebase.query(`
            SELECT
              f.sku,
              f.store_id,
              f.week,
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
            LIMIT 500
          `);
          res.json(result.rows);
        } catch (err) {
          console.error('[lakebase] GET /api/actions error', err);
          res.status(500).json({ error: 'Failed to fetch actions' });
        }
      });

      // POST /api/actions/status — upsert a status update into app.action_status
      app.post('/api/actions/status', async (req, res) => {
        const { sku, store_id, week, status, note } = req.body as {
          sku: string;
          store_id: string;
          week: string;
          status: string;
          note?: string;
        };

        if (!sku || !store_id || !week || !status) {
          res.status(400).json({ error: 'Missing required fields: sku, store_id, week, status' });
          return;
        }

        const action_id = `${sku}::${store_id}::${week}`;
        const updated_by =
          (req.headers['x-forwarded-email'] as string | undefined) ?? 'unknown';

        try {
          await appkit.lakebase.query(
            `INSERT INTO app.action_status
               (action_id, sku, store_id, week, status, note, updated_by, updated_at)
             VALUES ($1, $2, $3, $4::date, $5, $6, $7, now())
             ON CONFLICT (action_id) DO UPDATE SET
               status     = EXCLUDED.status,
               note       = EXCLUDED.note,
               updated_by = EXCLUDED.updated_by,
               updated_at = now()`,
            [action_id, sku, store_id, week, status, note ?? null, updated_by],
          );
          res.json({ ok: true });
        } catch (err) {
          console.error('[lakebase] POST /api/actions/status error', err);
          res.status(500).json({ error: 'Failed to update status' });
        }
      });
    });
  },
}).catch(console.error);
