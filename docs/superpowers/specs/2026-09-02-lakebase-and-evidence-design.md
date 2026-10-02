# Design: Lakebase Serving + Feature Store + Execution Evidence

**Date:** 2026-09-02
**Status:** Approved for planning
**Repo:** retail-forecast-poc

> **Current state (updated 2026-10-02).** This is the original point-in-time design; the live build has since moved on. Deltas vs. the text below:
> - **Workspace / profile:** now `adb-7405610530405651.11` via profile `otto-stable` — not `adb-7405605253712899.19` / `otto-sandbox` (that profile's token is retired). Applies to every `otto-sandbox` reference below.
> - **Model:** LightGBM with a Poisson objective, not RandomForest — the lighter artifact removed the earlier `score_batch` OOM concern (§6.1 / step 5 below).
> - **Training layout:** split into `training/build_features.py` → `train_model.py` → `score_forecast.py` (see the MLOps-split plan). The monolithic `train_forecast_model.py` referenced below no longer exists.
> - **Catalog storage:** `storage_root` points at this workspace's external location (`abfss://fevm-default-container@stojsvt6mzuc…/retail_forecast`); Default Storage can't be set from a bundle.
> - **App UC grants:** granted via `uc_securable` app resources in `resources/app.yml` (auto-grants the app's SP + ancestor USE). The Lakebase Postgres `GRANT SELECT` on the synced table stays a manual step.

## 1. Purpose & context

This is an assignment build: a working prototype that solves a specific
customer problem in a specific industry as an **integrated end-to-end data
journey** spanning Lakeflow → Unity Catalog → Lakebase → ML/GenAI → Genie →
Databricks App. We are reusing the existing `retail-forecast-poc` project,
which already covers every stage **except Lakebase**, and which currently
ships as source code with **no committed execution evidence**.

Two gaps must be closed:

1. **Lakebase** — the only missing stage. Add it as the operational-serving
   layer for the store-manager action list, including write-back.
2. **Execution evidence** — the assignment scores the "Build" domain on
   evidence the build actually ran, *readable as text*. Source code alone
   fails. We deploy the whole journey to a real workspace and commit the
   captured text outputs.

A third improvement is folded in at the user's request:

3. **Feature Store** — refactor ML training from inline feature engineering to
   Unity Catalog Feature Engineering (governed feature tables, point-in-time
   FeatureLookup, `fe.log_model` lineage, `fe.score_batch`).

### Customer problem & industry

- **Industry:** Retail (grocery / general merchandise).
- **Problem:** Stockouts and overstocks driven by promotions. Store managers
  cannot see which SKU-store combinations are about to run short (lost sales,
  empty shelves) or pile up (dead stock, wasted working capital) in the coming
  weeks.
- **Solution:** Forecast next-8-weeks demand per SKU-store, flag
  stockout/overstock risk, and surface a **live operational action list** that
  store managers act on and mark resolved.

## 2. Target environment

- **Workspace:** `https://adb-7405605253712899.19.azuredatabricks.net`
- **CLI profile:** `otto-sandbox` (verified: `otto.jaaskelainen@databricks.com`)
- **Nothing is currently deployed there** — this is a full end-to-end deploy.

## 3. What already exists (reused as-is unless noted)

| Stage | Artifacts | Change needed |
|---|---|---|
| Lakeflow ingest | `notebooks/generate_pos_data.py`, `generate_promo_data.py`; SDP pipeline `pipeline/bronze|silver|gold/*`; `resources/pipeline.yml`, `resources/job.yml` | Catalog var only |
| Unity Catalog | `resources/catalog.yml` (catalog/schemas/volumes), `notebooks/apply_uc_tags.py` | Add `feature` schema; new catalog name |
| ML / GenAI | `training/train_forecast_model.py` (RandomForest, MLflow, UC registry `@prod`, batch score → `gold.forecast_demand`) | **Refactor to Feature Store** |
| Genie Room | `resources/genie.yml`, `src/retail_forecast.geniespace.json` | Enable include |
| Dashboard | `resources/dashboard.yml`, `dashboard/retail_forecast_dashboard.lvdash.json` | Enable include |
| App | `retail-forecast/` AppKit app (pages: risk, forecast explorer, actions, genie); `resources/app.yml` | Add Lakebase read/write on Action List page; enable include |

### Known config issues to reconcile

- App SQL queries (`retail-forecast/config/queries/*.sql`) and the training
  notebook widget default **hardcode catalog `gdai_test_dev`**, while
  `databricks.yml` defaults `var.catalog` to `otto_demo`. Standardize on a new
  bundle-created catalog.
- `var.warehouse_id` default `b519c6909e98cb0c` belongs to the old workspace —
  needs a warehouse that exists in `adb-7405605253712899.19`.
- `databricks.yml` `workspace.host` points at the old workspace.

## 4. Decisions (locked)

1. **New catalog created by the bundle**, named **`retail_forecast`**. All
   code (app queries, notebooks) parametrized to use it — no hardcoded catalog.
2. **Feature Store: GA `FeatureLookup` API** (not Public-Preview Feature
   Views). Feature Views noted as a documented extension.
3. **Lakebase role: serve + write-back** the operational action list. **No
   feature online store** — Feature Store stays offline; Lakebase is a distinct
   operational-serving capability. Online store + real-time endpoint documented
   as an extension only.
4. **All execution driven via CLI on the `otto-sandbox` profile**; captured
   text outputs committed under `/evidence/`.
5. **Lakebase + SQL warehouse are declarative bundle resources** (verified
   against CLI v1.14.1 `bundle schema`), not post-deploy CLI steps — the whole
   journey deploys from one bundle. Use the **Autoscaling** resource family:
   `postgres_projects`, `postgres_catalogs`, `postgres_synced_tables`, and
   `sql_warehouses`. **Use `postgres_synced_tables` (Beta, branch-based), NOT
   the legacy `synced_database_tables`** (`database_instance_name`-based, tied
   to the retired Provisioned tier — deploys against Autoscaling fail).

## 5. Architecture / data flow

```
Synthetic POS + Promo (notebooks)
        │  Lakeflow Job orchestrates
        ▼
landing volumes ──Auto Loader──▶ bronze ──▶ silver ──▶ gold (star schema + forecast_demand)   [Lakeflow SDP]
        │                                        │
   Unity Catalog governs everything (catalog `retail_forecast`, schemas, volumes, tags, lineage)
                                                 │
   ┌───────────────────┬─────────────────────────┼──────────────────────┬─────────────────────┐
   ▼                   ▼                          ▼                      ▼                     ▼
Feature Store      ML training              Genie Room            AI/BI Dashboard        ★ Lakebase (NEW)
feature.weekly_    FeatureLookup (PIT) →    (NL Q&A over gold)    (Lakeview)             synced action list
demand_features →  fe.log_model @prod →                                                  + native action_status
(offline Delta)    fe.score_batch →                                                      (write-back)
                   gold.forecast_demand                                                        │
                                                          Databricks App (AppKit) ◀────────────┘
                                                          reads gold via SQL warehouse;
                                                          reads/writes operational action
                                                          list via Lakebase Postgres
```

## 6. Component design

### 6.1 Feature Store (ML stage refactor)

New schema `retail_forecast.feature`. New feature table:

- **`retail_forecast.feature.weekly_demand_features`**
  - Primary keys: `sku`, `store_id`, `week`
  - `timeseries_column="week"` (singular — API canonical name; `timestamp_keys`
    / `timeseries_columns` raise `TypeError`)
  - Features: `week_of_year`, `is_promoted`, `discount_pct_feat`,
    `rolling_4wk_avg`, `avg_demand_last_12w`
  - Computed from `gold.fact_transactions` + `gold.fact_promotions` + dims
    (the Spark feature logic already in `train_forecast_model.py`, moved into a
    feature-build step).

Training/scoring path (replaces current inline approach):

1. `fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")`;
   `mlflow.set_registry_uri("databricks-uc")`.
2. `fe.create_table(..., timeseries_column="week")` then `fe.write_table(...)`.
3. Build labels (weekly `total_quantity`) → `fe.create_training_set(df=labels,
   feature_lookups=[FeatureLookup(table_name=..., lookup_key=["sku","store_id"],
   timestamp_lookup_key="week")], label="total_quantity")`.
4. Time-based split (train on weeks < cutoff, holdout last 8 weeks); train
   `RandomForestRegressor`.
5. **`fe.log_model(model=..., flavor=mlflow.sklearn, training_set=training_set,
   registered_model_name="retail_forecast.gold.retail_forecast_rf")`** — binds
   feature lineage (required for `score_batch`). NOT `mlflow.log_model`.
6. `client.set_registered_model_alias(FULL_NAME, "prod", version)`.
7. Score next 8 weeks: build **keys-only** scoring df (`sku, store_id, week`) →
   `fe.score_batch(model_uri="models:/...@prod", df=keys_only)` → derive
   `is_stockout_risk` / `is_overstock_risk` → write `gold.forecast_demand`
   (same schema as today so downstream consumers are unchanged).

Requirements: `databricks-feature-engineering>=0.16.0`, `mlflow>=2.22.0`.
Runs as the existing `train_model` job task (serverless).

Point-in-time note: `timestamp_lookup_key="week"` ensures only feature values
at/before each label's week are joined — no future leakage. This is the
correctness detail Feature Store buys us over the inline version.

### 6.2 Lakebase (new operational-serving layer)

**All Lakebase infra is declarative in the bundle** (Autoscaling family):

1. **`postgres_projects`** — Lakebase project (auto-creates `production` branch +
   `primary` read-write endpoint, scale-to-zero, 1 CU).
2. **`postgres_catalogs`** — register the Lakebase Postgres database as a UC
   catalog (one-time; required before synced tables).
3. **`postgres_synced_tables`** (phase-2 include) — synced table (read path) from
   an **action-list gold source**. Because synced tables are read-only in
   Postgres and best fed pre-curated data, add a gold table/MV
   `gold.forecast_action_list` (forecast_demand joined to `dim_store`/
   `dim_product`, current-week at-risk rows — the `action_list.sql` logic
   materialized) and sync *that*. `scheduling_policy: SNAPSHOT` for the POC
   (no CDF dependency; simplest, re-runs on redeploy/refresh). PK:
   `sku, store_id, week`. `new_pipeline_spec.storage_catalog` = the regular UC
   catalog `retail_forecast` (NOT the Lakebase catalog).
4. **Native `action_status` table (write path)** — NOT synced; a Postgres-native
   table the app's Service Principal creates on startup and writes to:
   `action_id (PK), sku, store_id, week, status, note, updated_by, updated_at`.
   `status ∈ {open, acknowledged, reorder_placed, resolved}`. Lives in an
   app-owned schema so the SP owns it (avoids `42501`).

**App connectivity — AppKit built-in `lakebase` plugin** (`@databricks/appkit`,
resource key `postgres`, permission `CAN_CONNECT_AND_CREATE`): does SQL
execution against Lakebase Autoscaling, so it serves both the synced-table reads
and the `action_status` writes — no custom Postgres client. Wire-up:
- Enable `lakebase` in `appkit.plugins.json` + `lakebase()` in `server.ts`.
- Attach the `postgres` resource (project/branch/database full paths) to the app
  — declaratively in `resources/app.yml`.
- **App Action List page:** reads synced action list `LEFT JOIN action_status`,
  and POSTs status updates that write to `action_status`. Other app pages (risk
  dashboard, forecast explorer, Genie) stay on the SQL warehouse / Genie
  unchanged.

**Deploy first, then run locally** (SP must own the app schema — the #1 Lakebase
permission pitfall).

### 6.3 Catalog / config reconciliation

- `databricks.yml`: set `workspace.host` to the new workspace; set
  `var.catalog` default to `retail_forecast`.
- **SQL warehouse via bundle:** add a serverless `sql_warehouses` resource and
  reference its id (`${resources.sql_warehouses.<key>.id}`) from the app/Genie/
  dashboard instead of the hardcoded old-workspace `var.warehouse_id`.
- Parametrize app SQL queries and the training notebook to use `var.catalog` /
  the `catalog` widget instead of hardcoded `gdai_test_dev`.
- `resources/catalog.yml`: add `feature` schema alongside landing/bronze/
  silver/gold.

## 7. Execution & evidence plan

Deploy in order via `otto-sandbox`, capturing text output into a committed
`/evidence/` tree. Every file is real captured output (`.txt`/`.json`/`.md`);
`evidence/README.md` maps each assignment stage → its proof.

| # | Step | Evidence committed (text) |
|---|---|---|
| 0 | Reconcile config (host, catalog, warehouse_id), `bundle validate` | validate output, config diff |
| 1 | `bundle deploy` (catalog + pipeline + job) | deploy logs |
| 2 | Run data-gen notebooks (populate landing volumes) | row counts, `/Volumes` listing |
| 3 | Run SDP pipeline (bronze→silver→gold) | pipeline run status, table counts, sample rows |
| 4 | UC governance (`apply_uc_tags`) | catalog tree, applied tags, a lineage query + a grants query result |
| 5 | Feature Store + train + score | feature-table counts + sample, MLflow run MAE, registered `@prod` version, `fe.score_batch` output, `forecast_demand` counts + sample |
| 6 | Lakebase (bundle deploy of project/catalog/synced table) + write-back demo | project + endpoint status, `get-synced-table` state, `SELECT` from Postgres synced table, `CREATE`+`INSERT`+`SELECT` on `action_status` via `databricks psql` |
| 7 | Genie NL query | a question → generated SQL → result rows (Genie API/CLI) |
| 8 | Dashboard + App deploy | deploy status, app URL, key app API responses (curl'd JSON) |

Evidence is harvested via CLI: `databricks jobs get-run` / `get-run-output`,
`databricks pipelines`, SQL via warehouse (`databricks api` / statement
execution), Genie Conversation API, Lakebase Postgres client, and `curl`
against the deployed app.

## 8. Time estimate

~4–6h. Base build exists; the bulk is the Feature Store refactor, the Lakebase
layer + app write-back, and evidence harvesting.

## 9. Out of scope / documented extensions

- **Feature online store** (Lakebase-backed) + **real-time serving endpoint** —
  documented as an extension; not built (batch forecast doesn't need it, and
  Lakebase's operational role is covered by the action-list serving).
- **Feature Views** (declarative, Public Preview) — noted as the newer
  alternative to the GA FeatureLookup API; not used.
- No production hardening (CI/CD, multi-env promotion, alerting) beyond what the
  bundle already expresses.

## 10. Risks / open items

Resolved during planning:
- **AppKit ↔ Lakebase** → built-in `lakebase` plugin (resource key `postgres`);
  serves reads + writes. No custom client.
- **SQL warehouse** → created declaratively via bundle `sql_warehouses`.
- **Synced table = declarative** via `postgres_synced_tables` (Beta), SNAPSHOT
  mode; legacy `synced_database_tables` avoided.

Remaining risks:
- **`postgres_synced_tables` / `postgres_projects` are Beta** bundle resources —
  if a field/deploy misbehaves, fall back to the `databricks postgres
  create-project` / `create-synced-table` CLI (same field names) and reference
  the resulting IDs from the app.
- **Deploy ordering:** the synced table's `source_table_full_name`
  (`gold.forecast_action_list`) must exist at deploy time → synced table + app
  are phase-2 includes, enabled only after the pipeline run produces gold.
- **Serverless availability / entitlements** in the new workspace for the
  pipeline, jobs, and Lakebase — verify early (step 0/1).
- **App SP schema ownership** for `action_status` — deploy the app before any
  local run so the SP owns its schema (avoids `permission denied … 42501`).
