# Lakebase Serving + Feature Store + Execution Evidence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the retail-forecast journey end-to-end to a fresh workspace, add Lakebase operational serving (synced action list + write-back) and a Unity Catalog Feature Store, and commit text execution evidence for every stage.

**Architecture:** One Databricks Asset Bundle deploys the whole journey — Unity Catalog (catalog/schemas/volumes), a serverless SQL warehouse, the Lakeflow SDP pipeline + orchestration job, the Lakebase Autoscaling project/catalog/synced-table, Genie, dashboard, and the AppKit app. ML training is refactored to UC Feature Engineering (point-in-time FeatureLookup → `fe.log_model` → `fe.score_batch`). The app reads the synced action list and writes back action status through the AppKit `lakebase` plugin. Every deploy/run/query output is captured as text under `/evidence/`.

**Tech Stack:** Databricks CLI v1.14.1, DABs, Lakeflow SDP (PySpark), MLflow + `databricks-feature-engineering>=0.16.0`, Lakebase Autoscaling (Postgres 17), AppKit 0.38.1 (Node/TypeScript/React), Genie, Lakeview.

**Spec:** `docs/superpowers/specs/2026-09-02-lakebase-and-evidence-design.md`

## Global Constraints

- **Workspace/profile:** all CLI uses `--profile otto-sandbox` → `https://adb-7405605253712899.19.azuredatabricks.net`. Never omit `--profile`.
- **Catalog:** `retail_forecast` (bundle-created). No hardcoded `gdai_test_dev` or `otto_demo` anywhere after Task 0.
- **Feature Store:** `databricks-feature-engineering>=0.16.0`, `mlflow>=2.22.0`. Use `timeseries_column` (singular). Use `fe.log_model(training_set=...)` (NOT `mlflow.log_model`) and `fe.score_batch` (keys-only df).
- **Lakebase:** Autoscaling only. Bundle resources `postgres_projects` / `postgres_catalogs` / `postgres_synced_tables` (Beta) — NEVER `synced_database_tables` (legacy Provisioned, fails). Synced tables are read-only in Postgres; write-back is a separate native table owned by the app SP.
- **Deploy ordering:** two-phase includes in `databricks.yml`. Phase 1 = catalog, warehouse, pipeline, job, postgres_project, postgres_catalog. Phase 2 (enabled only after the job run produces gold) = postgres_synced_tables, genie, dashboard, app.
- **App SP schema ownership:** deploy the app BEFORE any local run so its Service Principal creates and owns its schema (avoids `permission denied … 42501`).
- **Evidence:** every task that runs something writes real captured stdout/JSON/query results into `/evidence/<NN_stage>/`. No screenshots. Commit evidence with the task that produced it.
- **Commits:** frequent, one per task minimum. Branch: `lakebase-and-evidence` (already checked out).

---

### Task 0: Config reconciliation + bundle validate

Reconcile the bundle to the new workspace/catalog, add the SQL warehouse resource, add the `feature` schema, de-hardcode the catalog, and split includes into two phases. No deploy yet — this task ends when `bundle validate` passes.

**Files:**
- Modify: `databricks.yml`
- Modify: `resources/catalog.yml`
- Create: `resources/warehouse.yml`
- Create: `resources/lakebase.yml` (phase-1 project + catalog; synced table added in Task 4)
- Modify: `resources/genie.yml`, `resources/dashboard.yml`, `resources/app.yml` (warehouse id reference)
- Modify: `retail-forecast/config/queries/risk_dashboard.sql`, `forecast_explorer.sql`, `forecast_explorer_options.sql` (catalog)
- Modify: `training/train_forecast_model.py` (widget default only; full refactor in Task 1)

**Interfaces:**
- Produces: `var.catalog = "retail_forecast"`; `resources.sql_warehouses.retail_forecast_wh` (id referenced as `${resources.sql_warehouses.retail_forecast_wh.id}`); `resources.postgres_projects.retail_forecast_lb`; `resources.postgres_catalogs.retail_forecast_lbcat`; schema `retail_forecast.feature`.

- [ ] **Step 1: Point the bundle at the new workspace and catalog, split includes into two phases**

