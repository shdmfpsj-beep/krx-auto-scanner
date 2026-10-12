#!/usr/bin/env python3
"""v6.6 sector breadth research: deterministic, one-session, NO trading signals.

Consumes validated v6.5 output only; does not request web data or collect OHLCV.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='reports/v65_sector_stock_map.csv')
    p.add_argument('--outdir', default='reports')
    p.add_argument('--min-members', type=int, default=8)
    a = p.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(a.input, dtype={'ticker':str}, encoding='utf-8-sig')
    required = {'ticker','sector','snapshot_date','open','close','volume','name'}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')
    dates = d['snapshot_date'].dropna().astype(str).unique()
    if len(dates) != 1:
        raise ValueError(f'Expected one snapshot date, got {dates.tolist()}')
    for c in ['open','close','volume']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d['ticker'] = d['ticker'].str.zfill(6)
    d['sector'] = d['sector'].fillna('').astype(str).str.strip()
    d['valid'] = d['open'].gt(0) & d['close'].gt(0) & d['volume'].ge(0)
    d['return_pct'] = np.where(d['valid'], (d['close']/d['open']-1)*100, np.nan)
    # A liquidity *proxy* only; cannot be called actual traded KRW turnover.
    d['proxy_krw'] = np.where(d['valid'], d['close']*d['volume'], np.nan)
    mapped = d[d['sector'].ne('') & d['valid']].copy()
    if mapped['ticker'].duplicated().any():
        raise ValueError('Duplicate tickers; refusing to rank')
    records = []
    for sector, g in mapped.groupby('sector', sort=True):
        n = len(g)
        rising = int((g['return_pct'] > 0).sum())
        declining = int((g['return_pct'] < 0).sum())
        median = float(g['return_pct'].median())
        proxy_sum = float(g['proxy_krw'].sum())
        proxy_top_share = float(g['proxy_krw'].max()/proxy_sum*100) if proxy_sum > 0 else None
        records.append({'sector':sector,'members':n,'rising':rising,'declining':declining,
            'breadth_pct':round(rising/n*100,2),'median_open_close_pct':round(median,3),
            'mean_open_close_pct':round(float(g['return_pct'].mean()),3),
            'top1_proxy_share_pct':round(proxy_top_share,2) if proxy_top_share is not None else None,
            'proxy_close_x_volume_sum':round(proxy_sum),
            'status':'ELIGIBLE_DESCRIPTIVE' if n >= a.min_members else 'TOO_SMALL_FOR_RANKING'})
    sectors = pd.DataFrame.from_records(records)
    if sectors.empty:
        raise ValueError('No sector mapping found; cannot generate report')
    # Only group size >= min; breadth and median as one-day observations, not forecasts.
    eligible = sectors[sectors.status.eq('ELIGIBLE_DESCRIPTIVE')].copy()
    eligible = eligible.sort_values(['breadth_pct','median_open_close_pct','members','sector'],ascending=[False,False,False,True])
    eligible.insert(0,'one_day_observation_rank',range(1,len(eligible)+1))
    sectors.sort_values(['members','sector'],ascending=[False,True]).to_csv(out/'v66_sector_coverage.csv',index=False,encoding='utf-8-sig')
    eligible.to_csv(out/'v66_sector_watchlist.csv',index=False,encoding='utf-8-sig')
    # Expose high-return stocks separately, without implying they're buy candidates.
    solo = d[d['valid']].sort_values(['return_pct','ticker'],ascending=[False,True]).head(30)
    solo[['ticker','name','sector','snapshot_date','return_pct','close','volume','proxy_krw']].to_csv(out/'v66_standalone_observations.csv',index=False,encoding='utf-8-sig')
    audit = {'version':'6.6','snapshot_date':dates[0],'market_rows':len(d),
        'mapped_valid_rows':len(mapped),'sector_count':len(sectors),
        'eligible_sector_count':len(eligible),'excluded_small_sector_count':len(sectors)-len(eligible),
        'minimum_sector_members':a.min_members,
        'status':'ONE_DAY_SECTOR_OBSERVATIONS_ONLY' if len(eligible) else 'NO_ELIGIBLE_SECTORS',
        'limitations':['Industry is current KIND classification, not historical PIT',
            'Only one open-to-close session; not 5/20-day relative strength',
            'Close multiplied by volume is an unverified proxy, not actual traded value',
            'No foreign/institutional flows, no investability verification',
            'Rank is descriptive only; not sector leadership confirmation or TOP3 BUY']}
    (out/'v66_sector_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
