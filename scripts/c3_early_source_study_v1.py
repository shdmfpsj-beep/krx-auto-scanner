"""Pinned publication replay; later official comparison is never backdated."""
import argparse,csv,hashlib,io,json,os
from pathlib import Path
from urllib.parse import quote
import requests
from c3_telegram_inputs import GitHub
from c3_morning_source_v1 import cache_rows,normalized_hash,compare
from c3_early_source_v1 import FDR,stamp,sha,write,clock,quality,differences,fdr_snapshot

SNAPSHOTS=[('1443','e329723ac6c9ea55237f4cb6b492120d6c4b7c73','2026-11-12T05:50:00Z'),
           ('2301','712478993090174fd3366104c22f1af8d3ee275b','2026-11-12T14:10:00Z'),
           ('0701','0dd9dc43dd0c07aa901558976ad24c10e3e420e1','2026-11-12T22:10:00Z')]

def parquet_probe(day,cutoff,out):
    import pandas as pd
    gh=GitHub(os.environ['GH_TOKEN'],'FinanceData/marcap');path='data/marcap-'+day[:4]+'.parquet'
    commits=gh.api('commits?path='+quote(path,safe='')+'&per_page=1&until='+quote(cutoff,safe=''))
    if not commits:raise ValueError('NO_MARCAP_VERSION_AT_CUTOFF')
    commit=commits[0];ref=commit['sha'];info=gh.api('contents/'+path+'?ref='+ref)
    if clock(commit['commit']['committer']['date'])>clock(cutoff):raise ValueError('MARCAP_FUTURE_VERSION')
    rawpath=Path(out)/'private-marcap.parquet';size=0;h=hashlib.sha256()
    url='https://raw.githubusercontent.com/FinanceData/marcap/'+ref+'/'+path
    with requests.get(url,stream=True,timeout=(10,45)) as response:
        response.raise_for_status()
        with rawpath.open('wb') as f:
            for chunk in response.iter_content(1024*1024):
                size+=len(chunk)
                if size>64*1024*1024:raise ValueError('MARCAP_DOWNLOAD_LIMIT')
                f.write(chunk);h.update(chunk)
    if size!=info['size']:raise ValueError('MARCAP_RAW_SIZE_MISMATCH')
    # Read the published raw dataset, never utility Volume>0 filtering.
    df=pd.read_parquet(rawpath)
    if 'Date' not in df.columns:df=df.reset_index()
    if 'Date' not in df.columns:raise ValueError('MARCAP_DATE_COLUMN_REQUIRED')
    dates=pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d');last=dates.max();selected=df[dates==day];rows=[];excluded={}
    for r in selected.to_dict('records'):
        market={'STK':'KOSPI','KSQ':'KOSDAQ','KNX':'KONEX'}.get(str(r.get('MarketId')))
        if market is None:
            m=str(r.get('Market','')).upper().replace(' ','').replace('_','')
            market={'KOSPI':'KOSPI','KOSDAQ':'KOSDAQ','KOSDAQGLOBAL':'KOSDAQ','KONEX':'KONEX'}.get(m)
        if market=='KONEX':excluded['KONEX']=excluded.get('KONEX',0)+1;continue
        if market not in ('KOSPI','KOSDAQ'):raise ValueError('MARCAP_UNKNOWN_MARKET')
        ticker=str(r['Code']).zfill(6)
        rows.append(dict(ticker=ticker,name=str(r['Name']),market=market,asof=day,
            **{k:float(r[c]) for k,c in [('open','Open'),('high','High'),('low','Low'),('close','Close'),('volume','Volume'),('turnover_krw','Amount')]}))
    result=dict(provider='FINANCEDATA_MARCAP_PUBLISHED_PARQUET',asof=day,repository=gh.repo,path=path,
        cutoff_at=cutoff,file_commit=ref,file_commit_at=commit['commit']['committer']['date'],
        raw_sha256=h.hexdigest(),git_blob_sha=info['sha'],raw_bytes=size,collected_at=stamp(),
        raw_schema=list(df.columns),latest_date_in_version=last,selected_rows=len(rows),excluded=excluded,
        source_status='SINGLE_SOURCE_UNVERIFIED' if rows else 'SOURCE_UNAVAILABLE_AT_CUTOFF',
        regular_only_certified=False,independent_provider_from_krx=False,
        utility_volume_filter_used=False,price_basis='UNADJUSTED_AS_PUBLISHED_NOT_CORPORATE_ACTION_CERTIFIED')
    if rows:result.update(quality=quality(rows,day),normalized_rows_sha256=normalized_hash(rows))
    rawpath.unlink();return rows,result