Edit `databricks.yml`:
- `workspace.host: https://adb-7405605253712899.19.azuredatabricks.net`
- `var.catalog.default: "retail_forecast"`
- Remove the `warehouse_id` variable (replaced by the `sql_warehouses` resource reference).
- Includes:

```yaml
include:
  # Phase 1 — no dependency on gold data
  - resources/catalog.yml
  - resources/warehouse.yml
  - resources/pipeline.yml
  - resources/job.yml
  - resources/lakebase.yml
  # Phase 2 — enable AFTER the job run has produced gold tables + forecast_action_list:
  ##- resources/synced_table.yml
  ##- resources/genie.yml
  ##- resources/dashboard.yml
  ##- resources/app.yml
```

- [ ] **Step 2: Add the serverless SQL warehouse resource**

Create `resources/warehouse.yml`:

```yaml
resources:
  sql_warehouses:
    retail_forecast_wh:
      name: retail-forecast-wh
      cluster_size: "2X-Small"
      enable_serverless_compute: true
      warehouse_type: PRO
      auto_stop_mins: 10
      max_num_clusters: 1
```

- [ ] **Step 3: Add the `feature` schema**

In `resources/catalog.yml`, add under `schemas:` (same shape as the existing schema blocks):

```yaml
    feature_schema:
      catalog_name: ${resources.catalogs.main_catalog.name}
      name: feature
      comment: "Feature Store — UC feature tables for demand forecasting"
```

- [ ] **Step 4: Add the phase-1 Lakebase project + UC catalog registration**

Create `resources/lakebase.yml`:

```yaml
resources:
  postgres_projects:
    retail_forecast_lb:
      project_id: retail-forecast-lb
      display_name: "Retail Forecast Lakebase"
      pg_version: 17
  postgres_catalogs:
    retail_forecast_lbcat:
      catalog_id: retail_forecast_lb
      branch: ${resources.postgres_projects.retail_forecast_lb.default_branch}
      postgres_database: databricks_postgres
      create_database_if_missing: true
```

(The project auto-creates a `production` branch + `primary` endpoint. `postgres_catalogs` registers the Postgres DB as a UC catalog named `retail_forecast_lb`, required before the synced table in Task 4.)

- [ ] **Step 5: Reference the warehouse resource id from genie/dashboard/app**

In `resources/genie.yml`, `resources/dashboard.yml`, `resources/app.yml`, replace `${var.warehouse_id}` with `${resources.sql_warehouses.retail_forecast_wh.id}`.

- [ ] **Step 6: De-hardcode the catalog in app SQL queries**

In `retail-forecast/config/queries/risk_dashboard.sql`, `forecast_explorer.sql`, `forecast_explorer_options.sql`: replace every `gdai_test_dev.` with `retail_forecast.`. (`action_list.sql` is replaced entirely by Lakebase in Task 5 — leave it for now.)

- [ ] **Step 7: Fix the training notebook widget default**

In `training/train_forecast_model.py` line ~19: `dbutils.widgets.text("catalog", "retail_forecast")`. (Full Feature Store refactor is Task 1.)

- [ ] **Step 8: Validate**

Run: `databricks bundle validate --profile otto-sandbox`
Expected: exits 0, no errors, resource tree lists the catalog, warehouse, pipeline, job, postgres_project, postgres_catalog.

- [ ] **Step 9: Commit**

```bash
git add databricks.yml resources/ retail-forecast/config/queries/ training/train_forecast_model.py
git commit -m "Reconcile bundle to new workspace; add warehouse + feature schema + phase-1 Lakebase resources"
```

---

### Task 1: Feature Store refactor of the training notebook

Refactor `training/train_forecast_model.py` to write a UC feature table, train via point-in-time `FeatureLookup`, register with `fe.log_model`, score with `fe.score_batch`, and additionally materialize `gold.forecast_action_list` (the synced-table source). Reuse the existing Spark feature-engineering transforms — only the persistence/train/score wiring changes.

**Files:**
- Modify: `training/train_forecast_model.py`

**Interfaces:**
- Produces (UC objects created at run time in Task 3): `retail_forecast.feature.weekly_demand_features` (PK `sku,store_id,week`; `timeseries_column="week"`), registered model `retail_forecast.gold.retail_forecast_rf@prod`, `retail_forecast.gold.forecast_demand`, `retail_forecast.gold.forecast_action_list`.

