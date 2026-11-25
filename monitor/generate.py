"""Create reproducible, entirely synthetic data for the platform monitor."""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

PIPELINES = ('catalog-sync', 'inventory-refresh', 'search-index', 'price-feed')
ISSUE_TYPES = ('missing-field', 'delayed-feed', 'schema-change', 'permission', 'timeout')


def generate(output: Path, seed: int = 42, end_date: str = '2026-11-25') -> None:
    rng = np.random.default_rng(seed)
    output.mkdir(parents=True, exist_ok=True)
    end = pd.Timestamp(end_date)
    days = pd.date_range(end - pd.Timedelta(days=29), end, freq='D')
    runs = []
    seq = 1
    for day in days:
        for pipeline in PIPELINES:
            for _ in range(2):
                failed = bool(rng.random() < 0.105)
                runs.append({
                    'run_id': f'RUN-{seq:04d}',
                    'run_date': day.strftime('%Y-%m-%d'),
                    'pipeline': pipeline,
                    'status': 'failed' if failed else 'success',
                    'duration_seconds': round(float(rng.uniform(30, 360)), 1),
                    'records_processed': int(rng.integers(200, 15000)) if not failed else 0,
                })
                seq += 1
    # Inject realistic QA issues, deliberately excluded from valid KPI calculations.
    runs.append({**runs[0]})                         # Duplicate run ID
    runs.append({**runs[1], 'run_id': 'RUN-BAD-1', 'records_processed': -7})
    runs.append({**runs[2], 'run_id': 'RUN-BAD-2', 'status': 'unknown'})
    pd.DataFrame(runs).to_csv(output / 'pipeline_runs.csv', index=False)

    tickets = []
    for idx in range(1, 51):
        tickets.append({
            'ticket_id': f'TKT-{idx:03d}',
            'opened_date': (end - pd.Timedelta(days=int(rng.integers(0, 30)))).strftime('%Y-%m-%d'),
            'pipeline': str(rng.choice(PIPELINES)),
            'category': str(rng.choice(ISSUE_TYPES)),
            'status': str(rng.choice(('open', 'resolved'), p=(0.3, 0.7))),
        })
    pd.DataFrame(tickets).to_csv(output / 'tickets.csv', index=False)

    use_cases = pd.DataFrame([
        ('UC-01', 'Product search ranking', 'AI', 'active', 'Search'),
        ('UC-02', 'Pipeline performance monitoring', 'Analytics', 'active', 'Platform'),
        ('UC-03', 'Catalog data validation', 'Analytics', 'active', 'Catalog'),
        ('UC-04', 'Automated ticket classification', 'AI', 'planned', 'Platform'),
        ('UC-05', 'Demand trend reporting', 'Analytics', 'planned', 'Planning'),
    ], columns=['use_case_id', 'name', 'type', 'status', 'owner_team'])
    use_cases.to_csv(output / 'use_case_registry.csv', index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate synthetic platform operations data.')
    parser.add_argument('--output', type=Path, default=Path('sample_data'))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--end-date', default='2026-11-25')
    args = parser.parse_args()
    generate(args.output, args.seed, args.end_date)
    print(f'Created synthetic CSVs in {args.output.resolve()}')


if __name__ == '__main__':
    main()
