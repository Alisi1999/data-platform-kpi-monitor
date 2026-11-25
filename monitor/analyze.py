"""Validate pipeline events and calculate useful KPIs with SQL and pandas."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

import pandas as pd

REQUIRED_RUN_COLUMNS = {
    'run_id', 'run_date', 'pipeline', 'status', 'duration_seconds', 'records_processed'
}
REQUIRED_TICKET_COLUMNS = {'ticket_id', 'opened_date', 'pipeline', 'category', 'status'}
VALID_STATUSES = {'success', 'failed'}
ISSUE_COLUMNS = ['row_number', 'run_id', 'issue']

DuplicatePolicy = Literal['keep_first', 'flag_all']


def _blank(values: pd.Series) -> pd.Series:
    """True where a value is missing or only whitespace."""
    return values.astype('string').str.strip().fillna('').eq('')


def validate_runs(
    runs: pd.DataFrame, duplicate_policy: DuplicatePolicy = 'keep_first'
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (valid_rows, detected_issues). No bad records are silently dropped.

    Each quality rule is a vectorised boolean mask over the whole table, so adding
    a rule is one line. With ``duplicate_policy='keep_first'`` the first occurrence
    of a run_id stays valid and only the extra copies are flagged; ``'flag_all'``
    flags every copy (useful when you cannot tell which copy is correct).
    The first *valid* occurrence wins, so a corrupt earlier row cannot suppress
    a valid later row with the same ID.
    """
    # CSV row_number represents the physical row number, not the DataFrame index.
    runs = runs.reset_index(drop=True)
    missing = REQUIRED_RUN_COLUMNS - set(runs.columns)
    if missing:
        raise ValueError(f'Missing required pipeline columns: {sorted(missing)}')
    if duplicate_policy not in ('keep_first', 'flag_all'):
        raise ValueError(f'Unknown duplicate_policy: {duplicate_policy}')

    run_id = runs['run_id'].astype('string').str.strip()
    duration = pd.to_numeric(runs['duration_seconds'], errors='coerce')
    records = pd.to_numeric(runs['records_processed'], errors='coerce')
    dates = pd.to_datetime(runs['run_date'], errors='coerce', format='%Y-%m-%d')
    rules: dict[str, pd.Series] = {
        'missing_run_id': _blank(runs['run_id']),
        'invalid_run_date': dates.isna(),
        'invalid_status': ~runs['status'].isin(VALID_STATUSES),
        'missing_pipeline': _blank(runs['pipeline']),
        'invalid_duration': duration.isna() | (duration <= 0) | (duration == float('inf')),
        # Row counts must be nonnegative whole numbers; never truncate 3.5 to 3.
        'invalid_record_count': records.isna() | (records < 0) | (records % 1 != 0),
    }
    if duplicate_policy == 'keep_first':
        candidates = ~pd.concat(rules, axis=1).any(axis=1)
        duplicate = pd.Series(False, index=runs.index)
        duplicate.loc[candidates] = run_id.loc[candidates].duplicated(keep='first')
    else:
        duplicate = ~rules['missing_run_id'] & run_id.duplicated(keep=False)
    rules['duplicate_run_id'] = duplicate

    issues = [
        pd.DataFrame({
            'row_number': mask[mask].index + 2,  # +2: header row and 1-based numbering
            'run_id': runs.loc[mask, 'run_id'].astype(str).values,
            'issue': name,
        })
        for name, mask in rules.items() if mask.any()
    ]
    issue_df = (pd.concat(issues, ignore_index=True).sort_values(['row_number', 'issue'])
                .reset_index(drop=True) if issues else pd.DataFrame(columns=ISSUE_COLUMNS))

    flagged = pd.concat(rules, axis=1).any(axis=1)
    good = runs.loc[~flagged].copy()
    good['duration_seconds'] = duration[~flagged]
    good['records_processed'] = records[~flagged].astype('int64')
    return good.reset_index(drop=True), issue_df


def _sql(query: str, **tables: pd.DataFrame) -> pd.DataFrame:
    """Load DataFrames into an in-memory SQLite database and run one query."""
    with sqlite3.connect(':memory:') as db:
        for name, frame in tables.items():
            frame.to_sql(name, db, index=False, if_exists='replace')
        return pd.read_sql_query(query, db)


