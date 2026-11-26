# SQL analysis guide

The monitor uses SQLite in memory, loading validated pandas DataFrames into temporary tables before executing SQL.

## Per-pipeline reliability

`pipeline_kpis()` calculates run counts, failures, success percentage, durations and processed records. It deliberately includes operationally failed executions in the denominator, as long as their source data is valid.

## Failure trend: calendar-aware window

```sql
WITH daily AS (
  SELECT run_date, COUNT(*) AS runs,
         SUM(status = 'failed') AS failed_runs
  FROM pipeline_runs
  GROUP BY run_date
)
SELECT run_date,
       ROUND(100.0 * failed_runs / runs, 1) AS failure_rate_pct,
       ROUND(
         AVG(100.0 * failed_runs / runs) OVER (
           ORDER BY julianday(run_date)
           RANGE BETWEEN 6 PRECEDING AND CURRENT ROW
         ), 1
       ) AS failure_rate_7d_avg_pct
FROM daily
ORDER BY run_date;
```

`RANGE BETWEEN 6 PRECEDING AND CURRENT ROW` over Julian day numbers includes observed days within the past **seven calendar days**, rather than simply taking the previous seven rows. Missing calendar dates are not assumed to have a 0% failure rate. The window averages daily rates equally, not weighted by each day's run count.

## Failures versus support tickets

`pipeline_ticket_overview()` creates separate aggregates in **CTEs** and combines them with a **LEFT JOIN**:

```sql
WITH runs AS (
  SELECT pipeline, COUNT(*) AS total_runs,
         SUM(status = 'failed') AS failed_runs
  FROM pipeline_runs GROUP BY pipeline
),
tickets_by_pipeline AS (
  SELECT pipeline, COUNT(*) AS tickets
  FROM tickets GROUP BY pipeline
)
SELECT runs.pipeline, runs.total_runs, runs.failed_runs,
       COALESCE(tickets_by_pipeline.tickets, 0) AS tickets,
       ROUND(1.0 * COALESCE(tickets_by_pipeline.tickets, 0)
             / NULLIF(runs.failed_runs, 0), 2) AS tickets_per_failure
FROM runs
LEFT JOIN tickets_by_pipeline
  ON tickets_by_pipeline.pipeline = runs.pipeline;
```

The left join keeps pipelines even if they have no support tickets. `NULLIF` avoids division by zero when no failures occurred.

For example, a pipeline with four runs (two failed) and three tickets has 1.5 tickets per failure. Joining the raw tables by pipeline would produce twelve rows (four runs times three tickets). Aggregating each table first preserves the original counts.

**Interpretation warning:** support tickets and failures are not linked to the same incidents; the ratio highlights which pipelines may deserve investigation but should not be interpreted as a causal measure.
