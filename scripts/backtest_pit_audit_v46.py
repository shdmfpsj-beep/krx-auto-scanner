"""C3 v4.6 research-only PIT provenance and leakage audit.

Run from repo root: python scripts/backtest_pit_audit_v46.py
No downloads, orders, strategy changes, or claims of verified point-in-time data.
A structural audit cannot certify historic universe membership or feature computation.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
REQUIRED = ['signal_id','ticker','signal_date','entry_date','entry_open','signal_close',
            'setup','ma_rising','rvol20','ret20','ret60','distance_ma20','hold']
FEATURES = ['rvol20','ret5','ret20','ret60','distance_ma20','distance_ma60',
            'ma_rising','near_prior_60d_high','heat20','heat60','ma20_distance',
            'volume_band','setup','signal_close']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, default=REPORTS/'entry_v32_paired_trades.csv')
    ap.add_argument('--output-dir', type=Path, default=REPORTS)
    args = ap.parse_args()
    if not args.input.is_file():
        raise SystemExit(f'Missing signal file: {args.input}')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    x = pd.read_csv(args.input, dtype={'ticker':'string','signal_id':'string'}, low_memory=False)
    missing = sorted(set(REQUIRED)-set(x.columns))
    if missing:
        raise SystemExit(f'Missing required columns: {missing}')
    raw_rows = len(x)
    x['ticker'] = x.ticker.str.zfill(6)
    for c in ['signal_date','entry_date']:
        x[c] = pd.to_datetime(x[c], errors='coerce')
    for c in ['entry_open','signal_close','rvol20','ret20','ret60','distance_ma20']:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    # v40.load_signals uses hold==1 and one row per signal_id.
    base = x.loc[pd.to_numeric(x.hold,errors='coerce').eq(1)].copy()
    checks = []
    def record(name, severity, count, note):
        checks.append({'check':name,'severity':severity,'affected_rows':int(count),
                       'passed':int(count)==0,'explanation':note})
    record('no_hold_1_signals','error',int(base.empty),'Backtest input must contain hold=1 rows')
    record('invalid_ticker','error',(~base.ticker.str.fullmatch(r'\d{6}',na=False)).sum(),'Six digit numeric ticker required')
    record('missing_or_invalid_dates','error',base[['signal_date','entry_date']].isna().any(axis=1).sum(),'Signal and entry dates must parse')
    record('signal_not_prior_to_entry','error',((base.signal_date>=base.entry_date) & base.signal_date.notna() & base.entry_date.notna()).sum(),'Signal must precede entry')
    record('duplicate_signal_ids','error',base.signal_id.duplicated(keep=False).sum(),'One hold=1 row per signal')
    record('invalid_signal_prices','error',(~(np.isfinite(base.signal_close)&base.signal_close.gt(0))).sum(),'Positive finite prior close required')
    record('invalid_entry_prices','error',(~(np.isfinite(base.entry_open)&base.entry_open.gt(0))).sum(),'Positive finite entry open required')
    record('negative_rvol','error',(base.rvol20.dropna()<0).sum(),'RVOL cannot be negative')
    record('missing_ranking_inputs','warning',base[['rvol20','ret20','distance_ma20']].isna().any(axis=1).sum(),
           'v40 substitutes zero for missing ranking features; flag for review')
    if 'tier_current' in base:
        record('current_tier_present','warning',base.tier_current.notna().sum(),
               'Current size tier is present: historical universe and tier assignments are not independently certified')
    else:
        record('current_tier_present','warning',0,'Current tier absent; this does not prove historical universe correctness')
    if 'year' in base:
        yr = pd.to_numeric(base.year,errors='coerce')
        record('year_signal_mismatch','warning',(yr.notna() & base.signal_date.notna() & yr.ne(base.signal_date.dt.year)).sum(),
               'Year field differs from signal year')
    # Availability provenance: columns are feature values, NOT calculation timestamps.
    provenance = []
    for feature in FEATURES:
        present = feature in base
        provenance.append({'feature':feature,'column_present':present,
                           'feature_asof_timestamp_present':False,
                           'recomputed_from_prior_session_bars':False,
                           'pit_verified':False,
                           'reason':'No feature calculation timestamp or independent as-of source audit in this input'})
    evidence = [
        ('historical_universe_membership','NOT_VERIFIED','Need archived daily listing/universe as-of each signal date, including delisted securities'),
        ('feature_asof_and_formula','NOT_VERIFIED','Need original OHLCV as-of signal date and independent feature recomputation'),
        ('corporate_actions_price_basis','NOT_VERIFIED','Need documented point-in-time split/adjustment basis for source bars'),
        ('signal_generation_timestamp','NOT_VERIFIED','Need archived signal generation time and immutable original candidate snapshots'),
        ('survivorship_bias','NOT_VERIFIED','Need delisted and suspended securities plus historic eligibility filters'),
        ('independent_oos','NOT_VERIFIED','2025 was previously inspected; new untouched forward period required'),
        ('execution_realism','NOT_VERIFIED','Daily OHLCV cannot establish order-book queue or actual limit fills'),
    ]
    pd.DataFrame(checks).to_csv(args.output_dir/'pit_v46_structural_checks.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(provenance).to_csv(args.output_dir/'pit_v46_feature_provenance.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(evidence,columns=['gate','status','required_evidence']).to_csv(
        args.output_dir/'pit_v46_evidence_gaps.csv',index=False,encoding='utf-8-sig')
    cohort = base.assign(signal_year=base.signal_date.dt.year).groupby(
        ['signal_year','setup'],dropna=False).agg(signals=('signal_id','size'),tickers=('ticker','nunique'),
        median_rvol=('rvol20','median')).reset_index()
    cohort.to_csv(args.output_dir/'pit_v46_cohorts.csv',index=False,encoding='utf-8-sig')
    failures = [r for r in checks if r['severity']=='error' and not r['passed']]
    result = {'version':'v4.6','scope':'STRUCTURAL_AUDIT_ONLY',
              'status':'STRUCTURAL_FAILED' if failures else 'STRUCTURAL_PASSED_PIT_NOT_VERIFIED',
              'source':str(args.input),'input_rows':raw_rows,'hold1_rows':len(base),
              'unique_hold1_tickers':int(base.ticker.nunique()),
              'structural_error_checks_failed':len(failures),
              'pit_approved':False,'live_trade_approved':False,
              'limitations':['Historical membership, feature timestamps, survivorship and corporate actions cannot be established from this CSV.',
                             'No independent holdout or real order execution validation.',
                             'This script never changes signals, trading rules, or scheduled scans.']}
    (args.output_dir/'pit_v46_metadata.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    if failures:
        raise SystemExit('Structural audit failed; see pit_v46_structural_checks.csv')

if __name__=='__main__':
    main()
