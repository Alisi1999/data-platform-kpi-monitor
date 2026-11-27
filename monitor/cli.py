"""Run data validation, SQL KPI aggregation, issue triage and HTML reporting."""
from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from monitor.analyze import (
    active_use_cases, daily_failure_trend, load_csvs, pipeline_kpis,
    pipeline_ticket_overview, ticket_summary, validate_runs,
)


def generate_report(input_dir: Path, output_dir: Path,
                    duplicate_policy: str = 'keep_first') -> dict[str, int]:
    runs, tickets, use_cases = load_csvs(input_dir)
    clean_runs, issues = validate_runs(runs, duplicate_policy=duplicate_policy)
    kpis = pipeline_kpis(clean_runs)
    trend = daily_failure_trend(clean_runs)
    overview = pipeline_ticket_overview(clean_runs, tickets)
    ticket_kpis = ticket_summary(tickets)
    active = active_use_cases(use_cases)
    output_dir.mkdir(parents=True, exist_ok=True)

    kpis.to_csv(output_dir / 'pipeline_kpis.csv', index=False)
    issues.to_csv(output_dir / 'data_quality_issues.csv', index=False)
    ticket_kpis.to_csv(output_dir / 'ticket_summary.csv', index=False)
    trend.to_csv(output_dir / 'daily_failure_trend.csv', index=False)
    overview.to_csv(output_dir / 'pipeline_ticket_overview.csv', index=False)
    use_cases.to_csv(output_dir / 'use_case_registry.csv', index=False)

    if not kpis.empty:
        fig, ax = plt.subplots(figsize=(7, 3.1))
        ax.barh(kpis['pipeline'], kpis['success_rate_pct'])
        ax.set_xlim(0, 100)
        ax.set_xlabel('Successful pipeline runs (%)')
        ax.set_title('Pipeline reliability by data product')
        for i, val in enumerate(kpis['success_rate_pct']):
            ax.text(min(float(val)+1, 98), i, f'{val:.1f}%', va='center', fontsize=9)
        fig.tight_layout()
        fig.savefig(output_dir / 'pipeline_reliability.png', dpi=130)
        plt.close(fig)

    total_runs = len(clean_runs)
    total_failed = int(kpis['failed_runs'].sum()) if not kpis.empty else 0
    total_open = int(ticket_kpis['open_tickets'].sum()) if not ticket_kpis.empty else 0
    summary = {
        'valid_runs': total_runs,
        'bad_rows': len(runs) - total_runs,
        'quality_issues': len(issues),
        'failed_runs': total_failed,
        'open_tickets': total_open,
        'active_use_cases': active,
    }
    top_category = str(ticket_kpis.iloc[0]['category']) if len(ticket_kpis) else 'none'
    paragraph = (
        f'Validated {total_runs} pipeline runs and flagged {summary["bad_rows"]} invalid records '
        f'({len(issues)} quality findings). {total_failed} valid runs failed operationally; '
        f'{total_open} support tickets remain open. The most common ticket category is '
        f'{top_category}. {active} registered data/AI use cases are active.'
    )
    (output_dir / 'executive_summary.md').write_text(
        '# Data platform quality and KPI report\n\n'
        '**Synthetic sample data — no actual user or company data.**\n\n'
        + paragraph + '\n\n'
        '## Interpretation\n\nQuality errors are separated from operational failures. '
        'Duplicates and invalid values are excluded from KPI denominators, but remain visible in the findings CSV.\n',
        encoding='utf-8',
    )

    def html_table(frame):
        return frame.to_html(index=False, border=0, escape=True, classes='data-table')

    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Data Platform Ops Monitor</title>
<style>body{{font-family:system-ui,Arial,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;background:#f6f8fb;color:#182638}}h1,h2{{color:#18365b}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}}.metric{{background:white;padding:1.1rem;border-radius:12px;box-shadow:0 1px 5px #ddd}}.metric b{{display:block;font-size:1.7rem;color:#135e90}}section{{margin-top:2rem;background:white;padding:1.2rem;border-radius:12px;overflow-x:auto}}.data-table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #e5e8ee;text-align:left}}th{{background:#edf3fa}}.note{{color:#566575}}</style></head><body>
<h1>Data Platform Ops Monitor</h1><p class="note">Demonstration using synthetic data from monitor/generate.py.</p>
<div class="metrics"><div class="metric">Valid runs<b>{total_runs}</b></div><div class="metric">Flagged rows<b>{summary['bad_rows']}</b></div><div class="metric">Operational failures<b>{total_failed}</b></div><div class="metric">Open tickets<b>{total_open}</b></div><div class="metric">Active use cases<b>{active}</b></div></div>
<section><h2>Pipeline reliability</h2><img style="max-width:100%" alt="Pipeline success rates" src="pipeline_reliability.png"><p>{escape(paragraph)}</p>{html_table(kpis)}</section>
<section><h2>Failures vs. support tickets per pipeline</h2><p>Tickets and failures are aggregated by pipeline, not linked to individual incidents. High counts can help prioritize investigation but do not establish a root cause.</p>{html_table(overview)}</section>
<section><h2>Daily failure trend (7-day rolling average)</h2>{html_table(trend.tail(10))}</section>
<section><h2>Recurring support issues</h2>{html_table(ticket_kpis)}</section>
<section><h2>Data-quality findings</h2><p>Flagged source rows are excluded from aggregated KPIs; investigation remains possible using the CSV.</p>{html_table(issues)}</section>
<section><h2>Data and AI use-case registry</h2>{html_table(use_cases)}</section>
</body></html>'''
    (output_dir / 'dashboard.html').write_text(html, encoding='utf-8')
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate KPI report and browser-viewable dashboard.')
    parser.add_argument('--input', type=Path, default=Path('sample_data'))
    parser.add_argument('--output', type=Path, default=Path('reports'))
    parser.add_argument('--duplicate-policy', choices=('keep_first', 'flag_all'), default='keep_first',
                        help='keep_first: first valid copy stays; flag_all: every duplicate copy is flagged')
    parser.add_argument('--fail-on-issues', action='store_true',
                        help='exit with code 1 if any data-quality issue is found (data contract for CI)')
    args = parser.parse_args(argv)
    metrics = generate_report(args.input, args.output, args.duplicate_policy)
    print(f'Report written to {args.output.resolve()}')
    print(metrics)
    if args.fail_on_issues and metrics['quality_issues'] > 0:
        print(f"Data contract violated: {metrics['quality_issues']} quality issue(s) found.", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
