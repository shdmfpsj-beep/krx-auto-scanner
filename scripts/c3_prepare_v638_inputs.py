#!/usr/bin/env python3
"""Rebuild research eligibility from immutable public KRX-source artifacts."""
import argparse,hashlib,json,zipfile
from pathlib import Path
import pandas as pd
from c3_eligibility_v637 import audit
from c3_research_v637 import FULL_ARCHIVE_SHA

ISSUER_ARCHIVE_SHA='f83b2bea958ced6c1631753044aaeb53b0b4ea845f2feb186a28a08fe06d4f38'


def prepare(market_zip,issuer_zip,sector_csv,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if hashlib.sha256(Path(market_zip).read_bytes()).hexdigest()!=FULL_ARCHIVE_SHA:
        raise ValueError('UNEXPECTED_FROZEN_MARKET_ARTIFACT')
    if hashlib.sha256(Path(issuer_zip).read_bytes()).hexdigest()!=ISSUER_ARCHIVE_SHA:
        raise ValueError('UNEXPECTED_FROZEN_ISSUER_ARTIFACT')
    basic=out/'basic';basic.mkdir(exist_ok=True)
    with zipfile.ZipFile(issuer_zip) as z:
        for name in ('krx_basic_v610_status.json','KOSPI_basic_v610.csv','KOSDAQ_basic_v610.csv'):
            (basic/name).write_bytes(z.read('basic/'+name))
    with zipfile.ZipFile(market_zip) as z:
        tickers=[dict(ticker=Path(n).stem) for n in z.namelist()
                 if n.startswith('market/prices/') and n.endswith('.csv')]
    pd.DataFrame(tickers).to_csv(out/'source_tickers.csv',index=False)
    target=out/'eligibility_snapshot.csv'
    audit(basic,sector_csv,out/'source_tickers.csv',target)
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('market-zip','issuer-zip','sector-csv','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();path=prepare(a.market_zip,a.issuer_zip,a.sector_csv,a.out)
    print(str(path),hashlib.sha256(path.read_bytes()).hexdigest())