- [ ] **Step 1: Update the install/imports cell**

Replace the pip line with:

```python
%pip install "mlflow>=2.22.0" "databricks-feature-engineering>=0.16.0" scikit-learn
dbutils.library.restartPython()
```

Add to imports: `from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup`.
Set constants: `FEATURE_SCHEMA = "feature"`, `FEATURE_TABLE = f"{CATALOG}.{FEATURE_SCHEMA}.weekly_demand_features"`.
Add `fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")`.

- [ ] **Step 2: Keep the existing Spark feature engineering, ending in a per-(sku,store,week) feature DataFrame**

Retain the current Spark logic (weekly aggregation, `valid_pairs` history filter, `add_promo_features`, `rolling_4wk_avg`, `week_of_year`). Add an `avg_demand_last_12w` rolling column (12-week trailing mean, matching the scoring feature). Produce `features_df` with exactly: `sku, store_id, week, week_of_year, is_promoted, discount_pct_feat, rolling_4wk_avg, avg_demand_last_12w`. Keep a separate `labels_df` with `sku, store_id, week, total_quantity`.

- [ ] **Step 3: Create + write the feature table**

```python
from databricks.sdk.runtime import spark
try:
    fe.create_table(
        name=FEATURE_TABLE,
        primary_keys=["sku", "store_id", "week"],
        timeseries_column="week",          # singular — canonical in >=0.16.0
        schema=features_df.schema,
        description="Weekly per-SKU/store demand features (point-in-time)",
    )
except Exception as e:
    if "already exists" not in str(e).lower():
        raise
fe.write_table(name=FEATURE_TABLE, df=features_df, mode="merge")
print("feature rows:", spark.table(FEATURE_TABLE).count())
```

- [ ] **Step 4: Build the point-in-time training set**

```python
all_weeks = [r.week for r in labels_df.select("week").distinct().orderBy("week").collect()]
cutoff = all_weeks[-8]                       # hold out last 8 weeks
train_labels = labels_df.filter(F.col("week") < cutoff)
test_labels  = labels_df.filter(F.col("week") >= cutoff)

lookups = [FeatureLookup(
    table_name=FEATURE_TABLE,
    lookup_key=["sku", "store_id"],
    timestamp_lookup_key="week",             # point-in-time: feature.week <= label.week
)]
training_set = fe.create_training_set(
    df=train_labels, feature_lookups=lookups,
    label="total_quantity", exclude_columns=["week", "sku", "store_id"],
)
train_pd = training_set.load_df().toPandas()
X_train, y_train = train_pd[FEATURES], train_pd[TARGET]
```

(`FEATURES` unchanged from the current file: `["week_of_year", "is_promoted", "discount_pct_feat", "rolling_4wk_avg"]`; `TARGET="total_quantity"`.)

- [ ] **Step 5: Train, compute holdout MAE, and register with `fe.log_model`**

```python
mlflow.set_experiment(f"/Users/{_current_user}/retail_forecast_demand")
with mlflow.start_run() as run:
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    test_set = fe.create_training_set(df=test_labels, feature_lookups=lookups,
                                      label="total_quantity", exclude_columns=["week","sku","store_id"])
    test_pd = test_set.load_df().toPandas()
    mae = mean_absolute_error(test_pd[TARGET], model.predict(test_pd[FEATURES]))
    mlflow.log_metric("mae_holdout", mae)
    print(f"MAE holdout: {mae:.2f}")

    fe.log_model(model=model, artifact_path="model", flavor=mlflow.sklearn,
                 training_set=training_set, registered_model_name=MODEL_NAME)

client = MlflowClient(registry_uri="databricks-uc")
latest = max(client.search_model_versions(f"name='{MODEL_NAME}'"), key=lambda v: int(v.version)).version
client.set_registered_model_alias(MODEL_NAME, "prod", latest)
print(f"Registered {MODEL_NAME} v{latest} @prod")
```

(`MODEL_NAME = f"{CATALOG}.gold.retail_forecast_rf"`.)

- [ ] **Step 6: Score the next 8 weeks with `fe.score_batch` (keys-only df) and write `forecast_demand`**

