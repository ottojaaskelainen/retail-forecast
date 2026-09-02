# MLOps Split + Future-Dated Forecast — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (or executing-plans) to implement this task-by-task. Steps use `- [ ]` checkboxes.

**Goal:** Refactor the single training notebook into three independent processes (feature build → train → score), make the forecast horizon dynamic and future-dated, and refresh the synthetic data to ~now so predictions land in the actual future (Sept–Oct 2026).

**Architecture:** Split `training/train_forecast_model.py` into three notebooks wired as separate tasks of `retail-forecast-job`, so the frequent light path (scoring) runs without retraining or rebuilding features, and any task is independently re-runnable via `databricks jobs run-now --only <task>`. The forecast anchor becomes dynamic (`DATA_END = max(week) in fact_transactions`) instead of a hardcoded date.

**Tech stack:** Databricks CLI v1.14.1 (profile `otto-sandbox`, workspace adb-7405605253712899.19), catalog `retail_forecast`, engine:direct DABs, serverless env `client:"5"` with job-env deps `databricks-feature-engineering>=0.16.0` + `scikit-learn`, MLflow + UC Feature Store, Lakebase synced table (unchanged).

**Prior spec (context):** `docs/superpowers/specs/2026-09-02-lakebase-and-evidence-design.md`. This plan builds on the completed build (tip commit at plan-write time; the whole journey is deployed and green). SDD ledger for the prior build: `<repo-root>/.superpowers/sdd/2026-09-02-lakebase-and-evidence/progress.md` — read its Ruling(...) lines for accepted constraints (engine:direct needs LITERAL Lakebase paths; env v5 + job-env deps; RandomForest bounded n_estimators=50/max_depth=12; tag keys renamed ingest_source/data_category; domain governed-tag allows 'retail').

## Global Constraints

- All CLI uses `--profile otto-sandbox`. Never omit it.
- Catalog `retail_forecast`; no hardcoded `gdai_test_dev`/`otto_demo`.
- Feature Store: `timeseries_column` (singular); `fe.log_model(training_set=...)`; `fe.score_batch` keys-only. RandomForest bounded: `n_estimators=50, max_depth=12, random_state=42` (avoids score_batch UDF OOM).
- Evidence: real captured text under `evidence/`, committed. No screenshots.
- The dynamic anchor `DATA_END` MUST be derived from data (`max(week)` of `gold.fact_transactions` weekly aggregation), not hardcoded, in BOTH train and score steps so they agree.
- Lakebase synced table (`postgres_synced_tables`) and the app are unchanged by this refactor — the synced source `gold.forecast_action_list` keeps the same schema.

---

### Task 1: Refresh synthetic data to ~now (dynamic end date)

**Files:** Modify `notebooks/generate_pos_data.py`, `notebooks/generate_promo_data.py`.

- [ ] **Step 1:** In both generators, change the hardcoded `DATA_END = date(2026, 6, 29)` so data runs up to a recent Monday near today. Prefer a dynamic default: `DATA_END = <most recent Monday on/before date.today()>` computed at run time (e.g. `today = date.today(); DATA_END = today - timedelta(days=today.weekday())`). Keep `DATA_START = date(2024, 7, 1)`. Keep `TODAY = DATA_END`. Ensure promos still generate a mix of past + a few future-dated ones relative to the new `DATA_END`.
- [ ] **Step 2:** Static check: `python -c "import ast; ast.parse(open('notebooks/generate_pos_data.py').read()); ast.parse(open('notebooks/generate_promo_data.py').read()); print('parse ok')"`.
- [ ] **Step 3:** Commit: `git add notebooks/generate_pos_data.py notebooks/generate_promo_data.py && git commit -m "Generate synthetic data through current week (dynamic DATA_END)"`.

### Task 2: Feature-build notebook (feature-store formation, standalone)

**Files:** Create `training/build_features.py` (Databricks notebook source). Extract the feature-engineering half of `training/train_forecast_model.py`.

- [ ] **Step 1:** New notebook reads `gold.fact_transactions`, `gold.fact_promotions`, `gold.dim_store`, `gold.dim_product`; reproduces the existing weekly aggregation, `valid_pairs` (≥12 weeks history), promo date-overlap features (`is_promoted`, `discount_pct_feat`), `rolling_4wk_avg`, `avg_demand_last_12w`, `week_of_year`. Compute `DATA_END` dynamically = max weekly `week` in the aggregation.
- [ ] **Step 2:** Build `features_all_df` = historical feature rows + forward-dated rows for the next 8 weeks after dynamic `DATA_END` (carry last-known rolling averages; promo features from future promos; `week_of_year` from the forecast week). Same columns as today: `sku, store_id, week, week_of_year, is_promoted, discount_pct_feat, rolling_4wk_avg, avg_demand_last_12w`.
- [ ] **Step 3:** `fe.create_table(name=retail_forecast.feature.weekly_demand_features, primary_keys=[sku,store_id,week], timeseries_column="week", schema=...)` (create-if-missing, swallow "already exists"), then `fe.write_table(mode="merge")`. Also write a small `feature.weekly_demand_labels` table (or leave labels to the train step reading fact_transactions) — decide: simplest is train step recomputes labels from fact_transactions weekly agg (keeps feature table = features only). Document the choice in the notebook header.
- [ ] **Step 4:** `dbutils.notebook.exit(json.dumps({"feature_rows": <count>, "data_end": str(DATA_END)}))`.
- [ ] **Step 5:** `ast.parse` check; commit `git commit -m "Add standalone feature-build notebook (UC Feature Store)"`.

### Task 3: Training notebook (train + register only)

