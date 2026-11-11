#!/usr/bin/env python3
"""As-of issue type provenance for C3: KRX issuer basic-info, read-only.
Never asserts original-vintage proof from a retrospective API response.
"""
import argparse,csv,hashlib,json,re,time
from collections import Counter
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

MARKET_ENDPOINTS={'KOSPI':'sto/stk_isu_base_info',
                  'KOSDAQ':'sto/ksq_isu_base_info'}
def sha(data):return hashlib.sha256(data).hexdigest()
def parse_category(row,selection_date):
    listing=str(row.get('LIST_DD',''))
    listed=re.sub(r'\D','',listing)
    if len(listed)==8 and listed>selection_date.replace('-',''):
        return {'status':'BLOCKED_LISTING_DATE_AFTER_SIGNAL','kind':None,'security_group':None,'segment':None}
    kind=str(row.get('KIND_STKCERT_TP_NM','')).strip() or None
    security=str(row.get('SECUGRP_NM','')).strip() or None
    segment=str(row.get('SECT_TP_NM','')).strip() or None
    return {'status':'DATED_METADATA_REPORTED_VINTAGE_NOT_INDEPENDENTLY_VERIFIED',
        'kind':kind,'security_group':security,'segment':segment,
        'common_share_reported':kind=='보통주',
        'preferred_share_reported':kind in ('우선주','우선주권'),
        'listing_date_reported':listing or None}

def fetch(day,market,key,opener=urlopen):
    if not key:return {'status':'BLOCKED_NO_AUTH','rows':None,'digest':None,'data':{}}
    path=MARKET_ENDPOINTS[market]
    req=Request('https://data-dbg.krx.co.kr/svc/apis/'+path+
                '?basDd='+day.replace('-',''),
                headers={'AUTH_KEY':key,'Accept':'application/json'})
    try:
        with opener(req,timeout=20) as h:raw=h.read(6*1024*1024+1)
        if len(raw)>6*1024*1024:return {'status':'BLOCKED_OVERSIZE','rows':None,'digest':None,'data':{}}
        data=json.loads(raw.decode('utf-8'))
        arr=data.get('OutBlock_1')
        if not isinstance(arr,list) or not arr:return {'status':'BLOCKED_EMPTY','rows':None,'digest':sha(raw),'data':{}}
        tickers={}
        for x in arr:
            k=str(x.get('ISU_SRT_CD','')).strip()
            if k in tickers:return {'status':'BLOCKED_DUPLICATE_TICKER','rows':len(arr),'digest':sha(raw),'data':{}}
            tickers[k]=x
        return {'status':'PROVISIONAL_KRX_DATE_REQUEST','rows':len(arr),'digest':sha(raw),'data':tickers}
    except HTTPError as err:
        return {'status':'BLOCKED_HTTP_'+str(err.code),'rows':None,'digest':None,'data':{}}
    except (URLError,TimeoutError,OSError):
        return {'status':'BLOCKED_NETWORK','rows':None,'digest':None,'data':{}}
    except (ValueError,KeyError,TypeError,UnicodeDecodeError):
        return {'status':'BLOCKED_BAD_RESPONSE','rows':None,'digest':None,'data':{}}

def market_for_event(root,ticker,day,cache):
    if day not in cache:
        st_path=root/day/'krx_v65_collect_status.json'
        if not st_path.is_file():return None
        st=json.loads(st_path.read_text())
        if st.get('asof')!=day or st.get('official_dataset_usable') is not True:return None
        date_data={}
        for market in MARKET_ENDPOINTS:
            path=root/day/(market+'_official.csv')
            if not path.is_file() or sha(path.read_bytes())!=st.get('market_file_sha256',{}).get(market):
                return None
            with path.open(encoding='utf-8-sig',newline='') as f:
                for r in csv.DictReader(f):
                    if r.get('valid_daily_bar')=='True':
                        if r['ticker'] in date_data:raise ValueError('DUPLICATE_TICKER_ACROSS_MARKETS')
                        date_data[r['ticker']]=market
        cache[day]=date_data
    return cache[day].get(ticker)

def audit(events,root,key,limit=130,sleep_seconds=.12):
    by_day={};pairs=set();records=[]
    for e in events:
        ticker,day=str(e['ticker']),str(e['date'])
        market=market_for_event(root,ticker,day,by_day)
        if market:pairs.add((day,market))
        records.append({'ticker':ticker,'date':day,'market':market})
    if len(pairs)>limit:
        return {'status':'BLOCKED_QUERY_LIMIT','planned_market_date_queries':len(pairs),
                'completed':0,'decision':'CASH','trade_approved':False}
    api={};counts=Counter()
    for day,market in sorted(pairs):
        a=fetch(day,market,key)
        api[(day,market)]=a
        counts[a['status']]+=1
        if sleep_seconds:time.sleep(sleep_seconds)
    for r in records:
        if not r['market']:
            r['issue_metadata']={'status':'BLOCKED_NO_HASHED_PRICE_MARKET_MATCH'}
            continue
        data=api[(r['date'],r['market'])]
        x=data['data'].get(r['ticker'])
        r['issue_metadata']=(parse_category(x,r['date']) if x else
            {'status':'BLOCKED_NO_MATCHING_ASOF_ISSUE_RECORD'})
        r['source_snapshot_sha256']=data['digest']
        r['source_api_status']=data['status']
        counts['kind_'+str(r['issue_metadata'].get('kind') or 'NO_MATCH')]+=1
        counts['issue_event_matched']+=bool(x)
    return {'schema':'C3_ASOF_KRX_ISSUE_META_V1',
        'status':'RESEARCH_ASOF_METADATA_PROVISIONAL',
        'event_count':len(records),'unique_market_date_queries':len(pairs),
        'source_status_counts':dict(counts),
        'query_manifest':[{'date':d,'market':m,'status':v['status'],
                           'records':v['rows'],'response_sha256':v['digest']}
                         for (d,m),v in sorted(api.items())],
        'asof_issuer_metadata_not_historical_vintage_certified':True,
        'corporate_actions_not_resolved':True,
        'delisted_issuer_completeness_not_resolved':True,
        'sector_business_category_not_verified':True,
        'production_filters_changed':False,'trade_approved':False,
        'decision':'CASH','events':records}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--max-requests',type=int,default=120)
    a=p.parse_args()
    import os
    events=json.loads(a.cohort.read_text())['events']
    r=audit(events,a.root,os.environ.get('KRX_AUTH_KEY'),a.max_requests)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('C3_ISSUE_METADATA',json.dumps({k:v for k,v in r.items() if k not in ('events','query_manifest')},ensure_ascii=False))
if __name__=='__main__':main()