Build `score_keys` with columns `sku, store_id, week` for the 8 forecast weeks (reuse the existing `forecast_weeks` logic). The feature table must contain rows at those weeks for point-in-time lookup — extend `features_df` to also emit forward-dated feature rows for the forecast weeks (carry `avg_demand_last_12w` / `rolling_4wk_avg` from the last known week; recompute `week_of_year`, and promo features via the existing `add_promo_features` on future promos) and write them to the feature table in Step 3. Then:

```python
scored = fe.score_batch(model_uri=f"models:/{MODEL_NAME}@prod",
                        df=score_keys, result_type="double")   # column: "prediction"
scored = (scored.withColumnRenamed("prediction", "predicted_demand_raw")
    .withColumn("predicted_demand", F.greatest(F.lit(0), F.round("predicted_demand_raw")).cast("int")))
# join avg_demand_last_12w from feature table for risk flags
feat = spark.table(FEATURE_TABLE).select("sku","store_id","week","avg_demand_last_12w")
out = (scored.join(feat, ["sku","store_id","week"])
    .withColumn("is_stockout_risk", (F.col("predicted_demand") > F.col("avg_demand_last_12w")*1.3) & (F.col("avg_demand_last_12w")>0))
    .withColumn("is_overstock_risk", (F.col("predicted_demand") < F.col("avg_demand_last_12w")*0.7) & (F.col("avg_demand_last_12w")>0))
    .withColumn("model_version", F.lit(f"rf_v{latest}"))
    .select("sku","store_id","week","predicted_demand","avg_demand_last_12w","is_stockout_risk","is_overstock_risk","model_version"))
out.write.mode("overwrite").option("overwriteSchema","true").saveAsTable(f"{CATALOG}.gold.forecast_demand")
print("forecast_demand rows:", out.count())
```

- [ ] **Step 7: Materialize `gold.forecast_action_list` (synced-table source) and exit with a structured result**

Materialize the `action_list.sql` logic as a gold table keyed by `sku, store_id, week` (current-week at-risk rows joined to `dim_store`/`dim_product`), so it's an existing UC table for the Task-4 synced table. Column names must be Postgres-friendly (`[A-Za-z0-9_]+`). End the notebook:

```python
import json
dbutils.notebook.exit(json.dumps({"mae_holdout": float(mae), "model_version": int(latest),
    "forecast_rows": out.count(), "action_rows": spark.table(f"{CATALOG}.gold.forecast_action_list").count()}))
```

- [ ] **Step 8: Static check + commit** (run happens in Task 3)

Run: `python -c "import ast; ast.parse(open('training/train_forecast_model.py').read()); print('parse ok')"`
Expected: `parse ok`.

```bash
git add training/train_forecast_model.py
git commit -m "Refactor training to UC Feature Store (point-in-time FeatureLookup) + forecast_action_list"
```

---

### Task 2: Deploy phase 1 + verify Lakebase project

**Files:** none (deploy). Create: `evidence/00_deploy/`, `evidence/README.md` (stub).

**Interfaces:** Consumes Task 0/1 config. Produces: deployed catalog/schemas/volumes/warehouse/pipeline/job and a READY Lakebase project + `primary` endpoint whose resource paths later tasks need.

- [ ] **Step 1: Deploy**

Run: `databricks bundle deploy --profile otto-sandbox 2>&1 | tee evidence/00_deploy/phase1_deploy.txt`
Expected: `Deployment complete!`, no errors.

- [ ] **Step 2: Capture the deployed resource tree**

Run: `databricks bundle summary --profile otto-sandbox 2>&1 | tee evidence/00_deploy/phase1_summary.txt`

- [ ] **Step 3: Verify + capture the Lakebase project/branch/endpoint**

```bash
databricks postgres list-projects --profile otto-sandbox -o json | tee evidence/06_lakebase/project.json
PROJ=$(databricks postgres list-projects --profile otto-sandbox -o json | python3 -c "import json,sys;print([p['name'] for p in json.load(sys.stdin) if 'retail-forecast-lb' in p['name']][0])")
databricks postgres list-branches "$PROJ" --profile otto-sandbox -o json | tee evidence/06_lakebase/branches.json
```
Expected: project `state`/`status` READY (poll if provisioning); a `production` branch and `primary` endpoint present. Record `$PROJ`, branch path, endpoint path for later tasks.

- [ ] **Step 4: Commit**

