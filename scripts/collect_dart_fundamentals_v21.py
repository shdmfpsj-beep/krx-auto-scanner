"""C3 v2.1: Open DART historical filing/financial data feasibility collector.
Research only. Does not modify trading scanners or approve live trading.
Usage: python scripts/collect_dart_fundamentals_v21.py --limit 5 --start-year 2023 --end-year 2025
Requires GitHub Actions secret OPEN_DART_API_KEY.
"""
import argparse
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'https://opendart.fss.or.kr/api'
REPORTS = {'11013': 'Q1', '11012': 'H1', '11014': 'Q3', '11011': 'FY'}


def get_json(session, endpoint, params):
    response = session.get(f'{BASE}/{endpoint}.json', params=params, timeout=35)
    response.raise_for_status()
    obj = response.json()
    status = obj.get('status', 'unknown')
    if status not in ('000', '013'):
        raise RuntimeError(f'{endpoint}: DART status {status}: {obj.get("message", "")}')
    return obj


def corp_map(session, key):
    response = session.get(f'{BASE}/corpCode.xml', params={'crtfc_key': key}, timeout=90)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        xml_name = next(n for n in archive.namelist() if n.lower().endswith('.xml'))
        root = ET.fromstring(archive.read(xml_name))
    mapping = {}
    for item in root.findall('.//list'):
        code = (item.findtext('stock_code') or '').strip()
        corp = (item.findtext('corp_code') or '').strip()
        if re.fullmatch(r'\d{6}', code) and re.fullmatch(r'\d{8}', corp):
            mapping[code] = corp
    return mapping


def sample_codes(limit):
    path = OUT / 'walkforward_v20_universe.csv'
    if path.exists():
        frame = pd.read_csv(path, dtype={'Code': str})
        if 'Code' in frame.columns:
            return [(str(v).zfill(6), str(n)) for v, n in zip(
                frame.Code, frame['Name'] if 'Name' in frame else frame.Code
            )][:limit]
    # Fallback only when the prior sampled-universe report does not exist.
    import FinanceDataReader as fdr
    frame = fdr.StockListing('KRX')
    frame = frame[frame['Market'].isin(['KOSPI', 'KOSDAQ'])]
    frame = frame[frame.Code.astype(str).str.fullmatch(r'\d{6}')]
    return [(str(row.Code), str(row.Name)) for row in frame.head(limit).itertuples()]


def filings(session, key, corp, start_year, end_year):
    # Include 2022 reports released in 2023 and 2025 reports released in 2026.
    params = {'crtfc_key': key, 'corp_code': corp,
              'bgn_de': f'{start_year}0101', 'end_de': f'{end_year + 1}1231',
              'pblntf_ty': 'A', 'page_count': 100, 'page_no': 1,
              'last_reprt_at': 'N'}
    items = []
    while True:
        obj = get_json(session, 'list', params)
        if obj.get('status') == '013':
            break
        items.extend(obj.get('list', []))
        if int(params['page_no']) >= int(obj.get('total_page', 1)):
            break
        params['page_no'] += 1
        time.sleep(.15)
    return items


