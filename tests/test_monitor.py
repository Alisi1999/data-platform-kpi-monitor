from pathlib import Path

import pandas as pd
import pytest

from monitor.analyze import (
    daily_failure_trend, pipeline_kpis, pipeline_ticket_overview, ticket_summary, validate_runs,
)
from monitor.cli import generate_report, main
from monitor.generate import generate


def _run(run_id, status='success', date='2026-11-24', pipeline='catalog', duration=10, records=100):
    return {'run_id': run_id, 'run_date': date, 'pipeline': pipeline, 'status': status,
            'duration_seconds': duration, 'records_processed': records}


def test_detects_duplicate_invalid_status_and_negative_count():
    runs = pd.DataFrame([
        _run('a'), _run('a', duration=11, records=120),
        _run('b', status='broken', records=-1), _run('c', status='failed', records=0),
    ])
    valid, issues = validate_runs(runs)
    # keep_first: the first 'a' stays valid, only the extra copy is flagged
    assert list(valid.run_id) == ['a', 'c']
    assert {'duplicate_run_id', 'invalid_status', 'invalid_record_count'} <= set(issues.issue)


def test_flag_all_policy_excludes_every_duplicate_copy():
    runs = pd.DataFrame([_run('a'), _run('a'), _run('c')])
    valid, issues = validate_runs(runs, duplicate_policy='flag_all')
    assert list(valid.run_id) == ['c']
    assert (issues.issue == 'duplicate_run_id').sum() == 2


@pytest.mark.parametrize('bad, expected', [
    ({'date': 'not-a-date'}, 'invalid_run_date'),
    ({'duration': 'abc'}, 'invalid_duration'),
    ({'duration': 0}, 'invalid_duration'),
    ({'records': 'n/a'}, 'invalid_record_count'),
    ({'pipeline': '   '}, 'missing_pipeline'),
])
def test_single_rule_violations(bad, expected):
    valid, issues = validate_runs(pd.DataFrame([_run('x', **bad), _run('y')]))
    assert list(valid.run_id) == ['y']
    assert list(issues.issue) == [expected]


def test_missing_run_id_is_flagged_not_treated_as_duplicate():
    runs = pd.DataFrame([_run(None), _run(None), _run('ok')])
    valid, issues = validate_runs(runs)
    assert list(valid.run_id) == ['ok']
    assert set(issues.issue) == {'missing_run_id'}


def test_kpis_are_sql_computed_and_failure_is_not_data_error():
    frame = pd.DataFrame([
        {'pipeline': 'feed', 'status': 'success', 'duration_seconds': 10, 'records_processed': 100},
        {'pipeline': 'feed', 'status': 'failed', 'duration_seconds': 20, 'records_processed': 0},
    ])
    result = pipeline_kpis(frame).iloc[0]
    assert int(result['total_runs']) == 2
    assert int(result['failed_runs']) == 1
    assert result['success_rate_pct'] == 50.0
    assert result['avg_duration_seconds'] == 15.0
    assert result['max_duration_seconds'] == 20


def test_daily_trend_uses_rolling_window():
    frame = pd.DataFrame([
        _run('1', date='2026-11-01', status='failed'), _run('2', date='2026-11-01'),
        _run('3', date='2026-11-02'), _run('4', date='2026-11-02'),
    ])
    trend = daily_failure_trend(frame)
    assert list(trend.failure_rate_pct) == [50.0, 0.0]
    assert list(trend.failure_rate_7d_avg_pct) == [50.0, 25.0]