def pipeline_kpis(good: pd.DataFrame) -> pd.DataFrame:
    """Operational KPIs per pipeline, calculated with a SQL aggregation."""
    if good.empty:
        return pd.DataFrame(columns=['pipeline', 'total_runs', 'failed_runs', 'success_rate_pct',
                                     'avg_duration_seconds', 'max_duration_seconds', 'records_processed'])
    return _sql('''
        SELECT pipeline,
               COUNT(*) AS total_runs,
               SUM(status = 'failed') AS failed_runs,
               ROUND(100.0 * SUM(status = 'success') / COUNT(*), 1) AS success_rate_pct,
               ROUND(AVG(duration_seconds), 1) AS avg_duration_seconds,
               MAX(duration_seconds) AS max_duration_seconds,
               SUM(records_processed) AS records_processed
        FROM pipeline_runs
        GROUP BY pipeline
        ORDER BY success_rate_pct ASC, pipeline ASC
    ''', pipeline_runs=good)


def daily_failure_trend(good: pd.DataFrame) -> pd.DataFrame:
    """Daily failure rate with an observed-day average within 7 calendar days."""
    if good.empty:
        return pd.DataFrame(columns=['run_date', 'runs', 'failed_runs', 'failure_rate_pct',
                                     'failure_rate_7d_avg_pct'])
    return _sql('''
        WITH daily AS (
            SELECT run_date,
                   COUNT(*) AS runs,
                   SUM(status = 'failed') AS failed_runs
            FROM pipeline_runs
            GROUP BY run_date
        )
        SELECT run_date, runs, failed_runs,
               ROUND(100.0 * failed_runs / runs, 1) AS failure_rate_pct,
               ROUND(AVG(100.0 * failed_runs / runs)
                     OVER (ORDER BY julianday(run_date) RANGE BETWEEN 6 PRECEDING AND CURRENT ROW), 1)
                   AS failure_rate_7d_avg_pct
        FROM daily
        ORDER BY run_date
    ''', pipeline_runs=good)


def pipeline_ticket_overview(good: pd.DataFrame, tickets: pd.DataFrame) -> pd.DataFrame:
    """Join run failures with support tickets per pipeline to point at root causes."""
    _require(tickets, REQUIRED_TICKET_COLUMNS, 'ticket')
    columns = ['pipeline', 'total_runs', 'failed_runs', 'tickets', 'open_tickets', 'tickets_per_failure']
    if good.empty:
        return pd.DataFrame(columns=columns)
    return _sql('''
        WITH runs AS (
            SELECT pipeline, COUNT(*) AS total_runs, SUM(status = 'failed') AS failed_runs
            FROM pipeline_runs GROUP BY pipeline
        ), t AS (
            SELECT pipeline, COUNT(*) AS tickets, SUM(status = 'open') AS open_tickets
            FROM tickets GROUP BY pipeline
        )
        SELECT r.pipeline, r.total_runs, r.failed_runs,
               COALESCE(t.tickets, 0) AS tickets,
               COALESCE(t.open_tickets, 0) AS open_tickets,
               ROUND(1.0 * COALESCE(t.tickets, 0) / NULLIF(r.failed_runs, 0), 2) AS tickets_per_failure
        FROM runs AS r
        LEFT JOIN t ON t.pipeline = r.pipeline
        ORDER BY tickets DESC, failed_runs DESC, r.pipeline
    ''', pipeline_runs=good, tickets=tickets)


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f'Missing {label} columns: {sorted(missing)}')


def ticket_summary(tickets: pd.DataFrame) -> pd.DataFrame:
    _require(tickets, REQUIRED_TICKET_COLUMNS, 'ticket')
    if tickets.empty:
        return pd.DataFrame(columns=['category', 'tickets', 'open_tickets'])
    grouped = tickets.assign(open_tickets=(tickets['status'] == 'open').astype(int))
    return (grouped.groupby('category', as_index=False)
            .agg(tickets=('ticket_id', 'count'), open_tickets=('open_tickets', 'sum'))
            .sort_values(['tickets', 'category'], ascending=[False, True]).reset_index(drop=True))


def active_use_cases(use_cases: pd.DataFrame) -> int:
    _require(use_cases, {'use_case_id', 'status'}, 'use case')
    return int((use_cases['status'] == 'active').sum())


def load_csvs(directory: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return tuple(pd.read_csv(directory / name) for name in (
        'pipeline_runs.csv', 'tickets.csv', 'use_case_registry.csv'
    ))
