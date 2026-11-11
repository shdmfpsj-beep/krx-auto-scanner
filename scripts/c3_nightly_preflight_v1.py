"""Read-only nightly readiness, official EOD probe and frozen chart replay.

No Telegram token, Git mutation, new signal, broker order or paper execution.
Output may report SOURCE_PENDING even when the audit job itself succeeds.
"""
import argparse
import copy
import csv
import io
import json
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from c3_telegram_inputs import GitHub, RESEARCH, ROOT, canonical, digest, frozen_live_bars
from c3_telegram_notify import expected_session, report_error
from c3_classic_theme import create_cards, create_final_cards
from c3_final_delivery_gate_v1 import review, filtered_report_for_presentation
from krx_official_eod_v65 import collect, read_csv


class ReadOnlyGitHub(GitHub):
    def api(self,path,method='GET',payload=None,missing_ok=False):
        if method!='GET' or payload is not None:
            raise ValueError('NIGHTLY_AUDIT_MUTATION_FORBIDDEN')
        return super().api(path,method,payload,missing_ok)

    def create(self,*args,**kwargs):
        raise ValueError('NIGHTLY_AUDIT_MUTATION_FORBIDDEN')


def protected(gh,ref,prefixes):
    tree=gh.api('git/trees/'+ref+'?recursive=1')
    if tree.get('truncated'):raise ValueError('INCOMPLETE_PROTECTED_TREE')
    return {x['path']:x['sha'] for x in tree['tree']
            if x['type']=='blob' and any(x['path'].startswith(p) for p in prefixes)}


def safe_code(exc):
    value=str(exc)
    return value if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]{1,100}',value) else 'SOURCE_OR_TRANSPORT_UNAVAILABLE'


def audit_cache(raw,day,previous=None):
    """Internal dated CSV checks only; a KRX cache is not independent proof."""
    raw_rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    # Mirror the already approved adapter: MarketId is the board key.
    # KOSDAQ GLOBAL is a KOSDAQ segment; KONEX is outside this system's scope.
    rows=[r for r in raw_rows if r.get('MarketId') in ('STK','KSQ')]
    excluded={}
    for row in raw_rows:
        if row.get('MarketId') not in ('STK','KSQ'):
            key=row.get('MarketId','MISSING');excluded[key]=excluded.get(key,0)+1
    issues=[];seen=set();markets={'KOSPI':0,'KOSDAQ':0};no_trades=0
    for row in rows:
        ticker=row.get('Code','');market={'STK':'KOSPI','KSQ':'KOSDAQ'}.get(row.get('MarketId'))
        if not re.fullmatch('[0-9A-Z]{6}',ticker) or ticker in seen:issues.append({'ticker':ticker,'reason':'CODE_OR_DUPLICATE'})
        seen.add(ticker)
        accepted_labels={'KOSPI':('KOSPI',),'KOSDAQ':('KOSDAQ','KOSDAQ GLOBAL')}
        if not row.get('Name','').strip() or market not in markets or row.get('Market') not in accepted_labels.get(market,()):
            issues.append({'ticker':ticker,'reason':'IDENTITY_OR_MARKET'})
        else:markets[market]+=1
        try:
            o,h,l,c,v,a=[float(str(row[k]).replace(',','')) for k in ('Open','High','Low','Close','Volume','Amount')]
            if not all(math.isfinite(x) and x>=0 for x in (o,h,l,c,v,a)) or v!=int(v):raise ValueError()
            if v==0:
                no_trades+=1
                if a!=0:raise ValueError()
            elif not 0<l<=min(o,c)<=max(o,c)<=h or a<=0:raise ValueError()
        except (KeyError,TypeError,ValueError):issues.append({'ticker':ticker,'reason':'INVALID_OHLCV_OR_TURNOVER'})
    if not rows or any(v==0 for v in markets.values()):issues.append({'reason':'EMPTY_MARKET'})
    result={'status':'INTERNAL_CHECKS_PASSED_NOT_SOURCE_CERTIFIED' if not issues else 'INTERNAL_QUALITY_FAILED',
            'requested_file_day':day,'raw_rows':len(raw_rows),'rows':len(rows),'market_rows':markets,'issues':issues,
            'out_of_scope_rows':sum(excluded.values()),'excluded_market_ids':excluded,
            'zero_volume_rows':no_trades,'halt_or_delisting_not_inferred':True,
            'regular_only_certified':False,'independent_source':False,'corporate_actions_certified':False}
    if previous:
        old={r['Code']:r for r in csv.DictReader(io.StringIO(previous.decode('utf-8-sig'))) if r.get('MarketId') in ('STK','KSQ')}
        current={r['Code']:r for r in rows}
        result['previous_cache_comparison']={'new_codes':sorted(set(current)-set(old)),
            'absent_codes':sorted(set(old)-set(current)),
            'changed_names':[t for t in current.keys()&old.keys() if current[t]['Name']!=old[t]['Name']],
            'listing_cause_not_certified':True,'prior_cache_is_current_vintage_not_original_replacement':True}
    return result


