#!/usr/bin/env python3
"""v6.4 sector mapping: Naver industry directory -> ticker mapping; research only.

No OHLCV redownload. Does not infer fund flow or historical sector strength.
If upstream fails, save audit and no misleading sector ranking.
"""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = 'https://finance.naver.com'
INDEX = BASE + '/sise/sise_group.naver?type=upjong'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; KRX-sector-research/1.0)', 'Referer': BASE + '/'}


def ticker(x):
    s = str(x).strip().removesuffix('.0')
    return s.zfill(6) if s.isdigit() and len(s) <= 6 else s


def get_soup(session, url):
    r = session.get(url, headers=HEADERS, timeout=12)
    r.raise_for_status()
    r.encoding = r.apparent_encoding if r.apparent_encoding and r.apparent_encoding.lower() != 'ascii' else 'euc-kr'
    return BeautifulSoup(r.text, 'html.parser')


def fetch_naver_sectors(max_sectors=140):
    s = requests.Session()
    soup = get_soup(s, INDEX)
    links = {}
    for a in soup.select('a[href]'):
        href = a.get('href', '')
        m = re.search(r'(?:\?|&)no=(\d+)', href)
        if 'sise_group_detail.naver' in href and m:
            name = a.get_text(' ', strip=True)
            if name:
                links[m.group(1)] = (name, urljoin(BASE, href))
    if not links:
        raise RuntimeError('Naver sector directory has no industry links (layout changed or access denied)')
    if len(links) > max_sectors:
        raise RuntimeError(f'Sector directory unexpectedly large ({len(links)} > {max_sectors}); manual review required')
    rows, failures = [], []
    for i, (sid, (sector, url)) in enumerate(sorted(links.items())):
        try:
            page = get_soup(s, url)
            found = set()
            for a in page.select('a[href]'):
                href = a.get('href', '')
                match = re.search(r'(?:\?|&)code=(\d{6})(?:&|$)', href)
                if match and ('item/main.naver' in href or 'item/item' in href):
                    found.add(match.group(1))
            if not found:
                failures.append({'sector': sector, 'reason': 'no_tickers_in_page'})
            for code in found:
                rows.append({'ticker': code, 'sector': sector, 'sector_id': sid})
        except (requests.RequestException, RuntimeError) as e:
            failures.append({'sector': sector, 'reason': type(e).__name__ + ': ' + str(e)[:160]})
        if i < len(links) - 1:
            time.sleep(0.12)
    return pd.DataFrame(rows, columns=['ticker', 'sector', 'sector_id']), len(links), failures