def run(out,official_dir):
    from c3_source_recovery_v1 import official_rows
    out=Path(out);out.mkdir(parents=True,exist_ok=True);day='2026-11-12';official=official_rows(Path(official_dir));quality(official,day)
    gh=GitHub(os.environ['GH_TOKEN'],FDR);versions=[];prices={}
    path='data/listing/krx/'+day+'.csv'
    history=gh.api('commits?path='+quote(path,safe='')+'&since=2026-11-11T15%3A00%3A00Z&until=2026-11-12T22%3A10%3A00Z&per_page=100')
    history_proof=[]
    if len(history)>=100:raise ValueError('DATED_FILE_HISTORY_PAGINATION_REQUIRED')
    for item in reversed(history):
        raw=gh.file(path,item['sha']);source=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        selected=[r for r in source if r.get('MarketId') in ('STK','KSQ')]
        observation=dict(file_commit=item['sha'],file_commit_at=item['commit']['committer']['date'],raw_sha256=sha(raw),raw_rows=len(source),target_rows=len(selected),
            empty_field_counts={k:sum(not r.get(k) for r in selected) for k in ('Open','High','Low','Close','Volume','Amount')})
        try:
            rows,_=cache_rows(raw,day);quality(rows,day);observation['official_comparison']=differences(rows,official)
        except (ValueError,KeyError):observation['status']='INVALID_PRICE_FIELDS'
        history_proof.append(observation)
    matching=[r for r in history_proof if r.get('official_comparison',{}).get('match_rate_pct')==100]
    earliest=min((r['file_commit_at'] for r in matching),default=None)
    if earliest!='2026-11-12T14:01:06Z':raise ValueError('EARLIEST_MATCHING_FILE_HISTORY_NOT_REPRODUCED')
    push_evidence=[];push_status='NO_MATCHING_PUBLIC_PUSH_EVENT'
    try:
        wanted={r['file_commit'] for r in history_proof}|{r[1] for r in SNAPSHOTS}
        for event in gh.api('events?per_page=100'):
            p=event.get('payload') or {};head=p.get('head');commits={r.get('sha') for r in p.get('commits',[])}
            matches=(commits|{head})&wanted
            if event.get('type')=='PushEvent' and matches:
                push_evidence.append(dict(event_id=event['id'],created_at=event['created_at'],ref=p.get('ref'),head=head,matched_commits=sorted(matches)))
        if push_evidence:push_status='MATCHED_PUBLIC_SERVER_PUSH_EVENT'
    except Exception as exc:push_status='PUBLIC_EVENT_PROBE_UNAVAILABLE_'+type(exc).__name__
    for label,ref,cutoff in SNAPSHOTS:
        raw=gh.file('data/listing/krx/'+day+'.csv',ref);rows,excluded=cache_rows(raw,day);prices[label]=rows
        (out/(label+'.csv')).write_bytes(raw)
        result=dict(label=label,snapshot_commit=ref,raw_sha256=sha(raw),rows=len(rows),excluded=excluded,
            normalized_rows_sha256=normalized_hash(rows),official_comparison=differences(rows,official),
            official_comparison_performed_at=stamp(),official_reference_known_at_historical_cutoff='NOT_ATTESTED',
            official_reference_collected_during_replay=True)
        try:
            _,_,meta=fdr_snapshot(day,cutoff,ref,gh);result.update(eligible_post_close=True,file_commit=meta['file_commit'],file_commit_at=meta['file_commit_at'])
        except ValueError as exc:result.update(eligible_post_close=False,rejection_reason=str(exc))
        versions.append(result)
    compare(prices['2301'],prices['0701'],day);compare(official,prices['2301'],day)
    if versions[0]['official_comparison']['matched_rows']==len(official):raise ValueError('INTRADAY_CONTROL_UNEXPECTEDLY_FINAL')
    future_rejected=False
    try:fdr_snapshot(day,'2026-11-12T14:10:00Z',SNAPSHOTS[2][1],gh)
    except ValueError as exc:future_rejected=str(exc)=='FUTURE_COMMIT_AT_REPLAY_CUTOFF'
    if not future_rejected:raise ValueError('REPLAY_FUTURE_COMMIT_WAS_NOT_REJECTED')
    sources=[]
    for cutoff in ('2026-11-12T14:10:00Z',stamp()):
        try:
            rows,doc=parquet_probe(day,cutoff,out)
            if rows:doc['official_comparison']=differences(rows,official)
            sources.append(doc)
        except Exception as exc:sources.append(dict(provider='FINANCEDATA_MARCAP_PUBLISHED_PARQUET',cutoff_at=cutoff,status='PROBE_FAILED',error_type=type(exc).__name__,reason=str(exc)[:180]))
    result=dict(schema='C3_EARLY_SOURCE_REPLAY_V1',asof=day,replay_executed_at=stamp(),source_run_id=os.environ.get('GITHUB_RUN_ID'),
        official_rows=len(official),official_normalized_sha256=normalized_hash(official),snapshots=versions,additional_sources=sources,
        dated_file_commit_history=history_proof,earliest_confirmed_matching_commit_at=earliest,
        public_push_event_status=push_status,public_push_events=push_evidence,
        timing_evidence_scope='EARLIEST_MATCHING_DATED_FILE_COMMIT_NOT_EXACT_SERVER_PUBLICATION_OR_PROVIDER_SLA',
        earlier_incorrect_version_at='2026-11-12T05:43:14Z',future_snapshot_rejected=True,
        improvement_vs_next_0701_seconds=28807,improvement_vs_0810_seconds=32934,
        naver=dict(status='NOT_QUERIED_TERMS_BLOCKED',quote_api_requests=0,rows=None,
            policy='https://policy.naver.com/policy/disclaimer.html',robots='https://finance.naver.com/robots.txt',regular_nxt_scope='UNVERIFIED'),
        fsc=dict(status='NOT_CONNECTED_NOT_EARLY',rows=None,requests=0,posting='NEXT_BUSINESS_DAY_AFTER_13_KST',
            documentation='https://www.data.go.kr/data/15094808/openapi.do'),
        regular_only_certified=False,buy_approved=False,telegram_requests=0)
    write(out/'replay.json',result);print(json.dumps(dict(official_rows=len(official),versions=[dict(label=v['label'],matched=v['official_comparison']['matched_rows']) for v in versions],marcap=sources),ensure_ascii=False))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--official-dir',type=Path,required=True);a=p.parse_args();run(a.out,a.official_dir)
