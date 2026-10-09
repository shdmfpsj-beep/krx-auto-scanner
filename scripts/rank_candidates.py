#!/usr/bin/env python3
"""KRX preliminary C3/K100 ranking v2.0. No order execution or trade approvals.

Reads existing reports/candidates.csv without changing the upstream collector.
Scores are *technical screening points*, not probabilities or validated returns.
"""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

FIELDS = [
    'ticker', 'latest_date', 'close_reference', 'setup',
    'c3_preliminary_score', 'k100_preliminary_score',
    'extension_vs_ma20_pct', 'rvol20', 'instrument_type',
    'eligibility', 'warnings', 'trade_approval', 'buy_price',
    'stop_price', 'data_source',
]


def num(row, key, default=None):
    try:
        value = float(row.get(key, ''))
        return value if math.isfinite(value) else default
    except (ValueError, TypeError):
        return default


def flag(row, key):
    return str(row.get(key, '')).strip().lower() in ('true', '1', 'yes')


def clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def instrument(row):
    # Use explicit source metadata only; a 6-digit ticker alone cannot identify a stock.
    raw = str(row.get('instrument_type') or row.get('security_type') or row.get('market_type') or '').strip().upper()
    if not raw:
        return 'UNKNOWN'
    if any(word in raw for word in ('ETF', 'ETN', 'SPAC', 'REIT', '우선주', 'PREFERRED', 'FUND', '리츠', '스팩')):
        return 'NON_COMMON_OR_SPECIAL'
    if raw in ('COMMON', 'COMMON_STOCK', '보통주'):
        return 'COMMON_STOCK'
    return 'UNKNOWN'


def score(row):
    close, ma20, ma60, ma120 = [num(row, k) for k in ('close', 'ma20', 'ma60', 'ma120')]
    if any(x is None or x <= 0 for x in (close, ma20, ma60, ma120)):
        return None
    rvol = num(row, 'rvol20', 0)
    ext = close / ma20 - 1
    trend = ma20 > ma60 > ma120
    long_trend = close > ma120 and ma60 > ma120
    weekly, monthly = flag(row, 'weekly_filter'), flag(row, 'monthly_filter')
    setup = ('PULLBACK_PROXY' if flag(row, 'first_pullback_proxy') else
             'BREAKOUT' if flag(row, 'breakout') else
             'REVERSAL_PROXY' if flag(row, 'reversal_proxy') else 'OTHER')

    # Scores capped below 100 because earnings, money flow, and true setup
    # validation are unavailable in the input. Avoid false precision.
    c3 = 0
    c3 += 18 if trend else 8 if long_trend else 0
    c3 += 12 if weekly else 0
    c3 += 8 if monthly else 0
    c3 += {'PULLBACK_PROXY': 14, 'BREAKOUT': 11, 'REVERSAL_PROXY': 5, 'OTHER': 0}[setup]
    c3 += round(16 * clamp((rvol - 0.8) / 2.2))
    c3 += round(17 * clamp(1 - abs(ext - 0.025) / 0.13))
    # Distinguish a calm pullback from an overextended breakout.
    c3 -= round(25 * clamp((ext - 0.10) / 0.20))
    if rvol > 10:
        c3 -= 12
    if rvol < 0.5:
        c3 -= 10

    k100 = 0
    k100 += 22 if trend else 10 if long_trend else 0
    k100 += 13 if weekly else 0
    k100 += 13 if monthly else 0
    k100 += 8 if close > ma20 else 0
    k100 += round(10 * clamp((rvol - 0.5) / 2.0))
    k100 += round(12 * clamp(1 - abs(ext - 0.03) / 0.16))
    k100 += 6 if close > ma60 else 0
    k100 -= round(15 * clamp((ext - 0.12) / 0.20))
    if rvol > 10:
        k100 -= 8
    if rvol < 0.5:
        k100 -= 5

    kind = instrument(row)
    warnings = []
    if kind == 'UNKNOWN':
        warnings.append('INSTRUMENT_TYPE_UNKNOWN')
    elif kind == 'NON_COMMON_OR_SPECIAL':
        warnings.append('NON_COMMON_OR_SPECIAL_INSTRUMENT')
    if ext > 0.12:
        warnings.append('EXTENDED_GT_12PCT')
    if rvol > 10:
        warnings.append('RVOL_GT_10_VERIFY')
    if rvol < 0.5:
        warnings.append('LOW_RVOL')
    if setup == 'OTHER':
        warnings.append('NO_SETUP')
    if setup == 'PULLBACK_PROXY':
        warnings.append('FIRST_PULLBACK_NOT_CONFIRMED')
    warnings.extend(['PRICE_NOT_CROSS_VERIFIED', 'LIQUIDITY_FLOW_NOT_VERIFIED',
                     'EARNINGS_CATALYST_NOT_VERIFIED'])
    ticker = str(row.get('ticker', '')).strip().zfill(6)
    return {
        'ticker': ticker, 'latest_date': row.get('latest_date', ''),
        'close_reference': close, 'setup': setup,
        'c3_preliminary_score': int(clamp(c3, 0, 85)),
        'k100_preliminary_score': int(clamp(k100, 0, 85)),
        'extension_vs_ma20_pct': round(ext * 100, 2),
        'rvol20': rvol, 'instrument_type': kind,
        'eligibility': 'EXCLUDE' if kind == 'NON_COMMON_OR_SPECIAL' else 'REVIEW',
        'warnings': ';'.join(warnings), 'trade_approval': 'NO',
        'buy_price': '', 'stop_price': '',
        'data_source': row.get('data_source', ''),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='reports/candidates.csv')
    parser.add_argument('--output-dir', default='reports')
    args = parser.parse_args()
    path = Path(args.input)
    if not path.is_file():
        raise SystemExit(f'Missing input: {path}')
    with path.open(encoding='utf-8-sig', newline='') as f:
        source = list(csv.DictReader(f))
    ranked = [item for row in source if (item := score(row)) is not None]
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for label, field in [('c3', 'c3_preliminary_score'), ('k100', 'k100_preliminary_score')]:
        with (output / f'{label}_preliminary.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(sorted(ranked, key=lambda x: (x['eligibility'] == 'EXCLUDE', -x[field], x['ticker'])))
    summary = {
        'version': '2.0', 'source_rows': len(source), 'ranked_rows': len(ranked),
        'instrument_type_counts': dict(Counter(x['instrument_type'] for x in ranked)),
        'excluded_special_instruments': sum(x['eligibility'] == 'EXCLUDE' for x in ranked),
        'unverified_instrument_types': sum(x['instrument_type'] == 'UNKNOWN' for x in ranked),
        'rvol_gt_10': sum(x['rvol20'] > 10 for x in ranked),
        'extended_gt_12pct': sum(x['extension_vs_ma20_pct'] > 12 for x in ranked),
        'trade_approvals': 0,
        'note': 'Technical-only preliminary ranks; scores are not win probabilities. No trade approvals.',
        'limitations': ['Current-listing survivorship bias', 'No independent price reconciliation',
                        'No verified turnover or liquidity', 'No institutional/foreign flows',
                        'No earnings/catalysts', 'No account cash validation',
                        'First-pullback flag is only a proxy',
                        'Unknown instrument types require source metadata'],
    }
    (output / 'ranking_status.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
