#!/usr/bin/env python3
"""Audit exact KRX share type and existing KIND sector snapshot. No orders.

Snapshot cleanup is an exploratory sensitivity for old signals. It does NOT
retroactively establish historical common-stock/non-biotech eligibility.
Unknown sector vintage prevents live review readiness even after cleanup.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import pandas as pd

PHARMA_BIO = re.compile(r'의약|생물|생명공학|의학\s*및\s*약학|자연과학.*연구')


def classify(info, sector):
    if not info:
        return False, 'NO_OFFICIAL_ISSUER_RECORD'
    if info.get('security_group') != '주권' or info.get('share_kind') != '보통주':
        return False, 'NOT_EXPLICIT_COMMON_EQUITY'
    name=str(info.get('name',''))
    if re.search(r'스팩|기업인수목적', name):
        return False, 'SPAC_EXCLUDED'
    if not isinstance(sector,str) or not sector.strip():
        return False, 'UNKNOWN_INDUSTRY_EXCLUDED'
    if PHARMA_BIO.search(sector):
        return False, 'PHARMA_BIO_EXCLUDED'
    # Medical devices are not automatically pharmaceutical/biotech companies.
    # Research-only remaining labels still need dated company-level validation.
    return True, 'SNAPSHOT_COMMON_NONPHARMA_RESEARCH_ONLY'


def audit(issuer_dir,sector_csv,candidate_csv,out):
    folder=Path(issuer_dir);meta=json.loads((folder/'krx_basic_v610_status.json').read_text())
    if meta.get('official_base_usable') is not True:
        raise ValueError('OFFICIAL_ISSUER_DATA_UNUSABLE')
    infos={}
    for market in ('KOSPI','KOSDAQ'):
        p=folder/f'{market}_basic_v610.csv'
        if hashlib.sha256(p.read_bytes()).hexdigest()!=meta['source_file_sha256'][market]:
            raise ValueError('OFFICIAL_ISSUER_SHA_CHANGED')
        rr=pd.read_csv(p,dtype=str).fillna('').to_dict('records')
        if len(rr)!=meta['market_counts'][market]:raise ValueError('ISSUER_COUNT_MISMATCH')
        for r in rr:
            if r['ticker'] in infos:raise ValueError('DUPLICATE_ISSUER')
            if r['asof_requested']!=meta['asof']:raise ValueError('ISSUER_REQUEST_DATE_MISMATCH')
            infos[r['ticker']]=r
    sec=pd.read_csv(sector_csv,dtype=str).fillna('')
    if sec.ticker.duplicated().any():raise ValueError('AMBIGUOUS_INDUSTRY_SNAPSHOT')
    sectors=dict(zip(sec.ticker,sec.sector))
    candidates=pd.read_csv(candidate_csv,dtype={'ticker':str})
    records=[]
    for t in sorted(candidates.ticker.unique()):
        info=infos.get(t);sector=sectors.get(t);allowed,reason=classify(info,sector)
        records.append(dict(ticker=t,name=info.get('name') if info else None,
             security_group=info.get('security_group') if info else None,
             share_kind=info.get('share_kind') if info else None,sector_snapshot=sector,
             official_request_asof=meta['asof'],official_received_utc=meta['received_utc'],
             sector_file_vintage_unknown=True,independent_historical_PIT_verified=False,
             snapshot_research_allowed=allowed,reason=reason,
             trade_approved=False,orders_enabled=False))
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(records).to_csv(out,index=False,encoding='utf-8-sig')
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--issuer-dir',required=True);p.add_argument('--sector-csv',required=True)
    p.add_argument('--candidates',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();r=audit(a.issuer_dir,a.sector_csv,a.candidates,a.out)
    print(pd.DataFrame(r).groupby(['reason']).size().to_string())