def test_ticket_overview_joins_and_handles_pipelines_without_tickets():
    runs = pd.DataFrame([_run('1', pipeline='p1', status='failed'), _run('2', pipeline='p2')])
    tickets = pd.DataFrame([
        {'ticket_id': 't1', 'opened_date': '2026-11-24', 'pipeline': 'p1', 'category': 'timeout', 'status': 'open'},
        {'ticket_id': 't2', 'opened_date': '2026-11-24', 'pipeline': 'p1', 'category': 'timeout', 'status': 'resolved'},
    ])
    overview = pipeline_ticket_overview(runs, tickets).set_index('pipeline')
    assert overview.loc['p1', 'tickets'] == 2 and overview.loc['p1', 'tickets_per_failure'] == 2.0
    assert overview.loc['p2', 'tickets'] == 0 and pd.isna(overview.loc['p2', 'tickets_per_failure'])


def test_ticket_triage_summary():
    tickets = pd.DataFrame([
        {'ticket_id': 't1', 'opened_date': '2026-11-24', 'pipeline': 'p1', 'category': 'timeout', 'status': 'open'},
        {'ticket_id': 't2', 'opened_date': '2026-11-24', 'pipeline': 'p1', 'category': 'timeout', 'status': 'resolved'},
    ])
    result = ticket_summary(tickets)
    assert int(result.loc[0, 'tickets']) == 2
    assert int(result.loc[0, 'open_tickets']) == 1


def test_empty_input_produces_empty_outputs():
    empty = pd.DataFrame(columns=list(_run('x')))
    valid, issues = validate_runs(empty)
    assert valid.empty and issues.empty
    assert pipeline_kpis(valid).empty and daily_failure_trend(valid).empty


def test_end_to_end_generates_reproducible_artifacts(tmp_path: Path):
    data, reports = tmp_path / 'data', tmp_path / 'reports'
    generate(data, seed=42, end_date='2026-11-25')
    result = generate_report(data, reports)
    assert result['bad_rows'] == 3
    assert result['valid_runs'] > 200
    for name in ('pipeline_kpis.csv', 'data_quality_issues.csv', 'ticket_summary.csv',
                 'daily_failure_trend.csv', 'pipeline_ticket_overview.csv',
                 'dashboard.html', 'executive_summary.md', 'pipeline_reliability.png'):
        assert (reports / name).exists(), name
    assert 'synthetic' in (reports / 'dashboard.html').read_text().lower()


def test_fail_on_issues_returns_nonzero_exit_code(tmp_path: Path):
    data = tmp_path / 'data'
    generate(data, seed=42, end_date='2026-11-25')
    assert main(['--input', str(data), '--output', str(tmp_path / 'r1')]) == 0
    assert main(['--input', str(data), '--output', str(tmp_path / 'r2'), '--fail-on-issues']) == 1


def test_missing_columns_fail_loudly():
    with pytest.raises(ValueError, match='Missing required'):
        validate_runs(pd.DataFrame([{'run_id': 'x'}]))


def test_invalid_earlier_duplicate_does_not_discard_valid_later_copy():
    data = pd.DataFrame([_run('same', status='broken'), _run('same'), _run('other')])
    valid, issues = validate_runs(data)
    assert list(valid.run_id) == ['same', 'other']
    assert list(issues.issue) == ['invalid_status']


def test_fractional_record_counts_are_rejected_not_truncated():
    valid, issues = validate_runs(pd.DataFrame([_run('bad', records=3.5), _run('good', records=3)]))
    assert list(valid.run_id) == ['good']
    assert list(issues.issue) == ['invalid_record_count']


def test_validation_row_numbers_are_positional_not_dataframe_index():
    frame = pd.DataFrame([_run('bad', date='not-a-date'), _run('good')], index=['alpha', 'beta'])
    valid, issues = validate_runs(frame)
    assert list(valid.run_id) == ['good']
    assert list(issues.row_number) == [2]


def test_calendar_rolling_window_does_not_include_gaps_over_seven_days():
    frame = pd.DataFrame([
        _run('day1', date='2026-11-01', status='failed'),
        _run('day30', date='2026-11-30'),
    ])
    trend = daily_failure_trend(frame)
    assert list(trend.failure_rate_pct) == [100.0, 0.0]
    assert list(trend.failure_rate_7d_avg_pct) == [100.0, 0.0]