```bash
git add evidence/00_deploy/ evidence/06_lakebase/project.json evidence/06_lakebase/branches.json evidence/README.md
git commit -m "Deploy phase 1; capture deploy + Lakebase project evidence"
```

---

### Task 3: Run the end-to-end job; capture ingest / pipeline / UC / feature / ML evidence

**Files:** Create: `evidence/01_ingest/`, `evidence/02_pipeline/`, `evidence/03_uc_governance/`, `evidence/04_feature_store/`, `evidence/05_ml/`.

**Interfaces:** Consumes the deployed job. Produces gold tables, feature table, registered model, `forecast_demand`, `forecast_action_list` — the inputs Task 4/5 depend on.

- [ ] **Step 1: Trigger the job and capture the run**

```bash
databricks bundle run retail_forecast_job --profile otto-sandbox 2>&1 | tee evidence/02_pipeline/job_run.txt
```
Expected: all tasks (generate_pos_data, generate_promo_data, run_pipeline, apply_uc_tags, train_model) SUCCESS. If it blocks, poll `databricks jobs get-run <id>` until terminal and confirm `result_state=SUCCESS`.

- [ ] **Step 2: Capture the training task's structured output (ML metrics)**

Get the `train_model` task run id from the run, then:
```bash
databricks jobs get-run-output <TASK_RUN_ID> --profile otto-sandbox | python3 -c "import json,sys;print(json.load(sys.stdin)['notebook_output']['result'])" | tee evidence/05_ml/train_result.json
```
Expected: JSON with `mae_holdout`, `model_version`, `forecast_rows`, `action_rows`.

- [ ] **Step 3: Capture ingest evidence (volumes + bronze counts)**

Use `databricks api post /api/2.0/sql/statements` (or the statement-execution CLI) against the warehouse to run and save results:
- `SELECT COUNT(*) FROM retail_forecast.bronze.bronze_transactions;` (+ promotions/stores/products) → `evidence/01_ingest/bronze_counts.txt`
- `databricks fs ls dbfs:/Volumes/retail_forecast/landing/raw_pos_data --profile otto-sandbox` → `evidence/01_ingest/volume_listing.txt`

- [ ] **Step 4: Capture pipeline evidence (silver/gold counts + sample rows)**

Run and save (one file per query under `evidence/02_pipeline/`):
- Row counts for `silver.*` and `gold.dim_store/dim_product/dim_date/fact_transactions/fact_promotions`.
- `SELECT * FROM retail_forecast.gold.fact_transactions LIMIT 10;` → `gold_fact_sample.txt`.

- [ ] **Step 5: Capture UC governance evidence**

- Catalog tree: `databricks catalogs get retail_forecast`, `databricks schemas list retail_forecast`, `databricks tables list retail_forecast gold` → `evidence/03_uc_governance/catalog_tree.txt`
- Applied tags: query `system.information_schema.table_tags`/`column_tags` filtered to `retail_forecast` → `tags.txt`
- Lineage: `SELECT * FROM system.access.table_lineage WHERE target_table_catalog='retail_forecast' LIMIT 20;` → `lineage.txt`
- Grants: `databricks grants get catalog retail_forecast` → `grants.txt`

- [ ] **Step 6: Capture Feature Store evidence**

- `SELECT COUNT(*) FROM retail_forecast.feature.weekly_demand_features;` + `LIMIT 10` sample → `evidence/04_feature_store/feature_table_sample.txt`
- `databricks tables get retail_forecast.feature.weekly_demand_features` (shows PK + timeseries metadata) → `feature_table_meta.txt`

- [ ] **Step 7: Capture ML evidence**

- `databricks registered-models get retail_forecast.gold.retail_forecast_rf` and `... aliases` → `evidence/05_ml/registered_model.txt`
- `SELECT COUNT(*), SUM(CAST(is_stockout_risk AS INT)) FROM retail_forecast.gold.forecast_demand;` + `LIMIT 10` sample → `forecast_demand_sample.txt`

- [ ] **Step 8: Commit**

```bash
git add evidence/
git commit -m "Run end-to-end job; capture ingest/pipeline/UC/feature-store/ML evidence"
```

---

### Task 4: Add + deploy the Lakebase synced table; capture Postgres read evidence

