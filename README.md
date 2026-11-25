# Data Platform KPI & Quality Monitor

A small, **reproducible portfolio project** that demonstrates practical **Python, pandas, SQL, data quality checks, KPI monitoring, support-ticket analysis and data/AI use-case documentation**. This project is a standalone learning demonstration, not an employer system or production platform.

> **Data note:** All input records are generated locally and are **synthetic**. The project contains no personal, pharmacy, patient or real company data.

## What it does

1. Generates demo pipeline executions, support tickets and a data/AI use-case registry.
2. Checks pipeline run data for missing/invalid values, duplicates, and negative record counts.
3. Keeps invalid data in an **issue log**, and excludes flagged records from KPI calculations.
4. Aggregates operational KPIs with **SQL queries in SQLite**: number of runs, failure counts, success rate, average and maximum duration, processed records.
5. Tracks the **daily failure rate with a 7-calendar-day rolling average** of dates that have recorded runs (SQL window function).
6. **Joins aggregate pipeline failures with support-ticket totals** (SQL `LEFT JOIN`) to help prioritize investigations. Tickets are not tied to particular failed runs; no causal attribution is implied.
7. Summarizes recurring support-ticket categories using pandas.
8. Exports a browser-readable **HTML dashboard**, a chart and machine-readable reports.
9. Can act as a **data contract**: with `--fail-on-issues` the run exits with code 1 when quality issues are found, so it can block a CI or scheduled job.

### Example output

After running the commands below, open `reports/dashboard.html` in your browser. Generated files include `reports/pipeline_reliability.png`, CSVs, and an executive summary. The sample inputs and derived reports are generated locally instead of committing large generated artifacts; GitHub Actions runs the same workflow.

## Quick start

```bash
# From this repository root
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt

# Create the reproducible synthetic sample (required before analyzing)
python -m monitor.generate --output sample_data --end-date 2026-11-25

# Analyze data, validate records and produce a local report
python -m monitor.cli --input sample_data --output reports

# Options
python -m monitor.cli --duplicate-policy flag_all   # flag every copy of a duplicated run_id
python -m monitor.cli --fail-on-issues              # exit code 1 if any quality issue is found

# Run automated tests
python -m pytest -q
```

## Project structure

```text
monitor/
  generate.py      # deterministic synthetic input generation
  analyze.py       # validation, SQL KPI calculation, ticket triage
  cli.py           # export outputs and local HTML dashboard
sample_data/        # generated synthetic CSV files (created by the generator)
reports/            # generated KPIs, issues, chart and HTML dashboard
tests/              # core logic and end-to-end tests
.github/workflows/  # automated CI test checks
```

## Documentation and CI artifacts

- [Architecture and pipeline data flow](docs/ARCHITECTURE.md)
- [Validation rules and data contract](docs/DATA_CONTRACT.md)
- [SQL queries and interpretation](docs/SQL_GUIDE.md)
- [GitHub Actions runs](../../actions/workflows/tests.yml) — each successful run also uploads the generated dashboard and report CSVs as a downloadable `synthetic-platform-report` artifact.

## Representative questions answered

- Which pipelines are failing most often?
- How reliable are our pipeline executions, and is the failure rate trending up?
- Which pipelines generate the most support tickets relative to their failures?
- How many data quality findings were detected before KPI aggregation?
- What types of issues appear most often in support tickets?
- How many data/AI use cases are active versus planned?

## Design choices and limitations

- **SQLite** keeps the project runnable without any cloud account. It demonstrates SQL querying, **not Databricks or Azure experience**.
- The example uses a fixed synthetic 30-day time window; it is not connected to live APIs or production jobs.
- Sample CSVs and report files are generated on demand, not tracked in Git, keeping the repository focused on source code and tests.
- Validation rules are **vectorised pandas masks**: each rule is one line, and the check scales to large tables.
- Invalid rows are excluded from aggregated metrics but saved to `data_quality_issues.csv` for investigation. Failed runs with valid data **are** included in reliability metrics.
- Duplicate run IDs: by default the **first otherwise-valid occurrence stays** and extra valid copies are flagged (`keep_first`). Earlier corrupt duplicates remain in the issue log but cannot suppress a later valid row. Use `flag_all` if every copy of a duplicate ID should be flagged.
- Counts of processed records must be whole numbers; fractional and invalid values are logged instead of silently truncated.
- The trend averages available daily rates within the preceding seven calendar days. Dates with no runs are not counted as zero-failure days.
- Data is generated with a fixed random seed to make results reproducible.
- This is not a real-time monitoring solution; it illustrates the workflow and can be extended with ingestion from real, consented sources.

## Ideas for further development

- Add a Streamlit interface with interactive filters.
- Load the demo data into PostgreSQL or Databricks.
- Move quality rules into a configuration file and schedule automated reports.
- Add richer issue-cause categories, e.g. linking ticket categories to failed runs by date.

## License

MIT License. See [LICENSE](LICENSE).