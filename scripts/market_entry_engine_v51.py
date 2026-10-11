#!/usr/bin/env python3
"""v5.1 C3/K100 market evidence and entry-quality gate. Research-only.

Uses reports/candidates.csv, optional reports/market_evidence_v51.csv, and
optional reports/entry_levels_v51.csv. Never upgrades unverified values to BUY.
No network, broker actions, or guessed prices. Safe to run on old report sets.
"""
import argparse
import csv
import json
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from entry_selection_v50 import evaluate


def read_csv(path):
    if not path.is_file():
        return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def yes(value):
    return str(value).strip().lower() in ('true', '1', 'yes', 'y', 'verified')


def ticker(value):
    return str(value).strip().zfill(6)


def indexed(rows):
    return {ticker(r.get('ticker')): r for r in rows if str(r.get('ticker', '')).strip()}


def fresh(snapshot, asof, max_age):
    try:
        d = date.fromisoformat(str(snapshot)[:10])
        age = (asof - d).days
        return 0 <= age <= max_age, age
    except ValueError:
        return False, None


def check(row, evidence, levels, asof, max_age):
    base = evaluate(row)
    code = base['ticker']
    ev = evidence.get(code, {})
    lv = levels.get(code, {})
    reasons = []
    is_fresh, age = fresh(row.get('latest_date'), asof, max_age)
    if not is_fresh:
        reasons.append('STALE_OR_INVALID_SNAPSHOT')
    if base['instrument_status'] != 'COMMON_SOURCE_ONLY':
        reasons.append('COMMON_STOCK_NOT_CONFIRMED')
    if not yes(ev.get('common_verified')):
        reasons.append('NO_INDEPENDENT_SECURITY_MASTER')
    if base['decision'] not in {'WATCH_VERIFY_INSTRUMENT', 'WATCH_VERIFY_FLOW_AND_TRIGGER'}:
        reasons.append('DIRECTION_OR_ENTRY_GATE_FAILED')
    if not yes(ev.get('turnover_verified')) or (num(ev.get('turnover_krw')) or 0) < 2_000_000_000:
        reasons.append('NO_VERIFIED_TURNOVER')
    if not yes(ev.get('sector_breadth_verified')) or (num(ev.get('sector_breadth_pct')) is None):
        reasons.append('NO_VERIFIED_SECTOR_BREADTH')
    if not yes(ev.get('relative_strength_verified')) or (num(ev.get('relative_strength')) is None):
        reasons.append('NO_VERIFIED_RELATIVE_STRENGTH')
    if not yes(ev.get('trigger_verified')):
        reasons.append('NO_VERIFIED_ENTRY_TRIGGER')
    if not yes(lv.get('levels_verified')):
        reasons.append('NO_VERIFIED_PRICE_LEVELS')
    ideal, max_buy, no_chase, stop, target = [num(lv.get(k)) for k in
        ('ideal_buy', 'max_buy', 'no_chase', 'structural_stop', 'target')]
    rr = None
    if all(x is not None and x > 0 for x in (ideal, max_buy, no_chase, stop, target)):
        # Conservative R:R: worst permitted entry, not optimistic ideal entry.
        risk, reward = max_buy - stop, target - max_buy
        if not (stop < ideal <= max_buy <= no_chase < target and risk > 0):
            reasons.append('INVALID_PRICE_GEOMETRY')
        else:
            rr = round(reward / risk, 3)
            if rr < 2:
                reasons.append('RR_BELOW_2')
    else:
        reasons.append('PRICE_LEVELS_MISSING')
    # Inputs are external annotations; source freshness and time provenance must be explicit.
    if ev and (not ev.get('asof') or not ev.get('source')):
        reasons.append('MARKET_EVIDENCE_PROVENANCE_MISSING')
    if lv and (not lv.get('asof') or not lv.get('source')):
        reasons.append('LEVEL_PROVENANCE_MISSING')
    # No live BUY: intraday quotes, broker orderable cash, and fill feasibility
    # are not authenticated by these CSV files.
    status = 'RESEARCH_READY_NOT_LIVE_BUY' if not reasons else 'WAIT_DATA_OR_SETUP'
    return {
        'ticker': code, 'name': row.get('name', ''), 'snapshot_date': row.get('latest_date', ''),
        'age_calendar_days': age if age is not None else '',
        'instrument_status': base['instrument_status'],
        'direction_score': base['direction_score'], 'entry_score': base['entry_geometry_score'],
        'setup_proxy': base['setup_proxy'], 'sector': ev.get('sector', ''),
        'verified_turnover_krw': ev.get('turnover_krw', '') if yes(ev.get('turnover_verified')) else '',
        'sector_breadth_pct': ev.get('sector_breadth_pct', '') if yes(ev.get('sector_breadth_verified')) else '',
        'relative_strength': ev.get('relative_strength', '') if yes(ev.get('relative_strength_verified')) else '',
        'ideal_buy': ideal if yes(lv.get('levels_verified')) and ideal is not None else '',
        'max_buy': max_buy if yes(lv.get('levels_verified')) and max_buy is not None else '',
        'no_chase': no_chase if yes(lv.get('levels_verified')) and no_chase is not None else '',
        'structural_stop': stop if yes(lv.get('levels_verified')) and stop is not None else '',
        'target': target if yes(lv.get('levels_verified')) and target is not None else '',
        'forward_rr': rr if rr is not None else '',
        'status': status, 'blocking_reasons': '|'.join(dict.fromkeys(reasons)),
        'live_buy_approved': False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='reports/candidates.csv')
    p.add_argument('--evidence', default='reports/market_evidence_v51.csv')
    p.add_argument('--levels', default='reports/entry_levels_v51.csv')
    p.add_argument('--outdir', default='reports')
    p.add_argument('--asof', default=date.today().isoformat())
    p.add_argument('--max-calendar-age', type=int, default=5)
    args = p.parse_args()
    asof = date.fromisoformat(args.asof)
    rows = read_csv(Path(args.input))
    if not rows:
        raise SystemExit('No candidate rows; run full_scan first or provide candidates.csv')
    evidence = indexed(read_csv(Path(args.evidence)))
    levels = indexed(read_csv(Path(args.levels)))
    results = [check(r, evidence, levels, asof, args.max_calendar_age) for r in rows]
    results.sort(key=lambda r: (r['status'] != 'RESEARCH_READY_NOT_LIVE_BUY',
                                -r['direction_score'], -r['entry_score'], r['ticker']))
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'market_entry_v51_all.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    counts = Counter(reason for r in results for reason in r['blocking_reasons'].split('|') if reason)
    audit = {'version': 'v5.1', 'status': 'RESEARCH_ONLY', 'asof': args.asof,
             'total_candidates': len(results), 'market_evidence_rows': len(evidence),
             'entry_level_rows': len(levels),
             'research_ready': sum(r['status'] == 'RESEARCH_READY_NOT_LIVE_BUY' for r in results),
             'live_buy_approved': 0, 'blocking_reasons': dict(counts),
             'limitations': ['Existing candidates are prefiltered, not full-market coverage',
                             'Optional evidence CSV is not automatically verified against exchanges',
                             'MA20 proximity is a setup proxy, not a confirmed support',
                             'No intraday order book, brokerage cash, or verified fills',
                             'No automatic live orders or portfolio-rule changes']}
    (out / 'market_entry_v51_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
