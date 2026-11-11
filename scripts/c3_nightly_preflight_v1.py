"""Read-only nightly readiness, official EOD probe and frozen chart replay.

No Telegram token, Git mutation, new signal, broker order or paper execution.
Output may report SOURCE_PENDING even when the audit job itself succeeds.
"""
import argparse
import copy
import csv
import io
import json
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
            if raw and official.get('official_dataset_usable'):
                rows={r['Code']:r for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))}
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
