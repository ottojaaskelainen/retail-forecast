# Evidence Index — Retail Demand Forecast POC

## The customer problem

Retail merchandising teams lose margin two ways: stockouts (demand exceeds supply) and overstocks (supply exceeds demand), both driven by promotion spikes that point-in-time inventory systems miss. This POC demonstrates an end-to-end Databricks lakehouse journey — raw transaction ingestion through ML-powered forecasting to an operational app — that surfaces 2,752 high-priority reorder/clearance actions to store managers every week, all **dynamically future-dated** (8 weeks of Sept–Oct 2026 forecasts generated from data through 2026-08-31).

## Workspace, catalog, and profile

| Item | Value |
|------|-------|
| Workspace | `adb-7405605253712899.19` (Azure) |
| UC Catalog | `retail_forecast` |
| Lakebase project | `retail-forecast-lb` |
| CLI/deploy profile | `otto-sandbox` |
| App runtime auth | Databricks Apps service principal (auto-provisioned) |
| App URL | `https://retail-forecast-7405605253712899.19.azure.databricksapps.com` |
| App Service Principal | client-id `944a2a4f-2bb9-465b-b587-4cbdac9c6106` |
| Evidence captured | 2026-09-02 |

## How to read the evidence

Each numbered subdirectory corresponds to one deployment stage. Files are raw CLI/API text or JSON captured immediately after execution. Numbers in this README come directly from those files — nothing is interpolated.

---

## Stage → Proof table

| # | Assignment stage | Evidence file(s) | What the output proves |
|---|-----------------|------------------|------------------------|
| 1 | **Lakeflow ingest** | `01_ingest/bronze_counts.txt`, `01_ingest/volume_listing.txt`, `02_pipeline/job_run_state.txt`, `02_pipeline/silver_gold_counts.txt` | Bronze tables loaded (13,271,903 transaction rows, 600 products, 120 stores, 150 promotions); Lakeflow pipeline job ran to SUCCEEDED; silver and gold layers materialized (fact_transactions 2,368,383 rows, all dimension tables present). |
| 2 | **Unity Catalog governance** | `03_uc_governance/catalog_tree.txt`, `03_uc_governance/tags.txt`, `03_uc_governance/lineage.txt`, `03_uc_governance/grants.txt`, `03_uc_governance/tag_policy_domain.json` | UC catalog `retail_forecast` exists with bronze/silver/gold/feature schemas; data-domain tag policy applied to tables; column-level lineage captured; grant output confirms current permission state. |
| 3 | **Lakebase operational serving** | `06_lakebase/project.json`, `06_lakebase/branches.json`, `06_lakebase/endpoints.json`, `06_lakebase/synced_table_deploy.txt`, `06_lakebase/synced_table_status.json`, `06_lakebase/synced_select.txt`, `06_lakebase/action_status_writeback.txt` | Lakebase project `retail-forecast-lb` (Postgres 17) created and ACTIVE; `forecast_action_list` synced-table pipeline deployed and running; live `databricks psql` SELECT confirms 2,752 rows in `databricks_postgres.public.forecast_action_list` (refreshed via SNAPSHOT from new gold data); write-back demonstration inserts two `action_status` rows (AP-001/store-1008 and HM-007/store-1003) and reads them back. |
| 4 | **ML + Feature Store (3-task split)** | `04_feature_store/feature_table_meta.txt`, `04_feature_store/feature_table_count.txt`, `04_feature_store/feature_table_sample.txt`, `05_ml/train_result.json`, `05_ml/registered_model.txt`, `05_ml/forecast_weeks.txt`, `05_ml/forecast_demand_summary.txt`, `05_ml/forecast_demand_sample.txt`, `05_ml/forecast_action_list_sample.txt`, `05_ml/score_only_run.txt` | UC Feature Store table `retail_forecast.feature.weekly_demand_features` created with 243,570 rows (PKs: sku, store_id, week, data through 2026-08-31); training split into 3 separate DAG tasks (build_features → train_model → score_forecast); RandomForest model trained with MAE 15.80 on holdout set; model version 9 registered at `retail_forecast.gold.retail_forecast_rf@prod`; `forecast_demand` gold table contains 16,000 rows (1,707 stockout-risk, 1,045 overstock-risk); `forecast_action_list` contains 2,752 rows; ALL 8 forecast weeks are FUTURE-DATED (2026-09-07 through 2026-10-26); score-only re-run (without retraining) also SUCCEEDED. |
| 5 | **Genie** | `08_genie/genie_query.json`, `08_genie/genie_query.md` | Genie space `01f1a6c8e89a1afeba1d4a5a85be89e2` answered a natural-language question ("top 5 stores by stockout-risk SKUs") by auto-generating SQL against `retail_forecast.gold.forecast_demand` + `dim_store`, executing it, and returning 5 ranked rows — proving the Genie space is live and data-connected. |
| 6 | **Databricks App** | `07_app/app_get.json`, `07_app/phase2_deploy.txt`, `07_app/app_start.txt`, `07_app/api_actions.json`, `07_app/api_risk.json`, `07_app/api_actions_after_writeback.json` | App `retail-forecast` deployed (state RUNNING, SUCCEEDED); `GET /api/actions` returns 460 rows from Lakebase Postgres, all with `week: 2026-09-07` (first future-dated forecast week); `GET /api/risk-summary` returns row_count 2,752; `POST /api/actions/status` write-back reflected in `api_actions_after_writeback.json`. |

