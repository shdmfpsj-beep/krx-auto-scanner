#!/usr/bin/env python3
"""Sector mapping and one-session breadth audit; research only, never a BUY signal."""
import argparse
import json
from pathlib import Path
import pandas as pd


def ticker(s):
    s = str(s).strip().removesuffix('.0')
    return s.zfill(6) if s.isdigit() and len(s) <= 6 else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='reports/market_data_v56_merged.csv')
    ap.add_argument('--outdir', default='reports')
    ap.add_argument('--listing', default='', help='Optional saved KRX-DESC listing CSV')
    args = ap.parse_args()
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    market = pd.read_csv(args.input, dtype={'ticker': str}, encoding='utf-8-sig')
    required = {'ticker','name','market','snapshot_date','open','close','volume','dated_ohlcv_valid'}
    if not required.issubset(market.columns):
        raise SystemExit('Missing market fields: '+str(sorted(required-set(market.columns))))
    market['ticker'] = market.ticker.map(ticker)
    market = market[market['dated_ohlcv_valid'].astype(str).str.lower().eq('true')].copy()
    market = market[market['market'].isin(['KOSPI','KOSDAQ'])]
    market['snapshot_date'] = pd.to_datetime(market.snapshot_date, errors='coerce')
    if market.snapshot_date.isna().any() or market.snapshot_date.nunique()!=1:
        raise SystemExit('Mixed or invalid market dates: refusing sector ranking')
    session = str(market.snapshot_date.iloc[0].date())
    if args.listing:
        listing = pd.read_csv(args.listing, dtype=str, encoding='utf-8-sig')
        source = args.listing
    else:
        import FinanceDataReader as fdr
        listing = fdr.StockListing('KRX-DESC')
        source = 'FinanceDataReader.StockListing(KRX-DESC) current listing'
    aliases = {c.lower().strip(): c for c in listing.columns}
    idcol = next((aliases[k] for k in ('symbol','code','ticker') if k in aliases), None)
    seccol = next((aliases[k] for k in ('sector','업종') if k in aliases), None)
    if not idcol or not seccol:
        raise SystemExit('Listing lacks ticker or sector field: '+str(list(listing.columns)))
    listing = listing[[idcol,seccol]].rename(columns={idcol:'ticker',seccol:'sector'})
    listing['ticker'] = listing.ticker.map(ticker)
    listing['sector'] = listing.sector.fillna('').astype(str).str.strip()
    listing = listing[listing.sector.ne('') & listing.ticker.str.fullmatch(r'\d{6}')]
    # Ambiguous sector labels are excluded rather than silently choosing one.
    ambiguous = listing.groupby('ticker').sector.nunique()
    listing = listing[~listing.ticker.isin(ambiguous[ambiguous>1].index)].drop_duplicates('ticker')
    m = market.merge(listing, on='ticker', how='left', validate='many_to_one')
    m['sector'] = m.sector.fillna('UNMAPPED')
    m['open'] = pd.to_numeric(m.open,errors='coerce')
    m['close'] = pd.to_numeric(m.close,errors='coerce')
    m['volume'] = pd.to_numeric(m.volume,errors='coerce')
    m['one_day_return_pct'] = ((m.close/m.open)-1)*100
    m.loc[(m.open<=0)|(m.close<=0),'one_day_return_pct'] = float('nan')
    m['turnover_proxy_krw'] = m.close*m.volume
    # Proxy is NOT verified traded value; not suitable for money-flow inference.
    m.to_csv(out/'v63_sector_stock_map.csv',index=False,encoding='utf-8-sig')
    valid = m[m.sector.ne('UNMAPPED')].copy()
    sectors = valid.groupby('sector').agg(stocks=('ticker','nunique'),advancers=('one_day_return_pct',lambda x:(x>0).sum()),valid_returns=('one_day_return_pct','count'),equal_weight_open_close_pct=('one_day_return_pct','mean'),median_open_close_pct=('one_day_return_pct','median'),close_times_volume_proxy_krw=('turnover_proxy_krw','sum')).reset_index()
    sectors['advance_ratio_pct'] = sectors.advancers/sectors.valid_returns.replace(0,float('nan'))*100
    sectors['ranking_status'] = 'DESCRIPTIVE_ONLY_NO_MULTI_DAY_SECTOR_STRENGTH'
    sectors = sectors.sort_values(['advance_ratio_pct','equal_weight_open_close_pct'],ascending=False)
    sectors.to_csv(out/'v63_sector_snapshot.csv',index=False,encoding='utf-8-sig')
    audit = {'session':session,'market_rows':len(m),'mapped_rows':len(valid),'unmapped_rows':len(m)-len(valid),'coverage_pct':round(100*len(valid)/len(m),2) if len(m) else 0,'sector_count':len(sectors),'mapping_source':source,'mapping_asof':'CURRENT_LISTING_NOT_HISTORICAL_PIT','status':'SECTOR_MAPPING_DIAGNOSTIC_ONLY','limitations':['Sector classifications may have changed since market session','Only one daily OHLCV snapshot: cannot compute 5/20-day sector relative strength, rotation, or capital inflow','close*volume is not verified traded turnover','No verified stock tradability, corporate actions, investor flows or news','No TOP3 and no entry/stop signals produced']}
    (out/'v63_sector_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
