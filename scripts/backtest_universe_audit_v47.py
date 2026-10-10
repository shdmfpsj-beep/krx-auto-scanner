"""v4.7 research-only: current-tier ablation and historic universe evidence audit.
Run: python scripts/backtest_universe_audit_v47.py
Does not certify PIT, alter trading rules, or approve live trading.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--reports', type=Path, default=REPORTS)
    a = p.parse_args()
    folder = a.reports
    src = folder / 'entry_v32_paired_trades.csv'
    if not src.exists():
        raise SystemExit(f'Missing {src}')
    raw = pd.read_csv(src, dtype={'ticker':str,'signal_id':str}, low_memory=False)
    need = {'signal_id','ticker','signal_date','entry_date','hold','setup','rvol20','ret20','distance_ma20'}
    if need-set(raw.columns):
        raise SystemExit(f'Missing columns: {sorted(need-set(raw.columns))}')
    x = raw.loc[pd.to_numeric(raw.hold,errors='coerce').eq(1)].copy()
    if x.signal_id.duplicated().any():
        raise SystemExit('Duplicate hold=1 signal_id; abort')
    x['ticker'] = x.ticker.str.zfill(6)
    for c in ('signal_date','entry_date'):
        x[c] = pd.to_datetime(x[c],errors='coerce')
    for c in ('rvol20','ret20','distance_ma20'):
        x[c] = pd.to_numeric(x[c],errors='coerce')
    if x[['signal_date','entry_date']].isna().any().any():
        raise SystemExit('Invalid dates; abort')
    # Exact v4.0 factor rank formula, with no tier field.
    x['rank_score'] = (np.clip(x.rvol20.fillna(0),0,5)*2
                       +np.clip(x.ret20.fillna(0),-.5,.5)*4
                       -np.clip(x.distance_ma20.fillna(0),-.5,.5)*2)
    x['tier_current'] = x['tier_current'].fillna('MISSING').astype(str) if 'tier_current' in x else 'NOT_PRESENT'
    x['signal_year'] = x.signal_date.dt.year
    # Diagnostic top signal for each entry date, NOT an executable portfolio.
    ordered = x.sort_values(['entry_date','rank_score','ticker'],ascending=[True,False,True],kind='stable')
    winners = ordered.drop_duplicates('entry_date').copy()
    winners['same_day_candidates'] = winners.entry_date.map(x.groupby('entry_date').size())
    winners[['entry_date','signal_id','ticker','tier_current','rank_score','same_day_candidates']].to_csv(
        folder/'pit_v47_daily_top_signals.csv',index=False,encoding='utf-8-sig')
    cohort = x.groupby(['signal_year','tier_current'],dropna=False).agg(
        signals=('signal_id','size'),unique_tickers=('ticker','nunique'),
        median_rank_score=('rank_score','median')).reset_index()
    cohort.to_csv(folder/'pit_v47_tier_cohorts.csv',index=False,encoding='utf-8-sig')
    # Compare the *same* original signals with and without tier column.
    ablated = x.drop(columns=['tier_current']).sort_values(
        ['entry_date','rank_score','ticker'],ascending=[True,False,True],kind='stable').drop_duplicates('entry_date')
    changed = int((winners.set_index('entry_date').signal_id.sort_index()!=
                   ablated.set_index('entry_date').signal_id.sort_index()).sum())
    # Check historical listing membership using only available evidence. A static universe is NOT PIT evidence.
    uni_path = folder/'walkforward_v20_universe.csv'
    static_count = 0
    static_coverage = None
    if uni_path.exists():
        u = pd.read_csv(uni_path,dtype={'Code':str})
        if 'Code' in u:
            static = set(u.Code.str.zfill(6))
            static_count = len(static)
            static_coverage = int(x.ticker.isin(static).sum())
    evidence = pd.DataFrame([
        {'gate':'current_tier_direct_rank_dependency','status':'NO_DIRECT_DEPENDENCY_IN_V40_FORMULA' if changed==0 else 'REVIEW','detail':f'Changed daily top signals after dropping tier column: {changed}; this is only a formula ablation'},
        {'gate':'historic_universe_asof_membership','status':'NOT_VERIFIED','detail':'Static walkforward universe has no effective dates or archived delisted universe'},
        {'gate':'upstream_universe_selection_bias','status':'NOT_VERIFIED','detail':'Same-signal ablation cannot recover securities omitted from the original candidate pool'},
        {'gate':'signal_feature_asof','status':'NOT_VERIFIED','detail':'Recomputed rank from saved feature values, not independently from historical as-of raw bars'},
        {'gate':'survivorship_and_corporate_actions','status':'NOT_VERIFIED','detail':'Historic listings, delistings and as-of adjustment provenance unavailable'},
        {'gate':'independent_holdout','status':'NOT_VERIFIED','detail':'2025 was inspected previously; new untouched data required'},
    ])
    evidence.to_csv(folder/'pit_v47_evidence_gaps.csv',index=False,encoding='utf-8-sig')
    metadata = {'version':'v4.7','status':'RANK_ABLATION_COMPLETE_PIT_NOT_VERIFIED',
                'hold1_signals':len(x),'unique_tickers':int(x.ticker.nunique()),
                'daily_selection_dates':len(winners),'changed_top_signals_after_tier_drop':changed,
                'static_universe_size':static_count,'signals_present_in_static_universe':static_coverage,
                'note':'No portfolio return is inferred. This audit does not re-run historic universe generation.',
                'pit_approved':False,'live_trade_approved':False}
    (folder/'pit_v47_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
