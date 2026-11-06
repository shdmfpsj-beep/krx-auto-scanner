"""Same-source presentation handoff and bounded recovery; never trading logic.

Only derived presentation paths may be written. A missing/old price source
produces an empty packet, never the historical preview candidates.
"""
import argparse,copy,json,os,re,time
import requests
from datetime import datetime,timezone
from pathlib import Path
from c3_telegram_inputs import GitHub,RESEARCH,ROOT,canonical,digest,report_pair,ServiceError

ENGINE='0f6ebc67bd755b00945388d431e32d94183ba7fe'
SCHEMA='C3_PRESENTATION_HANDOFF_V1'
FIELDS=('ticker','name','market','industry','model','rank','signal_id','reference_close','close','own_rs20','rs20','rs_accel5','turnover20','volume_ratio','turnover_ratio','market_regime','entry_plans','structure_reason','registered_at')
CONTEXT=('business','events','quarters','sources','missing','dart_status','collected_at','price_asof','selection_use','content_sha256')


def read_retry(read,pause=time.sleep):
    """Only idempotent GitHub reads; never retry any Telegram operation."""
    for attempt in range(3):
        try:return read()
        except ServiceError as exc:
            if exc.status not in (429,500,502,503,504) or attempt==2:raise
        except (requests.Timeout,requests.ConnectionError):
            if attempt==2:raise
        pause(attempt+1)


def packet(report,ref,result,clock,outdir,dry_run=False,render_validated=None):
    from c3_telegram_notify import expected_session
    ready=bool(render_validated) if render_validated is not None else result.get('status') in ('DRY_RUN_VALIDATED_NO_DELIVERY','DELIVERED','DUPLICATE_BLOCKED')
    out={'schema':SCHEMA,'generated_at':clock.isoformat(),'expected_price_session':expected_session(clock),
         'research_ref':ref,'source_report_sha256':digest(canonical(report)),
         'source_price_asof':report.get('source_price_asof'),'attempted_price_asof':report.get('attempted_price_asof'),
         'source_run_id':report.get('source_run_id'),'source_received_at':report.get('source_received_at'),
         'source_generated_at':report.get('generated_at'),'price_provider':report.get('source_provider'),
         'data_quality_state':report.get('data_quality_state'),'current_scope':report.get('current_scope'),
         'source_errors':report.get('errors',[]),'source_collection_status':report.get('source_collection_status'),
         'primary_collection_status':report.get('primary_collection_status'),
         'alternative_cache_readiness':report.get('alternative_cache_readiness'),
         'performance':report.get('performance',{}),'status':'READY' if ready else 'NOT_READY',
         'reason':result.get('reason'),'delivery':copy.deepcopy(result),'dry_run':bool(dry_run),
         'report_code_sha':os.environ.get('GITHUB_SHA'),'report_run_id':os.environ.get('GITHUB_RUN_ID'),
         'engine_sha':(report.get('invocation') or {}).get('engine_sha'),
         'orders_enabled':False,'current_action':'CASH','chatgpt_delivery_verified':False,
         'research_top2':[],'images':[]}
    if ready:
        root=Path(outdir)
        diagnostic=json.loads((root/'render_diagnostics.json').read_text())
        if diagnostic.get('example_only'):raise ValueError('HISTORICAL_PACKET_CANNOT_BE_LIVE')
        cards=diagnostic['cards'];picks=report.get('research_top2') or []
        if len(cards)!=2 or [c['ticker'] for c in cards]!=[r['ticker'] for r in picks]:raise ValueError('HANDOFF_IMAGE_IDENTITY_MISMATCH')
        for row,card in zip(picks,cards):
            body=(root/(row['ticker']+'_integrated.png')).read_bytes()
            if card['asof']!=report['source_price_asof'] or card['sha256']!=digest(body):raise ValueError('HANDOFF_IMAGE_DATE_OR_HASH_MISMATCH')
            item={k:copy.deepcopy(row[k]) for k in FIELDS if k in row}
            ctx=row.get('company_context') or {}
            item['company_context']={k:copy.deepcopy(ctx[k]) for k in CONTEXT if k in ctx}
            item['chart_audit']={k:card[k] for k in ('source_rows','source_basis','close','change','change_pct','ma_last','last5','notes','second_entry') if k in card}
            out['research_top2'].append(item)
            out['images'].append({'ticker':row['ticker'],'name':row['ticker']+'_integrated.png','sha256':digest(body),'bytes':len(body)})
    return out