def load_local(path):
    df = pd.read_csv(path, dtype=str, encoding='utf-8-sig')
    aliases = {'ticker': ('ticker', 'code', 'symbol', '종목코드'), 'sector': ('sector', '업종', '업종명')}
    renames = {}
    for dest, candidates in aliases.items():
        key = next((c for c in df.columns if c.strip().lower() in candidates), None)
        if key is None:
            raise ValueError(f'Missing {dest} in sector CSV')
        renames[key] = dest
    return df.rename(columns=renames)[['ticker', 'sector']].copy()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='reports/market_data_v56_merged.csv')
    p.add_argument('--outdir', default='reports')
    p.add_argument('--listing', default='', help='Optional verified CSV ticker,sector; bypasses network')
    args = p.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    market = pd.read_csv(args.input, dtype={'ticker': str}, encoding='utf-8-sig')
    required = {'ticker', 'market', 'snapshot_date', 'open', 'close', 'volume', 'dated_ohlcv_valid'}
    if not required.issubset(market.columns):
        raise SystemExit('Missing columns: ' + str(sorted(required - set(market.columns))))
    market['ticker'] = market['ticker'].map(ticker)
    market = market[market['dated_ohlcv_valid'].astype(str).str.lower().eq('true') & market['market'].isin(['KOSPI', 'KOSDAQ'])].copy()
    dates = pd.to_datetime(market['snapshot_date'], errors='coerce')
    if market.empty or dates.isna().any() or dates.nunique() != 1:
        raise SystemExit('Empty/mixed-date OHLCV snapshot')
    session = str(dates.iloc[0].date())
    audit = {'session': session, 'market_rows': len(market), 'source': 'LOCAL' if args.listing else 'NAVER_FINANCE_INDUSTRY_PAGES', 'status': 'NOT_RANKED', 'limitations': ['Industry classification is current, not as-of historical date', 'Naver industry pages may exclude or overlap instruments', 'One-session breadth is NOT money flow, multi-day relative strength, or buy signal']}
    try:
        if args.listing:
            mapping = load_local(args.listing)
            sector_count = mapping['sector'].nunique()
            failures = []
        else:
            mapping, sector_count, failures = fetch_naver_sectors()
        mapping['ticker'] = mapping['ticker'].map(ticker)
        mapping['sector'] = mapping['sector'].fillna('').astype(str).str.strip()
        mapping = mapping[mapping['ticker'].str.fullmatch(r'\d{6}') & mapping['sector'].ne('')].drop_duplicates(['ticker', 'sector'])
        # A ticker assigned to multiple industries is not silently allocated to one.
        conflict_codes = mapping.groupby('ticker')['sector'].nunique()
        ambiguous = set(conflict_codes[conflict_codes > 1].index)
        mapping = mapping[~mapping['ticker'].isin(ambiguous)].drop_duplicates('ticker')
        market = market.merge(mapping[['ticker', 'sector']], on='ticker', how='left', validate='many_to_one')
        mapped = int(market['sector'].notna().sum())
        coverage = round(mapped / len(market) * 100, 2)
        audit.update({'directory_sectors': int(sector_count), 'failed_sector_pages': failures[:30], 'failed_sector_page_count': len(failures), 'ambiguous_ticker_count': len(ambiguous), 'mapped_rows': mapped, 'unmapped_rows': len(market)-mapped, 'coverage_pct': coverage})
        if mapped == 0 or (not args.listing and failures and len(failures) > sector_count * .25):
            audit['status'] = 'SECTOR_SOURCE_INCOMPLETE_NO_RANKING'
        else:
            for c in ['open', 'close', 'volume']:
                market[c] = pd.to_numeric(market[c], errors='coerce')
            market['open_close_pct'] = (market['close'] / market['open'] - 1) * 100
            market.loc[(market['open'] <= 0) | (market['close'] <= 0), 'open_close_pct'] = float('nan')
            market['turnover_proxy_close_x_volume'] = market['close'] * market['volume']
            market['sector'] = market['sector'].fillna('UNMAPPED')
            market.to_csv(out / 'v64_sector_stock_map.csv', index=False, encoding='utf-8-sig')
            good = market[market['sector'].ne('UNMAPPED')]
            summary = good.groupby('sector').agg(stocks=('ticker', 'nunique'), valid_returns=('open_close_pct', 'count'), advancers=('open_close_pct', lambda x: int((x > 0).sum())), mean_open_close_pct=('open_close_pct', 'mean'), median_open_close_pct=('open_close_pct', 'median')).reset_index()
            summary['advance_ratio_pct'] = 100 * summary['advancers'] / summary['valid_returns'].replace(0, float('nan'))
            summary['classification'] = 'DESCRIPTIVE_ONE_SESSION_ONLY'
            summary.sort_values(['advance_ratio_pct', 'mean_open_close_pct'], ascending=False).to_csv(out / 'v64_sector_snapshot.csv', index=False, encoding='utf-8-sig')
            audit['status'] = 'MAPPED_DESCRIPTIVE_ONLY' if coverage >= 80 else 'LOW_COVERAGE_DESCRIPTIVE_ONLY'
    except Exception as e:
        audit.update({'status': 'SECTOR_SOURCE_UNAVAILABLE_NO_RANKING', 'error': type(e).__name__ + ': ' + str(e)[:350], 'mapped_rows': 0, 'unmapped_rows': len(market)})
    (out / 'v64_sector_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if audit['status'].endswith('NO_RANKING'):
        print('No sector ranking generated; do not repeat failed source automatically.')


if __name__ == '__main__':
    main()
