#!/usr/bin/env python3
"""v6.5: KRX KIND listed-company sector mapping, verified CSV first.

Research diagnostic, NOT sector momentum or trading signals. No OHLCV downloads.
"""
import argparse
import io
import json
import re
from pathlib import Path
import pandas as pd
import requests

KIND = 'https://kind.krx.co.kr/corpgeneral/corpList.do'
MARKETS = ('stockMkt', 'kosdaqMkt')


def code(v):
    s = str(v).strip().removesuffix('.0')
    return s.zfill(6) if s.isdigit() and len(s) <= 6 else s


def parse_listing_bytes(data):
    if len(data) > 12_000_000:
        raise ValueError('Listing response exceeds 12 MB')
    if data[:2] == b'PK':
        df = pd.read_excel(io.BytesIO(data), dtype=str)
    else:
        tables = pd.read_html(io.BytesIO(data), dtype=str)
        matches = [t for t in tables if {'종목코드', '업종'}.issubset(t.columns)]
        if not matches:
            raise ValueError('KIND download does not contain 종목코드 and 업종')
        df = matches[0]
    return normalize(df)


def normalize(df):
    names = {'ticker': ['ticker', '종목코드', 'code', 'symbol'], 'sector': ['sector', '업종', '업종명']}
    cols = {}
    for dest, variants in names.items():
        c = next((x for x in df.columns if str(x).strip().lower() in variants), None)
        if c is None:
            raise ValueError(f'Missing {dest}; available columns: {list(df.columns)[:16]}')
        cols[c] = dest
    d = df.rename(columns=cols)[['ticker', 'sector']].copy()
    d['ticker'] = d['ticker'].map(code)
    d['sector'] = d['sector'].fillna('').astype(str).str.strip()
    return d[d['ticker'].str.fullmatch(r'\d{6}') & d['sector'].ne('')].drop_duplicates()


def fetch_kind():
    frames = []
    for m in MARKETS:
        r = requests.get(KIND, params={
            'method': 'download', 'marketType': m, 'searchType': '13',
            'currentPageSize': '5000', 'pageIndex': '1', 'fiscalYearEnd': 'all',
            'location': 'all'}, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://kind.krx.co.kr/'}, timeout=18)
        r.raise_for_status()
        frames.append(parse_listing_bytes(r.content))
    return pd.concat(frames, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='reports/market_data_v56_merged.csv')
    ap.add_argument('--outdir', default='reports')
    ap.add_argument('--listing', default='', help='Verified KIND export CSV/XLS/HTML; bypass network')
    ap.add_argument('--cache', default='reports/kind_sector_master.csv', help='Previously verified ticker-sector cache')
    args = ap.parse_args()
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    market = pd.read_csv(args.input, dtype={'ticker': str}, encoding='utf-8-sig')
    req = {'ticker', 'market', 'snapshot_date', 'open', 'close', 'volume', 'dated_ohlcv_valid'}
    if not req.issubset(market):
        raise SystemExit('Missing OHLCV columns: ' + str(sorted(req-set(market))))
    market['ticker'] = market['ticker'].map(code)
    market = market[market['dated_ohlcv_valid'].astype(str).str.lower().eq('true') & market['market'].isin(['KOSPI', 'KOSDAQ'])].copy()
    dates = pd.to_datetime(market.snapshot_date, errors='coerce')
    if market.empty or dates.isna().any() or dates.nunique() != 1:
        raise SystemExit('Missing or mixed OHLCV dates')
    audit = {'version': '6.5', 'snapshot_date': str(dates.iloc[0].date()), 'market_rows': len(market),
             'status': 'NO_SECTOR_RANKING', 'mapping_source': None,
             'limitations': ['Current company industry, not historical point-in-time sector',
                             'One-session open-to-close breadth is not 5/20-day strength or fund flow',
                             'KIND company listing may not cover every security in OHLCV universe']}
    try:
        if args.listing:
            p = Path(args.listing)
            if p.suffix.lower() == '.csv':
                mapping = normalize(pd.read_csv(p, dtype=str, encoding='utf-8-sig'))
            elif p.suffix.lower() in ('.xlsx', '.xls'):
                mapping = normalize(pd.read_excel(p, dtype=str))
            else:
                mapping = parse_listing_bytes(p.read_bytes())
            audit['mapping_source'] = 'EXPLICIT_LOCAL_LISTING'
        elif Path(args.cache).is_file():
            mapping = normalize(pd.read_csv(args.cache, dtype=str, encoding='utf-8-sig'))
            audit['mapping_source'] = 'PREVIOUSLY_VERIFIED_CACHE'
        else:
            mapping = fetch_kind()
            audit['mapping_source'] = 'KIND_DOWNLOAD_LIVE'
        conflict = mapping.groupby('ticker')['sector'].nunique()
        ambiguous = set(conflict[conflict > 1].index)
        mapping = mapping[~mapping.ticker.isin(ambiguous)].drop_duplicates('ticker')
        merged = market.merge(mapping, on='ticker', how='left', validate='many_to_one')
        mapped = int(merged.sector.notna().sum()); coverage = mapped/len(merged)*100
        audit.update({'mapped_rows': mapped, 'unmapped_rows': len(merged)-mapped,
                      'coverage_pct': round(coverage, 2), 'ambiguous_tickers': len(ambiguous),
                      'sector_count': int(merged.sector.nunique())})
        if mapped == 0:
            audit['status'] = 'ZERO_COVERAGE_NO_RANKING'
        else:
            for c in ('open', 'close', 'volume'):
                merged[c] = pd.to_numeric(merged[c], errors='coerce')
            merged['open_close_pct'] = (merged.close / merged.open - 1)*100
            merged.loc[(merged.open <= 0) | (merged.close <= 0), 'open_close_pct'] = float('nan')
            merged['turnover_proxy_close_x_volume'] = merged.close*merged.volume
            merged.to_csv(out/'v65_sector_stock_map.csv', index=False, encoding='utf-8-sig')
            good = merged.dropna(subset=['sector'])
            snap = good.groupby('sector').agg(stocks=('ticker','nunique'),
                valid_returns=('open_close_pct','count'), advancers=('open_close_pct',lambda x: int((x>0).sum())),
                mean_open_close_pct=('open_close_pct','mean'), median_open_close_pct=('open_close_pct','median')).reset_index()
            snap['advance_ratio_pct'] = snap.advancers/snap.valid_returns.replace(0,float('nan'))*100
            snap['classification'] = 'DESCRIPTIVE_ONLY_NOT_TRADE_RANKING'
            snap.sort_values(['advance_ratio_pct','mean_open_close_pct'],ascending=False).to_csv(out/'v65_sector_snapshot.csv',index=False,encoding='utf-8-sig')
            audit['status'] = 'DESCRIPTIVE_COVERAGE_OK' if coverage >= 80 else 'LOW_COVERAGE_NOT_FOR_RANKING'
            if audit['mapping_source'] == 'KIND_DOWNLOAD_LIVE' and coverage >= 80:
                mapping.to_csv(args.cache,index=False,encoding='utf-8-sig')
                audit['cache_written'] = args.cache
    except Exception as e:
        audit.update({'status': 'SOURCE_UNAVAILABLE_NO_RANKING', 'error': type(e).__name__ + ': ' + str(e)[:350],
                      'mapped_rows': 0, 'unmapped_rows': len(market)})
    (out/'v65_sector_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
