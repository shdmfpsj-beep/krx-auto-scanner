"""Same-date morning status, image-only at-most-once delivery and derived log.

No experimental threshold/model or uncertified source can authorize a BUY.
Existing final/correction outcomes are read before recipient/network calls.
"""
import argparse,base64,copy,hashlib,json,os,re
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageDraw,PngImagePlugin
from c3_classic_theme import font
from c3_telegram_inputs import GitHub,ROOT,RESEARCH,canonical,digest,report_pair,ServiceError
from c3_telegram_notify import ReceiptStore,Telegram,RECEIPT_BRANCH,delivery_key,deliver


def packet(source,entry=None,company=None):
    day=source.get('requested_day')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(day)):raise ValueError('MORNING_PACKET_SOURCE_DATE_REQUIRED')
    good=source.get('status')=='OFFICIAL_CACHE_MATCHED' and source.get('ready') is True
    analysis=bool(good and entry and entry.get('price_asof')==day and
        entry.get('full_market_price_rows')==source.get('compared_rows') and
        re.fullmatch('[a-f0-9]{64}',str(entry.get('original_frozen_decision_payload_sha256',''))) and
        entry.get('source_proof_sha256')==digest(canonical(source)+b'\n'))
    # SHA is over the exact source-proof file bytes, not a re-labelled boolean.
    reasons=[]
    if not good:reasons.append('OFFICIAL_SOURCE_NOT_READY')
    if not analysis:reasons.append('ANALYSIS_NOT_VERIFIED_FOR_THIS_SOURCE')
    if source.get('regular_only_certified') is not True:reasons.append('REGULAR_ONLY_SOURCE_UNCERTIFIED')
    reasons.append('EXPERIMENTAL_ENTRY_MODEL_NOT_APPROVED')
    if not company or company.get('asof')!=day:reasons.append('COMPANY_REVIEW_NOT_READY')
    else:reasons.extend(company.get('blockers',[]))
    return dict(schema='C3_MORNING_FINAL_STATUS_V1',asof=day,generated_at=datetime.now(timezone.utc).isoformat(),
        source_run_id=entry.get('original_source_run_id') if analysis else None,
        frozen_decision_payload_sha256=entry.get('original_frozen_decision_payload_sha256') if analysis else None,
        original_source_validation_sha256=entry.get('original_source_validation_sha256') if analysis else None,
        morning_run_id=os.environ.get('C3_MORNING_SOURCE_RUN_ID') or os.environ.get('GITHUB_RUN_ID'),source_sha256=digest(canonical(source)),
        entry_review_sha256=digest(canonical(entry)) if entry else None,
        source=copy.deepcopy(source),analysis_completed=analysis,
        scope={k:entry.get(k) for k in ('full_market_price_rows','analysis_eligible','stock_preselector_count','original_b_filter_count','reviewed_technical_tickers')} if analysis else {},
        geometry_research_pass_count=entry.get('eligible_entry_feasible_tickers') if analysis else None,
        company_status_counts=company.get('company_status_counts') if company else {},
        status='SELECTION_HELD',final_candidate_count=None,final_top2=[],decision='CASH',
        buy_approved=False,orders_enabled=False,blockers=sorted(set(reasons)),
        experimental_thresholds_promoted=False,original_signals_modified=False,
        delivery={'status':'NOT_ATTEMPTED','send_attempts':0})


def render(report,outdir):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(1200,1580),'#FAF9F5');d=ImageDraw.Draw(im)
    ink='#292B2C';sub='#6C7073';gold='#AC8848'
    def txt(x,y,text,size=34,color=ink,bold=False):d.text((x,y),text,font=font(size,bold),fill=color)
    d.rectangle((0,0,1200,112),fill=ink);txt(55,30,'강현AI PRO | C3 TOP2',44,'#F3E6CD',True)
    txt(70,165,report['asof']+' 기준 · 오전 검증',45,ink,True)
    txt(70,270,'CASH',115,gold,True)
    txt(75,440,'매수 승인 보류 · 선정 미완료',49,ink,True)
    source_ok=report['source'].get('ready') is True
    txt(75,550,'정규장 거래량·거래대금 출처 인증 미완료' if source_ok else '전일 공식자료 확보·검증 미완료',31,'#B84B48',True)
    scope=report['scope'];rows=[('공식·캐시 대조',str(report['source'].get('compared_rows','대기'))),
        ('분석 가능 종목',str(scope.get('analysis_eligible','대기'))),
        ('기술적 후보 / 타점 검사',str(scope.get('stock_preselector_count','대기'))+' / '+str(scope.get('reviewed_technical_tickers','대기'))),
        ('연구용 타점 조건 통과',str(report.get('geometry_research_pass_count') if report.get('geometry_research_pass_count') is not None else '대기'))]
    y=680
    for label,value in rows:
        txt(80,y,label,34);txt(875,y,value,34,gold,True);d.line((75,y+63,1120,y+63),fill='#DEDAD1',width=2);y+=108
    txt(75,1180,'연구 조건 통과 수와 최종 매수 후보 수는 다릅니다.',29,sub)
    txt(75,1240,'재무 자료는 기준일·접수번호와 함께 별도 검토합니다.',29,sub)
    txt(75,1325,'범위 미도달 PASS · 미인증 자료는 CASH 유지',31,ink,True)
    txt(75,1410,'자동 주문 없음 · 이전 거래일 추천으로 대체하지 않음',27,sub)
    metadata=PngImagePlugin.PngInfo()
    for k in ('asof','source_run_id','frozen_decision_payload_sha256','source_sha256','entry_review_sha256','morning_run_id'):
        metadata.add_text(k,json.dumps(report.get(k)))
    p=out/'C3_morning_status.png';im.save(p,optimize=True,pnginfo=metadata)
    validate_image(p,report)
    report['image']={'name':p.name,'sha256':digest(p.read_bytes()),'bytes':p.stat().st_size}
    return p


