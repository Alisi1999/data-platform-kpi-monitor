# Architecture

The monitor is a small, reproducible **batch** pipeline, not a live monitoring service.

```text
monitor.generate
  ├── synthetic pipeline_runs.csv
  ├── synthetic tickets.csv
  └── synthetic use_case_registry.csv
          |
          v
monitor.cli → monitor.analyze.validate_runs
          |         ├── cleaned run records
          |         └── issue log (one row per quality finding)
          v
SQLite in-memory queries + pandas ticket aggregation
          |
          v
KPI CSVs + HTML dashboard + reliability chart + executive summary
```

## Modules

- `monitor/generate.py`: creates deterministic demo datasets using a fixed NumPy random seed.
- `monitor/analyze.py`: implements vectorized quality rules and SQLite aggregations, including CTEs, joins and calendar-based SQL window frames.
- `monitor/cli.py`: provides the command-line interface, exports, plots, HTML report, and CI-compatible exit codes.
- `tests/test_monitor.py`: verifies the contract, SQL results, failure modes and end-to-end report creation.

## Data quality versus operational failure

A pipeline execution whose `status` is `failed` can be a **valid observation**. Failed-but-valid runs belong in reliability metrics. Missing IDs, corrupted dates, invalid record counts, or repeated IDs are *quality findings* and are excluded from the operational KPI denominator.

The default duplicate policy retains the first otherwise-valid occurrence of an ID. An earlier corrupt row does not suppress a later valid one. The stricter `flag_all` policy removes every duplicate copy.

## Storage choices

The project uses **SQLite in memory** to make SQL analysis simple to reproduce without cloud credentials. It does not demonstrate production orchestration, distributed processing, Databricks or Azure. The synthetic CSV files and reports are regenerated on demand rather than stored as source-controlled artifacts.

## Boundaries

Support tickets are aggregated by pipeline; they are not linked to specific failed run IDs. A high ticket-to-failure ratio is a useful signal for investigation, not proof of causality.