def report_info(report_name):
    # Accept originals only; corrections are recorded but excluded from this initial
    # feasibility study because the financial API can expose the latest correction.
    if '기재정정' in report_name or '첨부정정' in report_name or '정정' in report_name:
        return None
    for label, code in [('사업보고서', '11011'), ('반기보고서', '11012'),
                        ('분기보고서', '11013')]:
        if label not in report_name:
            continue
        m = re.search(r'\((\d{4})\.(\d{2})\)', report_name)
        if not m:
            return None
        year, month = int(m.group(1)), int(m.group(2))
        if code == '11011' and month == 12:
            return year, code
        if code == '11012' and month == 6:
            return year, code
        if code == '11013' and month in (3, 9):
            return year, '11013' if month == 3 else '11014'
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--start-year', type=int, default=2023)
    parser.add_argument('--end-year', type=int, default=2025)
    args = parser.parse_args()
    if args.limit < 1 or args.start_year > args.end_year:
        raise ValueError('Invalid arguments')
    key = os.environ.get('OPEN_DART_API_KEY', '').strip()
    if not key:
        raise RuntimeError('Missing OPEN_DART_API_KEY GitHub Actions secret')
    session = requests.Session()
    session.headers['User-Agent'] = 'C3-research-feasibility/2.1'
    mapping = corp_map(session, key)
    codes = sample_codes(args.limit)
    filings_out, accounts_out, errors = [], [], []
    for idx, (ticker, name) in enumerate(codes, 1):
        corp = mapping.get(ticker)
        if not corp:
            errors.append({'ticker': ticker, 'stage': 'mapping', 'error': 'corp code unavailable'})
            continue
        try:
            found = filings(session, key, corp, args.start_year, args.end_year)
        except Exception as exc:
            errors.append({'ticker': ticker, 'stage': 'filings', 'error': str(exc)[:200]})
            continue
        seen = set()
        for filing in found:
            report_name = str(filing.get('report_nm', ''))
            parsed = report_info(report_name)
            receipt = str(filing.get('rcept_dt', ''))
            receipt_no = str(filing.get('rcept_no', ''))
            if not parsed or not re.fullmatch(r'\d{8}', receipt):
                continue
            year, report_code = parsed
            if not args.start_year - 1 <= year <= args.end_year:
                continue
            identity = (year, report_code)
            if identity in seen:
                continue
            seen.add(identity)
            base = {'ticker': ticker, 'name': name, 'corp_code': corp,
                    'business_year': year, 'report_code': report_code,
                    'period': REPORTS[report_code], 'receipt_date': receipt,
                    'receipt_no': receipt_no, 'report_name': report_name}
            filings_out.append(base)
            try:
                data = get_json(session, 'fnlttSinglAcnt', {
                    'crtfc_key': key, 'corp_code': corp,
                    'bsns_year': year, 'reprt_code': report_code})
                if data.get('status') == '013':
                    errors.append({'ticker': ticker, 'stage': f'financial_{year}_{report_code}',
                                   'error': 'no financial statement data'})
                    continue
                rows = data.get('list', [])
                for item in rows:
                    # API result may represent latest revisions. Never claim these
                    # values were the original figures known on receipt_date.
                    accounts_out.append({**base,
                        'financial_api_rcept_no': str(item.get('rcept_no', '')),
                        'fs_div': item.get('fs_div', ''),
                        'sj_div': item.get('sj_div', ''),
                        'account_nm': item.get('account_nm', ''),
                        'thstrm_amount': item.get('thstrm_amount', ''),
                        'thstrm_add_amount': item.get('thstrm_add_amount', ''),
                        'frmtrm_amount': item.get('frmtrm_amount', ''),
                        'currency': item.get('currency', ''),
                        'pit_verified': False})
            except Exception as exc:
                errors.append({'ticker': ticker, 'stage': f'financial_{year}_{report_code}',
                               'error': str(exc)[:200]})
            time.sleep(.16)
        print(f'DART processed {idx}/{len(codes)}: {ticker}', flush=True)
    for filename, records in [('filings', filings_out), ('accounts', accounts_out),
                              ('errors', errors)]:
        pd.DataFrame(records).to_csv(OUT / f'dart_v21_{filename}.csv',
                                     index=False, encoding='utf-8-sig')
    summary = {'version': 'C3 v2.1 DART feasibility',
               'run_utc': datetime.utcnow().isoformat() + 'Z',
               'sample_requested': len(codes), 'mapped_corporations': sum(c in mapping for c, _ in codes),
               'filings': len(filings_out), 'financial_account_rows': len(accounts_out),
               'errors': len(errors), 'pit_financial_values_verified': False,
               'backtest_or_trading_enabled': False,
               'warning': 'Original receipt dates collected, but financial API may show revised figures; '
                          'do not use for PIT backtest until revision matching is verified.'}
    (OUT / 'dart_v21_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
