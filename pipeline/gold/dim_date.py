from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(comment="Date dimension — 2024-01-01 through 2026-12-31")
def dim_date():
    dates = spark.sql("""
        SELECT explode(sequence(date('2024-01-01'), date('2026-12-31'), interval 1 day)) AS date_id
    """)
    return (
        dates
        .withColumn("year",         F.year("date_id"))
        .withColumn("quarter",      F.quarter("date_id"))
        .withColumn("month",        F.month("date_id"))
        .withColumn("week_of_year", F.weekofyear("date_id"))
        .withColumn("day_of_week",  F.dayofweek("date_id"))
        .withColumn("is_weekend",   F.dayofweek("date_id").isin(1, 7))
    )
