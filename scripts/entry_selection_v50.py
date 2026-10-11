#!/usr/bin/env python3
"""C3 v5.0 research-only: instrument eligibility before trend and entry ranking.

No network calls, no trades, no executable price levels. Unknown instrument
classification stays unverified, never silently upgraded to ordinary shares.
"""
import argparse
import csv
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

SPECIAL = re.compile(r'(?:스팩|SPAC|기업인수목적|ETF|ETN|리츠|REIT|인버스|레버리지|선물|우선주|우B$|우C$|\d+우B$)', re.I)
PREFERRED = re.compile(r'(?:우$|우B$|우C$|\d+우B$|\d+우C$)', re.I)


def number(row, key):
    try:
        x = float(row.get(key, ''))
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def flag(x):
    return str(x).strip().lower() in ('true', 'yes', '1')


def instrument(row):
    name = str(row.get('name', '')).strip()
    raw = str(row.get('instrument_type', '')).strip().upper()
    if SPECIAL.search(name) or PREFERRED.search(name):
        return 'EXCLUDE_SPECIAL_NAME', 'name indicates SPAC/preferred/fund/other special instrument'
    if raw in {'NON_COMMON_OR_SPECIAL', 'SPAC', 'ETF', 'ETN', 'PREFERRED', 'REIT', 'NON_COMMON'}:
        return 'EXCLUDE_SOURCE_TYPE', f'source instrument_type={raw}'
    if raw in {'COMMON', 'COMMON_STOCK', 'ORDINARY_SHARE', 'ORDINARY'}:
        return 'COMMON_SOURCE_ONLY', 'source labels common; independent verification pending'
    return 'UNKNOWN_VERIFY', 'ordinary-share status not verified'