---

## MLOps pipeline split (added 2026-09-02)

The monolithic training notebook was split into three independent DAG tasks:

1. **build_features** — reads silver/gold, computes UC Feature Store table `weekly_demand_features` (243,570 rows through 2026-08-31).
2. **train_model** — reads features, trains RandomForest, registers at `retail_forecast.gold.retail_forecast_rf@prod` (version 9, MAE 15.80).
3. **score_forecast** — loads `@prod` model, scores 8 dynamic future Mondays after data_end (2026-09-07 → 2026-10-26), writes `forecast_demand` + `forecast_action_list`.

The split enables:
- **Score-only re-runs** without retraining (proved by `evidence/05_ml/score_only_run.txt`).
- **Dynamic future-dating** — forecast weeks are always computed relative to `data_end`, never hardcoded.

---

## Post-deploy Service Principal grants (for reproducibility)

A fresh `databricks bundle deploy` provisions the app SP (client-id `944a2a4f-2bb9-465b-b587-4cbdac9c6106`) but does not automatically grant it access to the synced Lakebase table or the UC analytics catalog. The following two one-time grants are required after each clean redeploy.

### 1. Lakebase Postgres — SELECT on synced table

The synced-table pipeline owns `public.forecast_action_list`; the app SP needs an explicit grant:

```sql
-- Run in Lakebase Postgres as superuser (via the Databricks Lakebase endpoint)
GRANT SELECT ON public.forecast_action_list TO "944a2a4f-2bb9-465b-b587-4cbdac9c6106";
```

The SP principal name in Postgres is the client-id UUID. The app also writes to `app.action_status`; because the bundle resource declares `CAN_CONNECT_AND_CREATE` on the Postgres resource, the app SP can create and own tables in `app` schema without an extra grant.

### 2. Unity Catalog — analytics routes and Genie

The app SP needs `USE CATALOG`, `USE SCHEMA`, and `SELECT` on the UC catalog so the analytics API routes and the embedded Genie space can query `retail_forecast.gold.*`:

```sql
-- Applied via the UC Permissions REST API (databricks permissions set) because
-- `databricks grants update` could not resolve the SP by display name at deploy time.
GRANT USE CATALOG ON CATALOG retail_forecast TO `944a2a4f-2bb9-465b-b587-4cbdac9c6106`;
GRANT USE SCHEMA  ON SCHEMA retail_forecast.gold TO `944a2a4f-2bb9-465b-b587-4cbdac9c6106`;
GRANT SELECT      ON SCHEMA retail_forecast.gold TO `944a2a4f-2bb9-465b-b587-4cbdac9c6106`;
```

**Note:** `databricks grants update` expected a display name that could not be resolved for the auto-provisioned SP. The equivalent grants were applied successfully via `POST /api/2.0/permissions/…` (SQL Statements / Permissions REST API) using the numeric service_principal_id `146460119787691`.

### App is live at

`https://retail-forecast-7405605253712899.19.azure.databricksapps.com`
