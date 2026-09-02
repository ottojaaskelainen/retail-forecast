# Design: Lakebase Serving + Feature Store + Execution Evidence

**Date:** 2026-09-02
**Status:** Approved for planning
**Repo:** retail-forecast-poc

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

1. **Lakebase database instance** provisioned via DABs/CLI in the workspace
   (managed Postgres).
2. **Synced table (read path):** a Lakebase synced table from an action-list
   source (gold `forecast_demand` joined to `dim_store`/`dim_product`,
   filtered to current-week at-risk rows — the logic in
   `config/queries/action_list.sql`). This is the low-latency operational
   serving surface.
3. **Native `action_status` table (write path):** Postgres-native table the app
   writes to:
   `action_id (PK), sku, store_id, week, status, note, updated_by, updated_at`.
   `status ∈ {open, acknowledged, reorder_placed, resolved}`.
4. **App Action List page:** reads synced action list `LEFT JOIN action_status`
   (to show operational state per action), and POSTs status updates back to
   Postgres. Other app pages (risk dashboard, forecast explorer, Genie) stay on
   the SQL warehouse / Genie unchanged.

Exact AppKit ↔ Lakebase connectivity (plugin vs. Postgres client, app resource
binding, auth) to be confirmed against `databricks-lakebase` +
`databricks-apps` skills during planning; the design is connectivity-agnostic.

### 6.3 Catalog / config reconciliation

- `databricks.yml`: set `workspace.host` to the new workspace; set
  `var.catalog` default to `retail_forecast`; set `var.warehouse_id` to a
  warehouse that exists in the new workspace (create one via the bundle or
  reuse an existing serverless SQL warehouse — confirm during planning).
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
| 6 | Lakebase provision + sync + write-back demo | instance status, synced-table state, `SELECT` from Postgres, an `INSERT` into `action_status` + read-back |
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

- **AppKit ↔ Lakebase connectivity mechanics** — confirm the supported pattern
  (AppKit Lakebase/Postgres access + app resource binding) during planning.
- **SQL warehouse in the new workspace** — confirm whether to create one via the
  bundle or reuse an existing serverless warehouse.
- **Synced table refresh mode** (snapshot vs. continuous) — pick based on
  Lakebase sync capabilities and demo needs.
- **Serverless availability / entitlements** in the new workspace for the
  pipeline and jobs — verify early (step 0/1).