def execute(outdir):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    clock=datetime.now(ZoneInfo('Asia/Seoul'));day=expected_session(clock)
    audit={'schema':'C3_NIGHTLY_READ_ONLY_PREFLIGHT_V1','checked_at_kst':clock.isoformat(),
           'requested_source_day':day,'status':'SOURCE_PENDING','today_final_candidate_count':None,
           'telegram_send_attempts':0,'new_signals_registered':0,'git_write_requests':0,
           'orders_enabled':False,'decision':'CASH','main_deployed':False,
           'regular_only_certified':False,'financial_PIT_certified':False}
    try:
        gh=ReadOnlyGitHub(os.environ.get('GH_TOKEN',''))
        ref=gh.head(RESEARCH);main_ref=gh.head('main')
        latest=json.loads(gh.file(ROOT+'/latest.json',ref))
        summary=json.loads(gh.file(ROOT+'/mobile/summary.json',ref))
        initial=digest(canonical(latest))
        lane=ROOT+'/lanes/krx_unadjusted_v12/'
        immutable=protected(gh,ref,(lane,ROOT+'/key_envelopes/'))
        audit.update(research_ref=ref,main_ref=main_ref,source_report_sha256=initial,
                     source_price_asof=latest.get('source_price_asof'),source_run_id=latest.get('source_run_id'),
                     source_received_at=latest.get('source_received_at'),analysis_completed_at=latest.get('analysis_completed_at'),
                     source_generated_at=latest.get('generated_at'),source_quality=latest.get('source_quality_gate'),
                     source_scope=latest.get('current_scope'),protected_blob_count=len(immutable),
                     protected_tree_sha256=digest(canonical(immutable)))
        reason=report_error(latest,summary,clock)
        original_run=gh.api('actions/runs/'+str(latest['source_run_id']))
        audit['original_source_workflow']={k:original_run.get(k) for k in
            ('id','path','head_sha','head_branch','status','conclusion','created_at','updated_at')}
        artifacts=gh.api('actions/runs/'+str(latest['source_run_id'])+'/artifacts?per_page=100')
        audit['original_source_artifacts']=[{k:r.get(k) for k in ('id','name','digest','expired')}
            for r in artifacts.get('artifacts',[])]
        if reason is None and (original_run.get('status')!='completed' or original_run.get('conclusion')!='success'):
            reason='SOURCE_WORKFLOW_NOT_SUCCESSFUL'
        audit['current_report_gate']=reason or 'PASSED'
        if reason is None:
            audit['status']='CURRENT_RESEARCH_READY_SESSION_UNCERTIFIED'
            audit['today_final_candidate_count']=len(latest['research_top2'])
        audit['today_top2_is_zero_confirmed']=reason is None and latest['research_top2']==[]
        (out/'source_report.json').write_bytes(canonical(latest)+b'\n')
        (out/'source_summary.json').write_bytes(canonical(summary)+b'\n')
        try:
            original=copy.deepcopy(latest)
            authenticated=frozen_live_bars(gh,original,ref)
            analysis=review(authenticated,authenticated.get('presentation_ranked_pool'),authenticated.get('presentation_pool_proof'))
            replay=filtered_report_for_presentation(authenticated,analysis,authenticated.get('presentation_ranked_pool'))
            replay['historical_test_only']=True
            # Every audit PNG is diagnostic. No artifact is a live-send request.
            cards=create_final_cards(replay,out/'final_replay')
            (out/'final_replay'/'delivery_review.json').write_bytes(canonical(analysis)+b'\n')
            authenticated['example_only']=True
            if authenticated['research_top2']:
                create_cards(authenticated,out/'original_replay',allow_single=True)
            audit['frozen_replay']={'status':'HASH_AND_PLAN_MATCHED','asof':latest['source_price_asof'],
                'is_today':latest['source_price_asof']==day,'decision_sha256':authenticated['input_provenance']['decision_payload_sha256'],
                'original_candidate_count':len(latest['research_top2']),'diagnostic_final_images':len(cards),
                'candidate_pool_status':analysis['candidate_pool_status'],'reviewed':analysis['reviewed']}
        except Exception as exc:
            audit['frozen_replay']={'status':'BLOCKED','reason':safe_code(exc)}
        with tempfile.TemporaryDirectory(prefix='c3-read-only-official-') as tmp:
            official=collect(day,Path(tmp),os.environ.get('KRX_AUTH_KEY'))
            audit['today_official_probe']=official
            audit['today_cache_comparison']={'status':'NOT_AVAILABLE','independent_source':False,'regular_only_certified':False}
            cache=ReadOnlyGitHub(os.environ.get('GH_TOKEN',''),'FinanceData/fdr_krx_data_cache')
            cache_ref=cache.head('master')
            raw=cache.file('data/listing/krx/'+day+'.csv',cache_ref,missing_ok=True)
            if raw:
                prior=cache.file('data/listing/krx/'+latest['source_price_asof']+'.csv',cache_ref,missing_ok=True)
                audit['today_cache_quality']=audit_cache(raw,day,prior)
                history=cache.api('commits?sha='+cache_ref+'&path=data/listing/krx/'+day+'.csv&per_page=1')
                audit['today_cache_quality']['file_commit']={
                    'sha':history[0]['sha'],'committed_at':history[0]['commit']['committer']['date']} if history else None
                if history:
                    committed=datetime.fromisoformat(history[0]['commit']['committer']['date'].replace('Z','+00:00'))
                    closed=datetime.fromisoformat(day+'T15:30:00+09:00')
                    audit['today_cache_quality']['published_after_close_before_audit']=closed<=committed<=clock
            if raw and official.get('official_dataset_usable'):
                rows={r['Code']:r for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))) if r.get('MarketId') in ('STK','KSQ')}
                actual=[r for name in ('KOSPI','KOSDAQ') for r in read_csv(Path(tmp)/(name+'_official.csv'))]
                mapping={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume','turnover_krw':'Amount'}
                mismatches=[]
                for row in actual:
                    other=rows.get(row['ticker'])
                    if (other is None or other.get('Name')!=row['name'] or
                        {'STK':'KOSPI','KSQ':'KOSDAQ'}.get(other.get('MarketId'))!=row['market'] or
                        any(float(row[k])!=float(str(other[v]).replace(',','')) for k,v in mapping.items())):
                        mismatches.append(row['ticker'])
                audit['today_cache_comparison']={'status':'NUMERIC_MATCH' if not mismatches and len(actual)==len(rows) else 'MISMATCH',
                    'official_rows':len(actual),'cache_rows':len(rows),'mismatch_count':len(mismatches),
                    'cache_ref':cache_ref,'cache_sha256':digest(raw),'independent_source':False,'regular_only_certified':False}
            elif raw:
                audit['today_cache_comparison'].update(status='CACHE_ONLY_OFFICIAL_PENDING',cache_ref=cache_ref,cache_sha256=digest(raw))
        audit['protected_tree_same_at_pinned_ref']=immutable==protected(gh,ref,(lane,ROOT+'/key_envelopes/'))
        newest_ref=gh.head(RESEARCH)
        newest=protected(gh,newest_ref,(lane,ROOT+'/key_envelopes/'))
        audit['original_protected_blobs_unchanged_at_latest_head']=all(newest.get(p)==s for p,s in immutable.items())
        audit['end_research_ref']=newest_ref
        audit['source_report_not_mutated']=initial==digest(canonical(latest))
        try:
            receipt_ref=gh.head('delivery/c3-top2-telegram')
            receipts=protected(gh,receipt_ref,('receipts/',))
            outcomes=[p for p in receipts if p.startswith('receipts/outcomes/final/') and '/'+day+'-' in p]
            audit['delivery_receipts']={'ref':receipt_ref,'protected_blob_count':len(receipts),
                'tree_sha256':digest(canonical(receipts)),'today_outcomes':[]}
            for path in outcomes:
                result=json.loads(gh.file(path,receipt_ref))
                audit['delivery_receipts']['today_outcomes'].append({k:result.get(k) for k in
                    ('status','source_date','photos','message_ids','send_attempts','recorded_at')})
        except Exception as exc:
            audit['delivery_receipts']={'status':'NOT_VERIFIED','reason':safe_code(exc)}
        audit['workflow_schedule']={}
        for path in ('daily.yml','c3_research_daily_caller.yml','c3_top2_telegram.yml'):
            body=gh.file('.github/workflows/'+path,main_ref).decode()
            audit['workflow_schedule'][path]=re.findall(r"cron:\s*['\"]([^'\"]+)",body)
        audit['chatgpt_report_kst']='22:30 configured separately; completion/delivery not guaranteed'
        audit['source_may_complete_after_chatgpt_report']=True
        audit['audit_completed_at_kst']=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    except Exception as exc:
        audit.update(status='AUDIT_FAILED',reason=safe_code(exc))
    (out/'nightly_preflight.json').write_bytes(canonical(audit)+b'\n')
    print(json.dumps({k:audit.get(k) for k in ('status','requested_source_day','source_price_asof','current_report_gate','today_final_candidate_count','telegram_send_attempts')},ensure_ascii=False))
    return audit


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True)
    result=execute(parser.parse_args().outdir)
    raise SystemExit(1 if result['status']=='AUDIT_FAILED' else 0)
