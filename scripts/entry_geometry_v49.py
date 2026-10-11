#!/usr/bin/env python3
"""C3 v4.9: research-only stock-direction and entry-geometry snapshot.
No orders, no live buy signals. Requires reports/candidates.csv.
"""
import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def num(row, key):
    try:
        v = float(row.get(key, ''))
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def yes(v):
    return str(v).strip().lower() in ('true', '1', 'yes')


def evaluate(r):
    close, ma20, ma60, ma120, rvol = (num(r, k) for k in ('close', 'ma20', 'ma60', 'ma120', 'rvol20'))
    if not all(v is not None and v > 0 for v in (close, ma20, ma60, ma120)):
        return None
    distance = (close / ma20 - 1) * 100
    trend = close > ma60 and ma20 >= ma60 and yes(r.get('weekly_filter')) and yes(r.get('monthly_filter'))
    direction = 0
    direction += 25 if close > ma60 else 0
    direction += 20 if ma20 >= ma60 else 0
    direction += 15 if yes(r.get('weekly_filter')) else 0
    direction += 15 if yes(r.get('monthly_filter')) else 0
    direction += 15 if (rvol is not None and 1 <= rvol <= 5) else 0
    direction += 10 if (num(r, 'turnover_krw') or 0) >= 2_000_000_000 else 0
    # A proxy, not an actual execution-level technical signal.
    if 0 <= distance <= 2.5:
        geometry = 85
        setup = 'MA20_NEAR_SUPPORT_PROXY'
    elif -2.5 <= distance < 0:
        geometry = 70
        setup = 'BELOW_MA20_WAIT_RECLAIM'
    elif 2.5 < distance <= 5:
        geometry = 45
        setup = 'EXTENDED_WAIT_PULLBACK'
    else:
        geometry = 15
        setup = 'NO_CHASE_OR_TREND_BREAK'
    if not trend:
        geometry = min(geometry, 30)
    if yes(r.get('breakout')) and distance > 5:
        geometry = min(geometry, 15)
    # No OHLCV intraday/sector flow/true supports: never produce a BUY instruction.
    return {
        'snapshot_date': r.get('latest_date', ''),
        'ticker': r.get('ticker', ''), 'name': r.get('name', ''),
        'close': int(close) if close.is_integer() else close,
        'ma20': round(ma20, 2), 'ma60': round(ma60, 2),
        'rvol20': round(rvol, 2) if rvol is not None else '',
        'distance_ma20_pct': round(distance, 2),
        'direction_score': direction, 'entry_geometry_score': geometry,
        'setup_proxy': setup,
        'decision': 'WATCH_VERIFY' if trend and geometry >= 70 else 'WAIT_NO_CHASE',
        'ideal_buy': 'UNVERIFIED', 'max_buy': 'UNVERIFIED',
        'no_chase': 'UNVERIFIED', 'structural_stop': 'UNVERIFIED',
        'risk_reward': 'UNVERIFIED',
        'sector_flow': 'MISSING', 'foreign_institution_flow': 'MISSING',
        'intraday_confirmation': 'MISSING',
        'turnover_source': r.get('turnover_source', ''),
        'notes': 'Research proxy only; no verified support, executable prices, or real-time signal',
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='reports/candidates.csv')
    ap.add_argument('--outdir', default='reports')
    ap.add_argument('--top', type=int, default=20)
    a = ap.parse_args()
    src = Path(a.input)
    if not src.is_file():
        raise SystemExit(f'Missing candidate input: {src}')
    with src.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit('Empty candidate input')
    required = {'ticker', 'close', 'ma20', 'ma60', 'ma120', 'latest_date'}
    if not required.issubset(rows[0]):
        raise SystemExit(f'Missing columns: {sorted(required - set(rows[0]))}')
    evaluated = [v for r in rows if (v := evaluate(r)) is not None]
    if not evaluated:
        raise SystemExit('No valid candidates')
    evaluated.sort(key=lambda r: (r['direction_score'] >= 75 and r['entry_geometry_score'] >= 70,
                                  r['entry_geometry_score'], r['direction_score']), reverse=True)
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cols = list(evaluated[0])
    with (outdir / 'entry_geometry_v49.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(evaluated[:max(1, a.top)])
    dates = sorted({r['snapshot_date'] for r in evaluated})
    report = {
        'version': 'v4.9', 'research_only': True, 'live_approval': False,
        'status': 'DIRECTION_AND_ENTRY_PROXY_ONLY',
        'source': str(src), 'source_snapshot_dates': dates,
        'evaluated': len(evaluated), 'exported': min(len(evaluated), max(1, a.top)),
        'caveats': [
            'Candidates may be a prefiltered universe; not independently PIT-verified',
            'Latest input date may be stale; not real-time quotes',
            'No sector breadth or true money-flow data; turnover may be estimated',
            'MA20 proximity is not verified support or entry trigger',
            'No price levels or BUY signals are authorized by this report',
            'Forward outcomes require separately captured future market prices',
        ],
    }
    (outdir / 'entry_geometry_v49_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