def recovery_plan(latest,summary,clock,event,mode,active_runs):
    """Recollect delayed prices, never force two candidates from valid prices."""
    from c3_telegram_notify import expected_session
    day=expected_session(clock)
    answer={'recover':False,'expected_session':day,'engine_sha':ENGINE,'reason':'EVENT_DOES_NOT_REQUEST_RECOVERY'}
    if event not in ('schedule','workflow_dispatch') or (event=='workflow_dispatch' and mode!='live'):return answer
    if day is None:return dict(answer,reason='NO_WEEKDAY_SESSION')
    if any(r.get('status') in ('queued','in_progress','waiting','pending','requested') for r in active_runs):return dict(answer,reason='EXISTING_RESEARCH_RUN_ACTIVE')
    if (latest.get('source_price_asof')==day and summary.get('source_price_asof')==day and
        latest.get('source_run_id')==summary.get('source_run_id') and latest.get('generated_at')==summary.get('generated_at') and
        latest.get('data_quality_state') in ('OFFICIAL_VERIFIED','RESEARCH_VALIDATED') and not latest.get('errors') and
        (latest.get('source_quality_gate') or {}).get('status')=='QUALITY_GATE_PASSED'):
        return dict(answer,reason='CURRENT_DATA_ALREADY_VALIDATED')
    return dict(answer,recover=True,reason='BOUNDED_LATE_DATA_RECOVERY')


def publish(gh,manifest):
    """Optimistic Git transaction: immutable run packet + derived pointer only."""
    if manifest.get('schema')!=SCHEMA or manifest.get('orders_enabled') is not False:raise ValueError('HANDOFF_SCHEMA_REJECTED')
    for _ in range(2):
        head=read_retry(lambda:gh.head(RESEARCH))
        current=json.loads(read_retry(lambda:gh.file(ROOT+'/latest.json',head)))
        if digest(canonical(current))!=manifest['source_report_sha256']:return {'status':'SOURCE_CHANGED_NOT_PUBLISHED','ref':head}
        identity=digest(canonical(manifest));archive=ROOT+'/presentation/runs/'+identity+'.json'
        prior=read_retry(lambda:gh.file(archive,head,missing_ok=True))
        if prior is not None and json.loads(prior)!=manifest:raise ValueError('HANDOFF_IMMUTABLE_CONFLICT')
        commit=read_retry(lambda:gh.api('git/commits/'+head))
        entries=[{'path':p,'mode':'100644','type':'blob','content':canonical(manifest).decode()+'\n'} for p in (archive,ROOT+'/presentation/latest.json')]
        tree=gh.api('git/trees',method='POST',payload={'base_tree':commit['tree']['sha'],'tree':entries})
        saved=gh.api('git/commits',method='POST',payload={'message':'report: preserve same-source C3 presentation handoff','tree':tree['sha'],'parents':[head]})
        try:
            gh.api('git/refs/heads/'+RESEARCH,method='PATCH',payload={'sha':saved['sha'],'force':False})
            return {'status':'PUBLISHED_RESEARCH_ONLY','commit':saved['sha'],'source_report_sha256':manifest['source_report_sha256']}
        except ServiceError as exc:
            if exc.status not in (409,422,500,502,503,504):raise
            # An uncertain Git response is reconciled by reading the actual ref.
            # This never invokes album delivery or removes its claim.
            actual=read_retry(lambda:gh.head(RESEARCH))
            stored=read_retry(lambda:gh.file(ROOT+'/presentation/latest.json',actual,missing_ok=True))
            if stored is not None and json.loads(stored)==manifest:
                return {'status':'PUBLISHED_RESEARCH_ONLY','commit':actual,'confirmed_after_uncertain_git_response':True,'source_report_sha256':manifest['source_report_sha256']}
    raise ValueError('HANDOFF_SAVE_RACE_REQUIRES_REVIEW')


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('recovery','publish'));p.add_argument('--outdir',required=True);a=p.parse_args()
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True);gh=GitHub(os.environ.get('GH_TOKEN',''))
    if a.command=='recovery':
        latest,summary,_=read_retry(lambda:report_pair(gh));runs=[]
        for workflow in ('c3_research_daily_caller.yml','c3_daily_research_v8.yml'):
            runs+=read_retry(lambda:gh.api('actions/workflows/'+workflow+'/runs?per_page=10')).get('workflow_runs',[])
        runs=[r for r in runs if str(r['id'])!=os.environ.get('GITHUB_RUN_ID')]
        value=recovery_plan(latest,summary,datetime.now(timezone.utc),os.environ.get('GITHUB_EVENT_NAME'),os.environ.get('MODE','live'),runs)
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('recover='+str(value['recover']).lower()+'\n')
    else:
        manifest=json.loads((out/'presentation.json').read_text())
        # Artifact metadata is optional and never evidence of Telegram delivery.
        artifact=os.environ.get('C3_PRESENTATION_ARTIFACT_ID','')
        if artifact:
            if not re.fullmatch(r'\d+',artifact):raise ValueError('ARTIFACT_ID_INVALID')
            manifest['artifact']={'id':int(artifact),'run_id':os.environ.get('GITHUB_RUN_ID'),'retention_days':90,'name':os.environ.get('C3_PRESENTATION_ARTIFACT_NAME','c3-integrated-delivery-evidence')}
        diagnostic=out/'supply_diagnostics.json'
        if diagnostic.exists():
            audit=json.loads(diagnostic.read_text())
            # Never attach a diagnostic from a different price decision/run.
            if audit.get('source_run_id')==manifest.get('source_run_id'):
                manifest['source_diagnostics']=audit
        value=publish(gh,manifest)
    (out/(a.command+'_status.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps(value));return 0


if __name__=='__main__':raise SystemExit(main())