**Files:** Create `training/train_model.py`; the old `training/train_forecast_model.py` will be removed in Task 5 once the job references the new tasks.

- [ ] **Step 1:** Reads labels (weekly `total_quantity` per sku/store/week from `gold.fact_transactions`, valid pairs, weeks < cutoff = last 8 weeks held out). Build `training_set = fe.create_training_set(df=labels, feature_lookups=[FeatureLookup(FEATURE_TABLE, lookup_key=["sku","store_id"], timestamp_lookup_key="week")], label="total_quantity", exclude_columns=["week","sku","store_id"])`.
- [ ] **Step 2:** Train `RandomForestRegressor(n_estimators=50, max_depth=12, random_state=42)` on `FEATURES=["week_of_year","is_promoted","discount_pct_feat","rolling_4wk_avg","avg_demand_last_12w"]`; compute holdout MAE; `fe.log_model(training_set=training_set, flavor=mlflow.sklearn, registered_model_name="retail_forecast.gold.retail_forecast_rf")`; set `@prod` alias.
- [ ] **Step 3:** `dbutils.notebook.exit(json.dumps({"mae_holdout": ..., "model_version": ...}))`. `ast.parse` check; commit `git commit -m "Add standalone training notebook (FeatureLookup + fe.log_model)"`.

### Task 4: Scoring notebook (batch inference only)

**Files:** Create `training/score_forecast.py`.

- [ ] **Step 1:** Compute dynamic `DATA_END` = max week in `gold.fact_transactions` weekly agg (MUST match the feature build). Build `score_keys` = valid pairs × next-8-weeks-after-DATA_END, keys-only `(sku, store_id, week)`.
- [ ] **Step 2:** `scored = fe.score_batch(model_uri="models:/retail_forecast.gold.retail_forecast_rf@prod", df=score_keys, result_type="double")`; derive `predicted_demand` (max(0, round)), `is_stockout_risk`/`is_overstock_risk` from `avg_demand_last_12w` (present on scored via lookup), `model_version`; write `gold.forecast_demand` (same schema as today).
- [ ] **Step 3:** Materialize `gold.forecast_action_list` (at-risk subset joined to `dim_store`/`dim_product`, Postgres-friendly columns, keyed sku/store_id/week) — same schema the synced table expects.
- [ ] **Step 4:** `dbutils.notebook.exit(json.dumps({"forecast_rows":..., "action_rows":..., "forecast_weeks":[...]}))`. `ast.parse`; commit `git commit -m "Add standalone scoring notebook (fe.score_batch → forecast_demand + forecast_action_list)"`.

### Task 5: Rewire the job DAG

**Files:** Modify `resources/job.yml`; remove `training/train_forecast_model.py`.

- [ ] **Step 1:** Replace the single `train_model` task with three tasks (all env_key default / client:"5"):
  `build_features` (depends_on run_pipeline) → `train_model` (depends_on build_features) → `score_forecast` (depends_on train_model). Point `apply_uc_tags` `depends_on: score_forecast` (it tags forecast_demand/action_list). Keep generate_pos/promo → run_pipeline as-is.
- [ ] **Step 2:** `git rm training/train_forecast_model.py`. Run `databricks bundle validate --profile otto-sandbox`.
- [ ] **Step 3:** Commit: `git commit -m "Split job into build_features/train_model/score_forecast tasks; dynamic future-dated forecast"`.

### Task 6: Deploy, run end-to-end, re-capture evidence

**Files:** Update `evidence/` (ingest/pipeline/feature/ml/lakebase), `evidence/README.md`.

- [ ] **Step 1:** `databricks bundle deploy --profile otto-sandbox` (tee to evidence). Run the full job; confirm all tasks SUCCESS.
- [ ] **Step 2:** Verify the forecast is now FUTURE-dated: capture the distinct forecast weeks from `gold.forecast_demand` — they must be 8 weeks after the new data end (≈ Sept–Oct 2026, after 2026-09-02). Save to `evidence/05_ml/forecast_weeks.txt`.
- [ ] **Step 3:** Re-capture the affected evidence (bronze/silver/gold counts now larger; train_result; feature_table sample/count; forecast_demand sample+summary; forecast_action_list). The Lakebase synced table refreshes from the new `forecast_action_list` (SNAPSHOT) — re-capture `synced_select.txt` + a fresh `/api/actions` from the app (now future weeks).
- [ ] **Step 4:** Prove the split works: `databricks jobs run-now <job-id> --json '{"only":["score_forecast"]}'` succeeds WITHOUT retraining, and capture its run status → `evidence/05_ml/score_only_run.txt`.
- [ ] **Step 5:** Update `evidence/README.md`: note the 3-task split + dynamic future-dated forecast, and update headline numbers. Commit: `git add -A && git commit -m "Deploy split pipeline; re-capture evidence (future-dated forecast, score-only re-run)"`.

### Task 7 (optional, if time): dashboard week-scope + source labels

Carried from the earlier discussion (keeping the warehouse/Lakebase split): scope the Risk Dashboard to the same "next week" as the Action List (or add a week selector), and add a one-line data-source label per app page (Action List → Lakebase; Risk Dashboard/Forecast Explorer → UC Delta via SQL warehouse; Genie → gold via Genie). Local typecheck/build/smoke; redeploy; commit.

## Self-Review notes
- Feature build and score MUST compute `DATA_END` identically (max week of fact_transactions weekly agg) or the forward-dated feature rows won't align with score_keys → score_batch returns nulls. Call this out in both notebook headers.
- `forecast_action_list` schema must stay identical (the deployed `postgres_synced_tables` resource + app query depend on it).
- Keep RandomForest bounded (OOM ruling) and env v5 + job-env deps (no notebook %pip).
