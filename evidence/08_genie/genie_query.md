# Genie Natural-Language Query Evidence

**Space ID:** `01f1a6c8e89a1afeba1d4a5a85be89e2`  
**Conversation ID:** `01f1a6c9f3af1138af9bc4151c2bbb09`  
**Date:** 2026-09-02

---

## Question

> Show me the top 5 stores by total number of stockout-risk SKUs across all forecast weeks

## Generated SQL

```sql
WITH stockout_counts AS (
  SELECT
    s.store_id,
    s.store_name,
    COUNT(f.sku) AS stockout_risk_skus
  FROM retail_forecast.gold.forecast_demand f
  JOIN retail_forecast.gold.dim_store s ON f.store_id = s.store_id
  WHERE f.is_stockout_risk = true
    AND f.store_id IS NOT NULL
  GROUP BY s.store_id, s.store_name
)
SELECT store_id, store_name, stockout_risk_skus
FROM (
  SELECT *, RANK() OVER (ORDER BY stockout_risk_skus DESC) AS rank
  FROM stockout_counts
)
WHERE rank <= 5
```

## Result Rows (5 rows)

| store_id | store_name                    | stockout_risk_skus |
|----------|-------------------------------|--------------------|
| 1010     | Harris, Collins and Carney    | 324                |
| 1009     | Humphrey Inc                  | 282                |
| 1011     | Perez Inc                     | 235                |
| 1005     | Watts, Robinson and Nguyen    | 203                |
| 1012     | Jordan, Henderson and Owens   | 202                |

## Genie Answer

> The top 5 stores by total number of stockout-risk SKUs across all forecast weeks are:
> - **Harris, Collins and Carney**: 324 SKUs
> - **Humphrey Inc**: 282 SKUs
> - **Perez Inc**: 235 SKUs
> - **Watts, Robinson and Nguyen**: 203 SKUs
> - **Jordan, Henderson and Owens**: 202 SKUs
>
> Harris, Collins and Carney has the highest number of stockout-risk SKUs, with a notable lead over the other stores.

---

*Status: COMPLETED — Genie generated SQL and executed it against `retail_forecast.gold.forecast_demand` + `retail_forecast.gold.dim_store`, returning 5 rows.*
