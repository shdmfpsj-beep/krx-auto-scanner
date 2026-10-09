#!/usr/bin/env python3
"""Post-process existing KRX scanner candidates without altering data collection.
No brokerage integration and no trade approvals.
"""
import argparse
import csv
import json
from pathlib import Path


def num(row, key, default=0.0):
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def flag(row, key):
    return str(row.get(key, '')).lower() == 'true'


def clamp(x, low, high):
    return max(low, min(high, x))


def score(row):
    close = num(row, 'close')
    ma20, ma60, ma120 = (num(row, k) for k in ('ma20', 'ma60', 'ma120'))
    rvol = num(row, 'rvol20')
    if min(close, ma20, ma60, ma120) <= 0:
        return None
    extension = close / ma20 - 1
    trend = ma20 > ma60 > ma120
    long_trend = close > ma120 and ma60 > ma120
    setup = ('PULLBACK_PROXY' if flag(row, 'first_pullback_proxy') else
             'BREAKOUT' if flag(row, 'breakout') else
             'REVERSAL_PROXY' if flag(row, 'reversal_proxy') else 'OTHER')
    volume_score = round(15 * clamp((rvol - 0.8) / 2.2, 0, 1))
    geometry = round(25 * clamp((0.20 - abs(extension - 0.04)) / 0.20, 0, 1))
    c3 = (20 if trend else 8 if long_trend else 0) + (20 if flag(row, 'weekly_filter') else 0) + (10 if flag(row, 'monthly_filter') else 0) + volume_score + geometry + (10 if setup == 'PULLBACK_PROXY' else 8 if setup == 'BREAKOUT' else 4 if setup == 'REVERSAL_PROXY' else 0)
    k100 = (30 if trend else 16 if long_trend else 0) + (20 if flag(row, 'weekly_filter') else 0) + (20 if flag(row, 'monthly_filter') else 0) + (10 if close > ma20 else 0) + round(10 * clamp((rvol - 0.5) / 1.5, 0, 1)) + (10 if extension <= 0.08 else 0)
    warnings = []
    if extension > 0.12:
        warnings.append('EXTENDED_GT_12PCT')
    if rvol > 10:
        warnings.append('RVOL_GT_10_VERIFY')
    if rvol < 0.5:
        warnings.append('LOW_RVOL')
    if setup == 'OTHER':
        warnings.append('NO_SETUP')
    # No market-wide cross-check, liquidity, flows or earnings in input CSV.
    warnings.append('PRICE_NOT_CROSS_VERIFIED')
    warnings.append('LIQUIDITY_FLOW_NOT_VERIFIED')
    return {
        'ticker': row.get('ticker', '').zfill(6),
        'latest_date': row.get('latest_date', ''),
        'close_reference': close,
        'setup': setup,
        'c3_preliminary_score': int(clamp(c3, 0, 100)),
        'k100_preliminary_score': int(clamp(k100, 0, 100)),
        'extension_vs_ma20_pct': round(extension * 100, 2),
        'rvol20': rvol,
        'warnings': ';'.join(warnings),
        'trade_approval': 'NO',
        'buy_price': '',
        'stop_price': '',
        'data_source': row.get('data_source', ''),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='reports/candidates.csv')
    parser.add_argument('--output-dir', default='reports')
    args = parser.parse_args()
    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f'Missing input: {path}')
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    ranked = [s for row in rows if (s := score(row)) is not None]
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fields = list(score({'ticker':'000000','close':'1','ma20':'1','ma60':'1','ma120':'1'}).keys())
    for label, key in [('c3', 'c3_preliminary_score'), ('k100', 'k100_preliminary_score')]:
        dest = out / f'{label}_preliminary.csv'
        with dest.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(sorted(ranked, key=lambda r: (-r[key], r['ticker'])))
    summary = {
        'source_rows': len(rows), 'ranked_rows': len(ranked),
        'note': 'Heuristic preliminary ranking, not backtested; NO trade approvals.',
        'limitations': ['Current-listing survivorship bias', 'No independent price reconciliation', 'No turnover/liquidity', 'No institutional/foreign flows', 'No earnings/catalysts', 'No account cash validation'],
        'rvol_gt_10': sum(r['rvol20'] > 10 for r in ranked),
        'extended_gt_12pct': sum(r['extension_vs_ma20_pct'] > 12 for r in ranked),
    }
    (out / 'ranking_status.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
