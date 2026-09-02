# Retail Demand Forecast POC

End-to-end Databricks lakehouse demonstration: raw retail transactions → Lakeflow ingest → Unity Catalog governance → ML forecasting with Feature Store → Lakebase operational serving → Genie natural-language analytics → Databricks App for store managers.

## Repository layout

```
databricks.yml          # DABs bundle root (workspace adb-7405605253712899.19)
resources/              # Bundle resource definitions (catalog, jobs, pipelines, app, genie, lakebase)
retail-forecast/        # Databricks App source (AppKit/React + FastAPI backend)
notebooks/              # Pipeline, training, and feature engineering notebooks
evidence/               # Captured CLI/API output proving each stage ran (text-readable)
docs/                   # Design specs and architecture notes
```

## How this maps to the assignment

The six required assignment stages map directly to subdirectories under `evidence/`:

| Stage | Evidence directory | Key metric |
|-------|--------------------|------------|
| Lakeflow ingest | `evidence/01_ingest/`, `evidence/02_pipeline/` | 10.9 M transaction rows ingested; pipeline job SUCCEEDED |
| Unity Catalog governance | `evidence/03_uc_governance/` | Tags, lineage, and grants on catalog `retail_forecast` |
| Lakebase operational serving | `evidence/06_lakebase/` | Postgres 17 project live; synced table 3,182 rows; write-back confirmed |
| ML + Feature Store | `evidence/04_feature_store/`, `evidence/05_ml/` | MAE 12.20; feature table 225,994 rows; 16,000-row forecast gold table |
| Genie | `evidence/08_genie/` | NL question auto-generated SQL and returned 5 ranked store rows |
| Databricks App | `evidence/07_app/` | App RUNNING; `/api/actions` 500 rows; write-back reflected |

The full stage → proof mapping with exact file names, headline numbers, and post-deploy reproducibility notes (SP grants) is in **`evidence/README.md`**.

## Design specification

`docs/superpowers/specs/2026-09-02-lakebase-and-evidence-design.md`

## Architecture summary

Raw CSV/Parquet files (Unity Catalog Volumes) → Lakeflow Spark Declarative Pipeline (bronze → silver → gold) → UC Feature Store (weekly_demand_features, 225,994 rows) → MLflow RandomForest training (MAE 12.20) → gold forecast tables → Lakebase Postgres synced table + write-back → Genie space → Databricks App.
