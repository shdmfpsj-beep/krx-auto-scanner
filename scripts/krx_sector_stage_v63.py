#!/usr/bin/env python3
"""KRX sector diagnostic with resilient listing fallback; research only."""
import argparse
import json
from pathlib import Path
import pandas as pd


def norm_ticker(value):
    s = str(value).strip().removesuffix('.0')
    return s.zfill(6) if s.isdigit() and len(s) <= 6 else s


def save_audit(out, data):
    (out / 'v63_sector_audit.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(data, ensure_ascii=False, indent=2))


def normalize_listing(df):
    cols = {str(c).lower().strip(): c for c in df.columns}
    id_col = next((cols[k] for k in ('symbol', 'code', 'ticker', '종목코드', '단축코드') if k in cols), None)
    sec_col = next((cols[k] for k in ('sector', '업종', '업종명') if k in cols), None)
    if id_col is None or sec_col is None:
        raise ValueError('No ticker/sector columns: ' + ','.join(map(str, df.columns)))
    result = df[[id_col, sec_col]].rename(columns={id_col: 'ticker', sec_col: 'sector'}).copy()
    result['ticker'] = result['ticker'].map(norm_ticker)
    result['sector'] = result['sector'].fillna('').astype(str).str.strip()
    result = result[result['ticker'].str.fullmatch(r'\d{6}') & result['sector'].ne('')]
    ambiguous = result.groupby('ticker')['sector'].nunique()
    result = result[~result['ticker'].isin(ambiguous[ambiguous > 1].index)]
    return result.drop_duplicates('ticker')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='reports/market_data_v56_merged.csv')
    ap.add_argument('--outdir', default='reports')
    ap.add_argument('--listing', default='', help='Optional saved sector listing CSV')
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    market = pd.read_csv(args.input, dtype={'ticker': str}, encoding='utf-8-sig')
    required = {'ticker', 'name', 'market', 'snapshot_date', 'open', 'close', 'volume', 'dated_ohlcv_valid'}
    if not required.issubset(market.columns):
        raise SystemExit('Missing market fields: ' + str(sorted(required - set(market.columns))))
    market['ticker'] = market['ticker'].map(norm_ticker)
    market = market[market['dated_ohlcv_valid'].astype(str).str.lower().eq('true') & market['market'].isin(['KOSPI', 'KOSDAQ'])].copy()
    if market.empty:
        raise SystemExit('No valid OHLCV rows')
    dates = pd.to_datetime(market['snapshot_date'], errors='coerce')
    if dates.isna().any() or dates.nunique() != 1:
        raise SystemExit('Mixed or invalid market dates')
    session = str(dates.iloc[0].date())
    audit = {'session': session, 'market_rows': len(market), 'status': 'NOT_RANKED', 'limitations': ['One-day open-to-close change is not sector momentum', 'No verified sector money flow, institutional flow, or TOP3 entry signal']}
    attempts = []
    listing = None
    source = None
    if args.listing:
        try:
            listing = normalize_listing(pd.read_csv(args.listing, dtype=str, encoding='utf-8-sig'))
            source = 'LOCAL_FILE:' + args.listing
        except (OSError, ValueError, KeyError) as exc:
            attempts.append('local listing: ' + str(exc)[:250])
    else:
        try:
            import FinanceDataReader as fdr
            for label in ('KRX-DESC', 'KRX'):
                try:
                    candidate = normalize_listing(fdr.StockListing(label))
                    if len(candidate) == 0:
                        raise ValueError('No usable sector rows')
                    listing, source = candidate, 'FinanceDataReader:' + label
                    break
                except Exception as exc:
                    attempts.append(label + ': ' + type(exc).__name__ + ': ' + str(exc)[:180])
        except ImportError as exc:
            attempts.append('FinanceDataReader unavailable: ' + str(exc))
    if listing is None or listing.empty:
        audit.update({'status': 'SECTOR_SOURCE_UNAVAILABLE_NO_RANKING', 'mapping_source': None, 'attempts': attempts, 'mapped_rows': 0, 'unmapped_rows': len(market)})
        save_audit(out, audit)
        print('Sector source unavailable. Skipping sector ranking; no rerun of OHLCV required.')
        return
    market = market.merge(listing, on='ticker', how='left', validate='many_to_one')
    market['sector'] = market['sector'].fillna('UNMAPPED')
    for col in ('open', 'close', 'volume'):
        market[col] = pd.to_numeric(market[col], errors='coerce')
    market['one_day_open_close_pct'] = (market['close'] / market['open'] - 1) * 100
    market.loc[(market['open'] <= 0) | (market['close'] <= 0), 'one_day_open_close_pct'] = float('nan')
    market['close_times_volume_proxy_krw'] = market['close'] * market['volume']
    market.to_csv(out / 'v63_sector_stock_map.csv', index=False, encoding='utf-8-sig')
    mapped = market[market['sector'].ne('UNMAPPED')]
    grouped = mapped.groupby('sector').agg(stocks=('ticker', 'nunique'), advancers=('one_day_open_close_pct', lambda x: int((x > 0).sum())), valid_returns=('one_day_open_close_pct', 'count'), equal_weight_open_close_pct=('one_day_open_close_pct', 'mean'), median_open_close_pct=('one_day_open_close_pct', 'median'), close_times_volume_proxy_krw=('close_times_volume_proxy_krw', 'sum')).reset_index()
    grouped['advance_ratio_pct'] = grouped['advancers'] / grouped['valid_returns'].replace(0, float('nan')) * 100
    grouped['ranking_status'] = 'DESCRIPTIVE_ONLY_NO_MULTI_DAY_SECTOR_STRENGTH'
    grouped.sort_values(['advance_ratio_pct', 'equal_weight_open_close_pct'], ascending=False).to_csv(out / 'v63_sector_snapshot.csv', index=False, encoding='utf-8-sig')
    audit.update({'status': 'SECTOR_MAPPING_DIAGNOSTIC_ONLY', 'mapping_source': source, 'mapping_asof': 'CURRENT_NOT_HISTORICAL', 'mapped_rows': len(mapped), 'unmapped_rows': len(market) - len(mapped), 'coverage_pct': round(100 * len(mapped) / len(market), 2), 'sector_count': len(grouped), 'attempts': attempts})
    save_audit(out, audit)


if __name__ == '__main__':
    main()
