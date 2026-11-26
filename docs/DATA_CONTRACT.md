# Data contract and validation rules

The analyzer expects a `pipeline_runs.csv` containing these columns:

| Column | Meaning | Rule |
|---|---|---|
| `run_id` | Unique execution ID | Nonblank; duplicate handling applies |
| `run_date` | Execution date | Parseable ISO date (`YYYY-MM-DD`) |
| `pipeline` | Pipeline identifier | Nonblank |
| `status` | Operational result | `success` or `failed` |
| `duration_seconds` | Execution duration | Positive, finite, numeric |
| `records_processed` | Output record count | Nonnegative whole number |

The implementation emits a separate finding for each violated rule. Thus a source row with multiple problems appears multiple times in `data_quality_issues.csv`. `row_number` corresponds to the original CSV row, including its header row.

For example, if CSV row 4 has a blank pipeline name and a negative record count, it produces two findings for row 4. To count affected input rows, count distinct `row_number` values in the issue log.

## Duplicate handling

- `--duplicate-policy keep_first` (default): retain the first otherwise-valid occurrence and flag additional otherwise-valid duplicates.
- `--duplicate-policy flag_all`: flag all rows with a repeated nonblank ID.

Any record failing a validation rule is omitted from operational KPI calculations but represented in the issue log.

## CLI failure mode

By default, the CLI reports issues without failing the process.

```bash
python -m monitor.generate
python -m monitor.cli --fail-on-issues
```

When any quality finding exists, `--fail-on-issues` returns exit code **1** so that a scheduler or CI pipeline can reject the dataset. The synthetic demonstration intentionally includes three invalid rows, so this option is expected to fail on the default generated data.

## Limitations

Ticket records and use-case registry records are not subjected to the same row-level validation as pipeline runs. This is an intentional scope limitation of the demo, not an endorsement of skipping validation in production.