**Files:** Create: `resources/synced_table.yml`. Modify: `databricks.yml` (enable the phase-2 include for the synced table).

**Interfaces:** Consumes `gold.forecast_action_list` (Task 3) + `postgres_catalogs` (Task 2). Produces a Postgres-queryable synced table `retail_forecast_lb.public.forecast_action_list`.

- [ ] **Step 1: Define the synced table resource**

Create `resources/synced_table.yml`:

```yaml
resources:
  postgres_synced_tables:
    forecast_action_list_sync:
      synced_table_id: forecast_action_list
      source_table_full_name: ${var.catalog}.gold.forecast_action_list
      primary_key_columns: ["sku", "store_id", "week"]
      scheduling_policy: SNAPSHOT
      branch: ${resources.postgres_projects.retail_forecast_lb.default_branch}
      postgres_database: databricks_postgres
      create_database_objects_if_missing: true
      new_pipeline_spec:
        storage_catalog: ${var.catalog}
        storage_schema: gold
```

- [ ] **Step 2: Enable the phase-2 include and deploy**

In `databricks.yml`, uncomment `- resources/synced_table.yml`. Then:
```bash
databricks bundle deploy --profile otto-sandbox 2>&1 | tee evidence/06_lakebase/synced_table_deploy.txt
```
Expected: deploy succeeds; a sync pipeline is created.

- [ ] **Step 3: Verify sync status**

```bash
databricks postgres get-synced-table "synced_tables/retail_forecast_lb.public.forecast_action_list" --profile otto-sandbox -o json | tee evidence/06_lakebase/synced_table_status.json
```
Expected: state progresses to a synced/online state (poll if provisioning).

- [ ] **Step 4: Query the synced table from Postgres and capture rows**

Using the scriptable psql recipe (host from `get-endpoint`, token from `generate-database-credential` on the `primary` endpoint path):
```bash
PGPASSWORD="$TOKEN" psql "host=$HOST user=$USER dbname=databricks_postgres sslmode=require" \
  -c "SELECT sku, store_name, region, predicted_demand, risk_type FROM public.forecast_action_list LIMIT 10;" \
  2>&1 | tee evidence/06_lakebase/synced_select.txt
```
Expected: rows returned from Postgres (proves gold → Lakebase serving).

- [ ] **Step 5: Commit**

```bash
git add resources/synced_table.yml databricks.yml evidence/06_lakebase/
git commit -m "Add + deploy Lakebase synced action-list table; capture Postgres read evidence"
```

---

### Task 5: App — Lakebase plugin, write-back schema, Action List page

Wire the AppKit `lakebase` plugin, attach the `postgres` resource, create the `action_status` write-back table on server startup (SP-owned), and rewrite the Action List page to read the synced list joined to status and to POST status updates.

**Files:**
- Modify: `retail-forecast/appkit.plugins.json` (enable `lakebase`)
- Modify: `retail-forecast/server/server.ts` (add `lakebase()`; add startup migration + action-status routes)
- Modify: `resources/app.yml` (add `postgres` resource + `lakebase` scope)
- Create: `retail-forecast/config/queries/action_list_pg.sql` (Postgres read query)
- Modify: `retail-forecast/client/src/pages/actions/ActionListPage.tsx` (read + write-back UI)
- Reference: read `retail-forecast/node_modules/@databricks/appkit/CLAUDE.md` and `.../appkit-ui/CLAUDE.md` for the exact `lakebase` plugin query/route API before writing server/client code.

**Interfaces:**
- Produces Postgres table `app.action_status(action_id text primary key, sku text, store_id text, week date, status text, note text, updated_by text, updated_at timestamptz default now())`, owned by the app SP.
- Read query joins `public.forecast_action_list` LEFT JOIN `app.action_status` on `(sku, store_id, week)`.
- HTTP: `POST /api/actions/status` `{sku, store_id, week, status, note}` → upsert into `app.action_status`.

- [ ] **Step 1: Enable the lakebase plugin**

In `appkit.plugins.json`, ensure `lakebase` is in the enabled set (the manifest already declares it). Run `npm run sync` in `retail-forecast/` to regenerate plugin wiring.

- [ ] **Step 2: Attach the postgres resource to the app**

In `resources/app.yml`, add to `user_api_scopes` and `resources`:

```yaml
      user_api_scopes:
        - genie
        - dashboards.genie
        - sql
        - postgres
      resources:
        - name: postgres
          postgres:
            branch: ${resources.postgres_projects.retail_forecast_lb.default_branch}
            database: ${resources.postgres_databases... }   # full DB resource path; if not modeled, use the branch's databricks_postgres DB path from `databricks postgres list-databases`
            permission: CAN_CONNECT_AND_CREATE
```

(If the DB resource path isn't available as a bundle reference, capture it from `databricks postgres list-databases <BRANCH>` and inline the full `projects/.../databases/...` path.)

- [ ] **Step 3: Add lakebase() + startup migration + routes in server.ts**

Add `lakebase` to the `createApp` plugins. On startup, run the `CREATE SCHEMA IF NOT EXISTS app; CREATE TABLE IF NOT EXISTS app.action_status (...)` migration via the lakebase plugin's query API (so the SP owns `app`). Add the `POST /api/actions/status` upsert route and a `GET /api/actions` route running `action_list_pg.sql`. Use the exact plugin API from the appkit CLAUDE.md referenced above.

- [ ] **Step 4: Write the Postgres read query**

Create `config/queries/action_list_pg.sql`:

```sql
SELECT f.sku, f.store_name, f.region, f.product_name, f.category,
       f.predicted_demand, f.avg_demand_last_12w, f.risk_type, f.demand_delta,
       COALESCE(s.status, 'open') AS status, s.note, s.updated_by, s.updated_at
FROM public.forecast_action_list f
LEFT JOIN app.action_status s
  ON s.sku = f.sku AND s.store_id = f.store_id AND s.week = f.week
ORDER BY (f.risk_type = 'Stockout') DESC, ABS(f.demand_delta) DESC
LIMIT 500;
```

- [ ] **Step 5: Update the Action List page**

Rewrite `ActionListPage.tsx` to fetch `GET /api/actions`, render the list with a status badge, and provide a control to set status (acknowledged / reorder_placed / resolved) that POSTs to `/api/actions/status` and refetches. Follow existing page patterns (see `RiskDashboardPage.tsx`).

- [ ] **Step 6: Local verification (typecheck + build + smoke)**

In `retail-forecast/`:
```bash
npm run typecheck && npm run build && npm run test:smoke 2>&1 | tee ../evidence/07_app/local_build.txt
```
Expected: typecheck + build pass; smoke test passes. (Full data flow is verified against deployed Lakebase in Task 6 — do NOT run the app locally against Lakebase before deploy.)

- [ ] **Step 7: Commit**

```bash
git add retail-forecast/ resources/app.yml
git commit -m "App: Lakebase plugin, action_status write-back, Action List page"
```

---

### Task 6: Deploy Genie + dashboard + app; capture app, write-back, and Genie evidence

**Files:** Modify: `databricks.yml` (enable remaining phase-2 includes). Create: `evidence/07_app/`, `evidence/08_genie/`.

**Interfaces:** Consumes everything above. Produces the deployed app + Genie + dashboard and their evidence.

- [ ] **Step 1: Enable remaining phase-2 includes and deploy**

Uncomment `- resources/genie.yml`, `- resources/dashboard.yml`, `- resources/app.yml` in `databricks.yml`, then:
```bash
databricks bundle deploy --profile otto-sandbox 2>&1 | tee evidence/07_app/phase2_deploy.txt
databricks bundle run retail_forecast_app --profile otto-sandbox 2>&1 | tee evidence/07_app/app_start.txt
```
Expected: app deploys and reaches RUNNING; capture the app URL and `service_principal_client_id` from `databricks apps get retail-forecast --profile otto-sandbox`.

- [ ] **Step 2: Capture app API responses (text proof the app serves data)**

`curl` the deployed app's data endpoints (with an OAuth token) and save JSON:
- `GET /api/actions` → `evidence/07_app/api_actions.json`
- the risk-dashboard analytics endpoint → `evidence/07_app/api_risk.json`
Expected: JSON arrays of rows.

- [ ] **Step 3: Capture the Lakebase write-back demo**

After the app deploy created `app.action_status` (SP-owned), connect via psql (superuser) and exercise the write path:
```bash
PGPASSWORD="$TOKEN" psql "host=$HOST user=$USER dbname=databricks_postgres sslmode=require" -c \
"INSERT INTO app.action_status(action_id,sku,store_id,week,status,note,updated_by) \
 VALUES ('demo-1','SKU123','S01', current_date, 'reorder_placed','demo reorder','otto') \
 ON CONFLICT (action_id) DO UPDATE SET status=EXCLUDED.status; \
 SELECT * FROM app.action_status;" 2>&1 | tee evidence/06_lakebase/action_status_writeback.txt
```
Expected: insert succeeds; select shows the row (proves write-back).

- [ ] **Step 4: Capture a Genie natural-language query (question → SQL → rows)**

Use the Genie Conversation API (space id from the deployed `genie_spaces`): ask e.g. *"Which stores have the highest stockout risk next week?"*, poll to completion, and save the returned generated SQL + result rows to `evidence/08_genie/genie_query.json` (and a readable `.md`).
Expected: Genie returns SQL and a result table.

- [ ] **Step 5: Commit**

```bash
git add databricks.yml evidence/
git commit -m "Deploy Genie/dashboard/app; capture app, Lakebase write-back, and Genie evidence"
```

---

### Task 7: Assemble evidence README + final review

**Files:** Modify: `evidence/README.md`. Create: `README.md` update or `evidence/index` mapping (as needed).

- [ ] **Step 1: Write `evidence/README.md` mapping each assignment stage → its proof file**

Table: stage (Lakeflow / Unity Catalog / Lakebase / ML+Feature Store / Genie / App) → evidence file(s) → one-line description of what the output proves. Include the workspace + catalog + run identifiers.

- [ ] **Step 2: Verify every evidence file contains real captured output (not empty, not a placeholder)**

Run: `find evidence -type f -size -1c` → expect no output (no empty files). Skim each file confirms real rows/metrics/status.

- [ ] **Step 3: Update the top-level repo README** with a short "How this maps to the assignment" section pointing at `evidence/` and the spec.

- [ ] **Step 4: Final commit**

```bash
git add evidence/README.md README.md
git commit -m "Add evidence index mapping each journey stage to its execution proof"
```

- [ ] **Step 5: Push reminder**

Before pushing/opening a PR: these changes haven't been reviewed with Isaac Review yet — you can run `/review` (Databricks' recommended code and documentation review pipeline) before or after pushing. Then push the branch and (per the assignment) ensure the repo is readable by the validator (public or GitHub-connected).