def validate_image(path,report):
    with Image.open(path) as im:
        if im.format!='PNG' or im.size!=(1200,1580):raise ValueError('MORNING_STATUS_IMAGE_INVALID')
        for k in ('asof','source_run_id','frozen_decision_payload_sha256','source_sha256','entry_review_sha256','morning_run_id'):
            if json.loads(im.info.get(k,'"MISSING"'))!=report.get(k):raise ValueError('MORNING_IMAGE_SOURCE_LINEAGE_MISMATCH')
        im.verify()


def prepared_image(source,entry,company,report_path,image_path,outdir):
    """Send the exact completed artifact bytes, never a later re-render."""
    report=json.loads(Path(report_path).read_text());expected=packet(source,entry,company)
    fields=('schema','asof','source_run_id','frozen_decision_payload_sha256',
        'original_source_validation_sha256','morning_run_id','source_sha256','entry_review_sha256',
        'analysis_completed','scope','geometry_research_pass_count','company_status_counts',
        'status','final_candidate_count','final_top2','decision','buy_approved','orders_enabled','blockers')
    if any(report.get(k)!=expected.get(k) for k in fields):raise ValueError('PREPARED_MORNING_REPORT_SOURCE_MISMATCH')
    body=Path(image_path).read_bytes()
    if digest(body)!=(report.get('image') or {}).get('sha256'):raise ValueError('PREPARED_MORNING_IMAGE_HASH_MISMATCH')
    validate_image(image_path,report)
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    target=out/'C3_morning_status.png';target.write_bytes(body)
    return report,target


def known_recipient_fingerprint(gh):
    marker=json.loads(gh.file('receipts/STORE_V1.json',RECEIPT_BRANCH))
    obj=gh.api('git/blobs/'+marker['first_verified_outcome_blob_sha'])
    prior=json.loads(base64.b64decode(obj['content']))
    if prior.get('status')!='DELIVERED':raise ValueError('VERIFIED_RECIPIENT_ANCHOR_REQUIRED')
    fingerprint=prior['key'].rsplit('-',1)[1]
    if not re.fullmatch('[a-f0-9]{16}',fingerprint):raise ValueError('RECIPIENT_FINGERPRINT_INVALID')
    return fingerprint


def delivery_preflight(gh,day,fingerprint):
    store=ReceiptStore(gh);store.initialize();key=delivery_key(day,fingerprint)
    if store.legacy_exists(day) or store.exists(key):return {'status':'DUPLICATE_BLOCKED','send_attempts':0,'key':key}
    tree=gh.api('git/trees/'+gh.head(RECEIPT_BRANCH)+'?recursive=1')
    if tree.get('truncated'):raise ValueError('RECEIPT_INVENTORY_INCOMPLETE')
    if any(r['type']=='blob' and r['path'].startswith(('receipts/claims/','receipts/outcomes/')) and
           '/'+day+'-' in r['path'] and r['path'].endswith('-'+fingerprint+'.json') for r in tree['tree']):
        return {'status':'DUPLICATE_BLOCKED','send_attempts':0,'key':key,'prior_date_delivery_or_correction_preserved':True}
    return {'status':'READY_NO_PRIOR_DATE_CLAIM','send_attempts':0,'key':key}


def finish_delivery(report,image,gh,send=False,bot=None):
    validate_image(image,report)
    if report.get('status')!='SELECTION_HELD' or report.get('final_top2')!=[] or report.get('buy_approved') is not False or report.get('orders_enabled') is not False:
        raise ValueError('UNAPPROVED_MORNING_RECOMMENDATION')
    # An early failed collection/registration cannot consume the final date
    # claim and block the scheduled 08:20/30 recovery. No Telegram/store call.
    if report.get('analysis_completed') is not True:
        return {'status':'DEFERRED_SOURCE_OR_REGISTRATION_NOT_READY','send_attempts':0,'final_date_claim_created':False}
    fingerprint=bot.fingerprint if bot is not None else known_recipient_fingerprint(gh)
    preflight=delivery_preflight(gh,report['asof'],fingerprint)
    if preflight['status']=='DUPLICATE_BLOCKED':return preflight
    if not send:return dict(preflight,status='DRY_RUN_NO_DELIVERY')
    if bot is None:raise ValueError('MORNING_DELIVERY_BOT_REQUIRED')
    # Same durable final/date claim and the existing verified destination.
    payload=dict(source_price_asof=report['asof'],source_run_id=report['source_run_id'],
        source_validation_sha256=report['original_source_validation_sha256'],research_top2=[],
        input_provenance={'decision_payload_sha256':report['frozen_decision_payload_sha256']},
        morning_source_proof_sha256=report['source_sha256'],
        morning_status_sha256=digest(canonical(report)),status='SELECTION_HELD',orders_enabled=False)
    return deliver([image],payload,ReceiptStore(gh),bot)