def evaluate(row):
    ticker = str(row.get('ticker', '')).strip().zfill(6)
    close, ma20, ma60, ma120 = (number(row, k) for k in ('close', 'ma20', 'ma60', 'ma120'))
    rvol = number(row, 'rvol20')
    status, evidence = instrument(row)
    valid = all(v is not None and v > 0 for v in (close, ma20, ma60, ma120))
    weekly, monthly = flag(row.get('weekly_filter')), flag(row.get('monthly_filter'))
    trend = bool(valid and close > ma60 and ma20 >= ma60 and weekly and monthly)
    direction = (25 * bool(valid and close > ma60) + 20 * bool(valid and ma20 >= ma60)
                 + 15 * weekly + 15 * monthly + 15 * bool(rvol is not None and 1 <= rvol <= 5))
    # Estimated close*volume is NOT treated as independently verified turnover.
    turnover = number(row, 'turnover_krw')
    turnover_source = str(row.get('turnover_source', '')).strip().upper()
    turnover_verified = turnover is not None and turnover >= 2_000_000_000 and turnover_source in {
        'EXCHANGE_REPORTED', 'KRX_REPORTED', 'PYKRX_REPORTED', 'VERIFIED_EXCHANGE'
    }
    direction += 10 * turnover_verified
    distance = (close / ma20 - 1) * 100 if valid else None
    if distance is None:
        geometry, setup = 0, 'INVALID_PRICE_DATA'
    elif 0 <= distance <= 2.5:
        geometry, setup = 85, 'MA20_NEAR_SUPPORT_PROXY'
    elif -2.5 <= distance < 0:
        geometry, setup = 70, 'BELOW_MA20_WAIT_RECLAIM'
    elif 2.5 < distance <= 5:
        geometry, setup = 45, 'EXTENDED_WAIT_PULLBACK'
    else:
        geometry, setup = 15, 'NO_CHASE_OR_TREND_BREAK'
    if not trend:
        geometry = min(geometry, 30)
    if flag(row.get('breakout')) and distance is not None and distance > 5:
        geometry = min(geometry, 15)
    # Eligibility precedes technical ranking. Even a strong setup is only a watch candidate.
    if status.startswith('EXCLUDE'):
        decision = 'EXCLUDE'
    elif not valid or not trend:
        decision = 'WAIT_DIRECTION'
    elif geometry < 70:
        decision = 'WAIT_ENTRY'
    else:
        decision = 'WATCH_VERIFY_INSTRUMENT' if status == 'UNKNOWN_VERIFY' else 'WATCH_VERIFY_FLOW_AND_TRIGGER'
    return {
        'snapshot_date': row.get('latest_date', ''), 'ticker': ticker, 'name': row.get('name', ''),
        'instrument_status': status, 'instrument_evidence': evidence,
        'source_instrument_type': row.get('instrument_type', ''),
        'direction_score': direction, 'entry_geometry_score': geometry,
        'setup_proxy': setup, 'distance_ma20_pct': round(distance, 2) if distance is not None else '',
        'close': close if close is not None else '', 'ma20': ma20 if ma20 is not None else '',
        'ma60': ma60 if ma60 is not None else '', 'rvol20': rvol if rvol is not None else '',
        'turnover_krw': turnover if turnover is not None else '',
        'turnover_source': row.get('turnover_source', ''),
        'turnover_verified': turnover_verified,
        'decision': decision,
        'ideal_buy': 'UNVERIFIED', 'max_buy': 'UNVERIFIED', 'no_chase': 'UNVERIFIED',
        'structural_stop': 'UNVERIFIED', 'forward_rr': 'UNVERIFIED',
        'sector_money_flow': 'MISSING', 'foreign_institution_flow': 'MISSING',
        'intraday_entry_trigger': 'MISSING', 'live_buy_approved': False,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='reports/candidates.csv')
    ap.add_argument('--outdir', default='reports')
    ap.add_argument('--top', type=int, default=20)
    args = ap.parse_args()
    with Path(args.input).open(encoding='utf-8-sig', newline='') as f:
        source = list(csv.DictReader(f))
    if not source:
        raise SystemExit('Empty candidates file')
    required = {'ticker', 'name', 'latest_date', 'close', 'ma20', 'ma60', 'ma120'}
    if not required.issubset(source[0]):
        raise SystemExit('Missing columns: ' + ','.join(sorted(required - set(source[0]))))
    rows = [evaluate(x) for x in source]
    priority = {'WATCH_VERIFY_FLOW_AND_TRIGGER': 0, 'WATCH_VERIFY_INSTRUMENT': 1,
                'WAIT_ENTRY': 2, 'WAIT_DIRECTION': 3, 'EXCLUDE': 4}
    rows.sort(key=lambda r: (priority[r['decision']], -r['direction_score'],
                             -r['entry_geometry_score'], r['ticker']))
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    for name, data in [('entry_selection_v50_all.csv', rows),
                       ('entry_selection_v50_top.csv', [r for r in rows if r['decision'] != 'EXCLUDE'][:max(1, args.top)])]:
        with (out / name).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
    summary = {
        'version': 'v5.0', 'status': 'RESEARCH_ONLY_NO_LIVE_BUY',
        'source': args.input, 'source_dates': sorted({r['snapshot_date'] for r in rows}),
        'evaluated': len(rows), 'instrument_counts': dict(Counter(r['instrument_status'] for r in rows)),
        'decision_counts': dict(Counter(r['decision'] for r in rows)),
        'buy_approved': 0, 'independent_common_share_verification': False,
        'limitations': [
            'Name and source-type exclusion is conservative but not a complete KRX security-master check',
            'UNKNOWN is never assumed to be common stock',
            'Turnover estimated as close times volume does not prove real money flow',
            'No sector breadth, verified institutional flow, intraday trigger, or executable price levels',
            'The candidate input may be stale and prefiltered; no full-market coverage guarantee',
            'No live orders or changes to C3/K100 portfolio rules',
        ],
    }
    (out / 'entry_selection_v50_audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
