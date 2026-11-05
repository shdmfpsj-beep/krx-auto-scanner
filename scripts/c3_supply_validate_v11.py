"""Validate the whole dated cache against actual official controls and quarantine conflicts."""
import csv,io,json,os,subprocess,zipfile
from pathlib import Path
import pandas as pd
from c3_supply_v11 import open_sealed,seal,write,digest,compare,rows_from_frame,transport,now
from c3_supply_bridge_v11 import extract_zip
from c3_market_supply_v11 import mirror


def run(root):
    root=Path(root);private=root/'private';pub=root/'public';private.mkdir(parents=True,exist_ok=True);pub.mkdir(exist_ok=True)
    data=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/13450414308/zip'],timeout=60)
    if digest(data)!='b190024af12ef397e5183a518492394b6c115c3f376106717e5abfe05818699c':raise ValueError('BRIDGE_HASH_MISMATCH')
    extract_zip(data,root/'input');extract_zip(open_sealed(root/'input/private_market_data.aesgcm',os.environ['KRX_AUTH_KEY']),private/'recovered')
    base=private/'recovered/sample_cache';out=private/'validated/2026-11-05';m=mirror('2026-11-05',base/'official/2026-11-04',out,private/'mirror_wire',previous_day='2026-11-04')
    allrows=[]
    for market in ('KOSPI','KOSDAQ'):
        with (out/m['price_files'][market]).open(encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):allrows.append(dict({k:float(r[k]) for k in ('open','high','low','close','volume','turnover_krw')},ticker=r['ticker'],market=market,date=r['asof']))
    # Reuse previously observed samples instead of recollecting forty names.
    naver=[]
    for p in (base/'normalized/NAVER_JSON').glob('*.json'):naver+=json.loads(p.read_text())
    sample={r['ticker'] for r in naver};c=compare([r for r in allrows if r['ticker'] in sample],naver,['2026-11-05'])
    write(pub/'mirror_vs_naver_current.json',c)
    native=[]
    for ticker in ('005930','036930'):
        j=json.loads((private/'recovered'/('NAVER_NEW_CHART_'+ticker+'.json')).read_text());market=next(r['market'] for r in allrows if r['ticker']==ticker)
        cols={'Open':'openPrice','High':'highPrice','Low':'lowPrice','Close':'closePrice','Volume':'accumulatedTradingVolume'}
        frame=pd.DataFrame([{k:x[v] for k,v in cols.items()} for x in j],index=pd.to_datetime([x['localDate'] for x in j]));native+=rows_from_frame(frame,ticker,market,'2026-11-05')
    write(pub/'native_naver_current_check.json',compare([r for r in allrows if r['ticker'] in {n['ticker'] for n in native}],native,['2026-11-05']))
    write(pub/'validated_cache_manifest.json',dict(m,price_files=None));write(pub/'summary.json',dict(run_id=os.environ.get('GITHUB_RUN_ID'),generated_at=now(),source_date=m['asof'],rows=m['official_market_rows'],quality_state=m['data_quality_state'],full_control=m['validation']['control'],quality=m['validation']['quality'],reference_rebases=m['validation']['reference_rebase_candidates'],naver_current=c['counts'],independent_current_confirmation=False,current_action='CASH',new_signals=0))
    write(pub/'archive_manifest.json',seal(private,root/'private_market_data.aesgcm',os.environ['KRX_AUTH_KEY']))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args();run(a.outdir)
