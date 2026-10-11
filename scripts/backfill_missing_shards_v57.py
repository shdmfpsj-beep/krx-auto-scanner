#!/usr/bin/env python3
"""v5.7: bounded, fail-closed backfill of missing v5.5 dated OHLCV shards.

Run AFTER v5.6.3 merge audit is written. Each selected shard is collected into
an isolated directory and packed as a local artifact ZIP for a SECOND merger
pass. Does not modify the current run's source CSVs or place orders.

Example:
 python scripts/backfill_missing_shards_v57.py --outdir reports --max-shards 2
 python scripts/merge_market_shards_v56.py --outdir reports --offline-artifacts reports/v57_shards/*.zip
"""
import argparse
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

FILES = ('market_data_v52_audit.json', 'market_data_v52.csv',
         'market_data_v54_dated.csv', 'market_data_v54_failures.csv')
KST = timezone(timedelta(hours=9))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='reports')
    p.add_argument('--collector', default='scripts/market_data_collect_v52.py')
    p.add_argument('--max-shards', type=int, default=2)
    p.add_argument('--delay', type=float, default=0.3)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--timeout-seconds', type=int, default=900, help='Per-shard collector timeout')
    a = p.parse_args()
    if not 120 <= a.timeout_seconds <= 1500:
        p.error('--timeout-seconds must be 120..1500')
    if not 1 <= a.max_shards <= 3:
        p.error('--max-shards must be between 1 and 3 (bounded API load)')
    out = Path(a.outdir)
    report = {'version': 'v5.7', 'research_only': True,
              'run_kst': datetime.now(KST).isoformat(),
              'live_buy_approved': 0, 'status': 'NOT_RUN',
              'selected_shards': [], 'successful_shards': [],
              'failed_shards': [], 'warnings': []}
    try:
        merged = json.loads((out/'market_data_v56_merge_audit.json').read_text(encoding='utf-8'))
        current = json.loads((out/'market_data_v52_audit.json').read_text(encoding='utf-8'))
        if current.get('version') != 'v5.5' or not current.get('batch_date'):
            raise ValueError('CURRENT_V55_SHARD_NOT_AVAILABLE')
        if merged.get('batch_date') != current.get('batch_date') or merged.get('universe_count') != current.get('universe_count'):
            raise ValueError('MERGE_AUDIT_DATE_OR_UNIVERSE_MISMATCH')
        if merged.get('shard_count') != current.get('shard_count'):
            raise ValueError('SHARD_LAYOUT_MISMATCH')
        missing = merged.get('missing_shards')
        if not isinstance(missing, list) or any(type(i) is not int or i < 0 or i >= current['shard_count'] for i in missing):
            raise ValueError('INVALID_MISSING_SHARD_LIST')
        # Never backfill an old session with today's StockListing.
        if (datetime.now(KST).date() - datetime.fromisoformat(current['batch_date']).date()).days > 5:
            raise ValueError('SESSION_TOO_OLD_FOR_CURRENT_LISTING_BACKFILL')
        selected = sorted(set(missing))[:a.max_shards]
        report.update(status='DRY_RUN' if a.dry_run else 'IN_PROGRESS',
                      batch_date=current['batch_date'], selected_shards=selected,
                      missing_before=len(missing))
        if a.dry_run:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        shard_dir = out/'v57_shards'
        shard_dir.mkdir(parents=True, exist_ok=True)
        for idx in selected:
            folder = shard_dir/f'shard_{idx:02d}'
            folder.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, a.collector, '--outdir', str(folder),
                   '--shard-index', str(idx), '--batch-size', str(current['batch_size']),
                   '--delay', str(a.delay), '--retries', '1']
            try:
                # One shard is bounded to 120 requests by the collector; cap wall time with configurable timeout.
                proc = subprocess.run(cmd, text=True, capture_output=True, timeout=a.timeout_seconds)
                audit_file = folder/FILES[0]
                if not audit_file.exists():
                    detail = ((proc.stderr or '') + '\n' + (proc.stdout or ''))[-1200:]
                    raise ValueError(f'NO_SHARD_AUDIT exit={proc.returncode} output={detail!r}')
                audit = json.loads(audit_file.read_text(encoding='utf-8'))
                if (audit.get('version') != 'v5.5' or audit.get('batch_date') != current['batch_date']
                    or audit.get('universe_count') != current['universe_count']
                    or audit.get('shard_count') != current['shard_count']
                    or audit.get('shard_index') != idx
                    or audit.get('dated_valid_rows', 0) <= 0):
                    raise ValueError('SHARD_FAILED_OR_METADATA_CHANGED')
                if not all((folder/name).is_file() for name in FILES):
                    raise ValueError('MISSING_SHARD_FILES')
                archive = shard_dir/f'shard_{idx:02d}.zip'
                with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                    for name in FILES:
                        z.write(folder/name, arcname=name)
                report['successful_shards'].append({'index': idx, 'dated_valid_rows': audit['dated_valid_rows'], 'zip': str(archive)})
            except subprocess.TimeoutExpired as exc:
                report['failed_shards'].append({'index': idx, 'error': f'TIMEOUT_AFTER_{a.timeout_seconds}s', 'stdout_tail': str(exc.stdout or b'')[-400:], 'stderr_tail': str(exc.stderr or b'')[-400:]})
            except Exception as exc:
                report['failed_shards'].append({'index': idx, 'error': f'{type(exc).__name__}:{str(exc)[:150]}'})
        report['status'] = 'BACKFILL_PARTIAL_NO_BUY' if report['successful_shards'] else 'BACKFILL_FAILED_NO_BUY'
    except Exception as exc:
        report['status'] = 'BACKFILL_BLOCKED_NO_BUY'
        report['warnings'].append(f'{type(exc).__name__}:{str(exc)[:180]}')
    out.mkdir(parents=True, exist_ok=True)
    (out/'market_data_v57_backfill_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] in ('DRY_RUN', 'BACKFILL_PARTIAL_NO_BUY') else 2

if __name__ == '__main__':
    sys.exit(main())