---

## Self-Review

**Spec coverage:**
- Lakeflow ingest → Task 3 evidence (bronze counts, volume listing). ✓
- Unity Catalog govern → Task 0 (feature schema), Task 3 (tags/lineage/grants). ✓
- Lakebase serve + write-back → Task 0/2 (project/catalog), Task 4 (synced table + read), Task 5 (plugin + action_status), Task 6 (write-back demo). ✓
- ML + Feature Store → Task 1 (refactor), Task 3 (feature table + model + forecast_demand evidence). ✓
- Genie → Task 6 Step 4. ✓
- App → Task 5 (build), Task 6 (deploy + API evidence). ✓
- Catalog reconciliation + warehouse-via-bundle → Task 0. ✓
- Evidence readable as text, committed → every run task. ✓

**Open items carried into execution (resolve in-task, not placeholders):**
- Exact AppKit `lakebase` plugin query/route API — Task 5 Step references the plugin's own CLAUDE.md as the authoritative source (concrete file, not a guess).
- The app `postgres` resource `database` full path — Task 5 Step 2 says derive from `databricks postgres list-databases` if not expressible as a bundle reference.
- Statement-execution mechanics for SQL evidence capture — use `databricks api post /api/2.0/sql/statements` against the deployed warehouse; consistent across Tasks 3/4.

**Type/name consistency:** catalog `retail_forecast`; Lakebase project id `retail-forecast-lb`, UC catalog `retail_forecast_lb`; feature table `retail_forecast.feature.weekly_demand_features` (PK `sku,store_id,week`, `timeseries_column="week"`); model `retail_forecast.gold.retail_forecast_rf@prod`; gold `forecast_demand` + `forecast_action_list`; synced table `retail_forecast_lb.public.forecast_action_list`; write-back `app.action_status`. Consistent across tasks.