def publish(gh,report):
    from c3_report_handoff import active_research,read_retry
    if any(r.get('status')!='queued' for r in active_research(gh)):
        return {'status':'RESEARCH_ACTIVE_PUBLICATION_DEFERRED'}
    head=gh.head(RESEARCH)
    identity=digest(canonical(report));base=gh.api('git/commits/'+head)
    entries=[dict(path=p,mode='100644',type='blob',content=canonical(report).decode()+'\n') for p in
        ('reports/c3_morning_v1/runs/'+identity+'.json','reports/c3_morning_v1/latest.json')]
    tree=gh.api('git/trees',method='POST',payload={'base_tree':base['tree']['sha'],'tree':entries})
    commit=gh.api('git/commits',method='POST',payload={'tree':tree['sha'],'parents':[head],'message':'report: preserve derived morning source/entry/delivery status'})
    try:gh.api('git/refs/heads/'+RESEARCH,method='PATCH',payload={'sha':commit['sha'],'force':False})
    except ServiceError:return {'status':'SOURCE_RACE_PUBLICATION_DEFERRED'}
    return {'status':'PUBLISHED_DERIVED_ONLY','commit':commit['sha']}


def protected_snapshot(gh):
    result={};refs={}
    for branch,prefixes in ((RESEARCH,(ROOT+'/lanes/',ROOT+'/key_envelopes/',ROOT+'/bootstrap/')),
                            (RECEIPT_BRANCH,('receipts/',))):
        ref=gh.head(branch);refs[branch]=ref
        tree=gh.api('git/trees/'+ref+'?recursive=1')
        if tree.get('truncated'):raise ValueError('PROTECTED_TREE_INCOMPLETE')
        result[branch]={r['path']:r['sha'] for r in tree['tree'] if r['type']=='blob' and any(r['path'].startswith(p) for p in prefixes)}
    return result,refs


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--entry');p.add_argument('--company');p.add_argument('--outdir',required=True);p.add_argument('--send',action='store_true');p.add_argument('--publish',action='store_true')
    p.add_argument('--prepared-report');p.add_argument('--prepared-image');a=p.parse_args()
    load=lambda name:json.loads(Path(name).read_text()) if name and Path(name).exists() else None
    gh=GitHub(os.environ.get('GH_TOKEN',''))
    before,before_refs=protected_snapshot(gh)
    out=Path(a.outdir)
    if a.prepared_report:
        result,image=prepared_image(load(a.source),load(a.entry),load(a.company),a.prepared_report,a.prepared_image,out)
    else:result=packet(load(a.source),load(a.entry),load(a.company));image=render(result,out)
    bot=Telegram(os.environ.get('TELEGRAM_BOT_TOKEN',''),os.environ.get('TELEGRAM_CHAT_ID','')) if a.send and result.get('analysis_completed') is True else None
    result['delivery']=finish_delivery(result,image,gh,a.send,bot)
    (out/'morning_final.json').write_bytes(canonical(result)+b'\n')
    if a.publish:
        publication=publish(gh,result);(out/'publication.json').write_bytes(canonical(publication)+b'\n')
    after,after_refs=protected_snapshot(gh)
    unchanged=all(after[b].get(p)==sha for b,items in before.items() for p,sha in items.items())
    integrity=dict(original_protected_blobs_unchanged=unchanged,
        before_refs=before_refs,after_refs=after_refs,
        protected_counts={b:len(v) for b,v in before.items()},
        protected_sha256=digest(canonical(before)),orders_enabled=False,
        source_lane_write_requests=0,send_attempts=result['delivery'].get('send_attempts',0))
    (out/'morning_integrity.json').write_bytes(canonical(integrity)+b'\n')
    if not unchanged:raise ValueError('ORIGINAL_PROTECTED_RECORD_CHANGED')
    print(json.dumps(dict(asof=result['asof'],status=result['status'],delivery=result['delivery']['status'],send_attempts=result['delivery'].get('send_attempts',0))))
    if a.send and (result['delivery'].get('status') not in ('DELIVERED','DUPLICATE_BLOCKED','DEFERRED_SOURCE_OR_REGISTRATION_NOT_READY') or 'receipt_write_status' in result['delivery']):
        raise SystemExit(1)
