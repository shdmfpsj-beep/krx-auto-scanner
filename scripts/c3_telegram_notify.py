"""Photo-only C3 albums. Durable exclusive claim BEFORE the single send attempt."""
import argparse,hashlib,json,os,re,sys,unicodedata
from contextlib import ExitStack
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from PIL import Image
from c3_telegram_inputs import GitHub,ServiceError,RESEARCH,ROOT,EXAMPLE_ASOF,canonical,report_pair,load_example,frozen_live_bars

KST=ZoneInfo('Asia/Seoul')
RECEIPT_BRANCH='delivery/c3-top2-telegram'
EXAMPLE_REQUEST='integrated-white-gold-20261106'

def now_kst():return datetime.now(KST)
def sha(body):return hashlib.sha256(body).hexdigest()
def iso_timestamp(s):
    value=datetime.fromisoformat(str(s).replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return value.astimezone(timezone.utc)

def expected_session(clock):
    local=clock.astimezone(KST)
    if local.weekday()>=5:return None
    day=local.date()
    if local.hour*60+local.minute<930:
        day-=timedelta(days=1)
        while day.weekday()>=5:day-=timedelta(days=1)
    return day.isoformat()

def report_error(latest,summary,current):
    day=latest.get('source_price_asof')
    if day!=expected_session(current):return 'NO_NEW_COMPLETED_SESSION'
    if summary.get('source_price_asof')!=day:return 'SUMMARY_DATE_MISMATCH'
    if summary.get('source_run_id')!=latest.get('source_run_id'):return 'RUN_ID_MISMATCH'
    if summary.get('generated_at')!=latest.get('generated_at'):return 'REPORT_VERSION_MISMATCH'
    state=latest.get('data_quality_state');provider=latest.get('source_provider')
    if state=='OFFICIAL_VERIFIED':
        if provider!='KRX_OFFICIAL_EOD':return 'UNAPPROVED_PRICE_PROVIDER'
    elif state=='RESEARCH_VALIDATED':
        if provider!='FINANCEDATA_KRX_CACHE' or not re.fullmatch('[a-f0-9]{64}',latest.get('source_validation_sha256','')):return 'UNVERIFIED_ALTERNATIVE_PROOF'
    else:return 'UNVERIFIED_MARKET_DATA'
    quality=latest.get('source_quality_gate') or {};scope=latest.get('current_scope') or {};markets=quality.get('markets') or {}
    if quality.get('status')!='QUALITY_GATE_PASSED' or quality.get('errors'):return 'SOURCE_QUALITY_GATE_FAILED'
    if set(markets)!={'KOSPI','KOSDAQ'} or any(markets[m].get('rows',0)<=0 for m in markets):return 'INCOMPLETE_MARKET_COVERAGE'
    if scope.get('analysis_eligible',0)<=0 or sum(m['rows'] for m in markets.values())!=scope.get('price_rows'):return 'MARKET_ROW_COUNT_MISMATCH'
    if latest.get('errors'):return 'REPORT_HAS_UNRESOLVED_ERRORS'
    if latest.get('orders_enabled') is not False or latest.get('current_action')!='CASH':return 'LIVE_ORDER_OR_ACTION_POLICY_VIOLATION'
    if latest.get('research_top2_registered_for_source_session') is not True:return 'UNREGISTERED_RESEARCH_PREVIEW'
    picks=latest.get('research_top2') or []
    if len(picks)!=2 or len({r.get('ticker') for r in picks})!=2:return 'EXACTLY_TWO_UNIQUE_CANDIDATES_REQUIRED'
    try:
        generated=iso_timestamp(latest['generated_at']);received=iso_timestamp(latest['source_received_at'])
        if not timedelta(0)<=current.astimezone(timezone.utc)-generated<=timedelta(hours=30):return 'STALE_OR_FUTURE_REPORT'
        if not datetime.fromisoformat(day+'T15:30:00+09:00')<=received<=generated:return 'INVALID_SOURCE_RECEIPT_TIME'
    except (ValueError,TypeError,KeyError):return 'INVALID_REPORT_GENERATION_TIME'
    return None

def delivery_key(day,chat_fingerprint,mode='live'):
    if date.fromisoformat(day).isoformat()!=day or not re.fullmatch('[a-f0-9]{16}',chat_fingerprint):raise ValueError('INVALID_DELIVERY_KEY')
    kind='final' if mode=='live' else EXAMPLE_REQUEST if mode=='past_example' else None
    if kind is None:raise ValueError('UNAPPROVED_DELIVERY_MODE')
    if mode=='past_example' and day!=EXAMPLE_ASOF:raise ValueError('UNAPPROVED_EXAMPLE_DATE')
    return kind+'/'+day+'-'+chat_fingerprint

class ReceiptStore:
    def __init__(self,gh):self.gh=gh
    def initialize(self):
        # The first deployment initialized this store. Never recreate an empty
        # history after accidental deletion/reset: old sends could otherwise repeat.
        if not self.gh.api('git/ref/heads/'+RECEIPT_BRANCH,missing_ok=True):raise ValueError('RECEIPT_STORE_MISSING_MANUAL_RECONCILIATION_REQUIRED')
        raw=self.gh.file('receipts/STORE_V1.json',RECEIPT_BRANCH,missing_ok=True)
        marker=json.loads(raw) if raw is not None else {}
        if marker.get('schema')!='C3_TELEGRAM_RECEIPT_STORE_V1' or marker.get('automatic_reinitialization_allowed') is not False:raise ValueError('RECEIPT_STORE_ANCHOR_MISSING_MANUAL_RECONCILIATION_REQUIRED')
    def exists(self,key):
        return any(self.gh.file('receipts/'+folder+'/'+key+'.json',RECEIPT_BRANCH,missing_ok=True) is not None for folder in ('claims','outcomes'))
    def legacy_exists(self,day):return self.gh.file(ROOT+'/telegram_receipts/'+day+'.json',RESEARCH,missing_ok=True) is not None
    def reserve(self,key,payload):
        try:self.gh.create('receipts/claims/'+key+'.json',RECEIPT_BRANCH,payload);return True
        except ServiceError as e:
            if e.status in (409,422) and self.exists(key):return False
            raise
    def finish(self,key,payload):self.gh.create('receipts/outcomes/'+key+'.json',RECEIPT_BRANCH,payload)

def validate_photos(paths):
    if len(paths)!=2:raise ValueError('EXACTLY_TWO_PHOTOS_REQUIRED')
    hashes=[]
    for path in paths:
        p=Path(path)
        if not 0<p.stat().st_size<=10*1024*1024:raise ValueError('PHOTO_SIZE_REJECTED')
        with Image.open(p) as im:
            if im.format!='PNG' or sum(im.size)>10000 or max(im.size)/min(im.size)>20:raise ValueError('PHOTO_FORMAT_OR_DIMENSIONS_REJECTED')
            im.verify()
        hashes.append(sha(p.read_bytes()))
    if len(set(hashes))!=2:raise ValueError('DISTINCT_CARDS_REQUIRED')
    return hashes

class Telegram:
    def __init__(self,token,chat_id):
        if not token or not re.fullmatch('-?[0-9]{4,20}',chat_id):raise ValueError('TELEGRAM_CONFIGURATION_INVALID')
        self.token=token;self.chat_id=chat_id;self.fingerprint=sha(chat_id.encode())[:16]
    def verify_group(self):
        # Read-only recipient preflight; never enumerate users or send a test text.
        r=requests.post('https://api.telegram.org/bot'+self.token+'/getChat',json={'chat_id':self.chat_id},timeout=(10,25),allow_redirects=False)
        if r.status_code!=200:raise ValueError('RECIPIENT_PREFLIGHT_REJECTED')
        obj=r.json();chat=obj.get('result') or {}
        title=''.join(unicodedata.normalize('NFKC',chat.get('title','')).split())
        if not obj.get('ok') or str(chat.get('id'))!=self.chat_id or chat.get('type') not in ('group','supergroup') or title!='강현AI':raise ValueError('CONFIGURED_RECIPIENT_IS_NOT_REQUESTED_GROUP')
    def send_album(self,paths):
        media=[{'type':'photo','media':'attach://photo'+str(i)} for i in range(2)]
        with ExitStack() as stack:
            files=[('photo'+str(i),(Path(p).name,stack.enter_context(open(p,'rb')),'image/png')) for i,p in enumerate(paths)]
            # requests has zero transport retries; redirects and any POST retry are disabled.
            r=requests.post('https://api.telegram.org/bot'+self.token+'/sendMediaGroup',data={'chat_id':self.chat_id,'media':json.dumps(media)},files=files,timeout=(10,65),allow_redirects=False)
        if r.status_code!=200:raise ValueError('ALBUM_RESPONSE_UNCERTAIN_REVIEW_REQUIRED')
        reply=r.json();messages=reply.get('result') or []
        if not reply.get('ok') or len(messages)!=2 or len({m.get('message_id') for m in messages})!=2 or any(type(m.get('message_id')) is not int or m['message_id']<=0 for m in messages):raise ValueError('ALBUM_RESULT_UNCERTAIN_REVIEW_REQUIRED')
        groups={m.get('media_group_id') for m in messages}
        if len(groups)!=1 or None in groups or any('caption' in m or 'text' in m or not m.get('photo') for m in messages):raise ValueError('PHOTO_ONLY_ALBUM_CONFIRMATION_FAILED')
        if any(str(m.get('chat',{}).get('id'))!=self.chat_id for m in messages):raise ValueError('ALBUM_RECIPIENT_CONFIRMATION_FAILED')
        return dict(message_ids=[m['message_id'] for m in messages],media_group_hash=sha(next(iter(groups)).encode()),photos=2,captions_present=False,text_present=False)

def deliver(paths,report,store,bot,mode='live',clock=None):
    hashes=validate_photos(paths);day=report['source_price_asof'];key=delivery_key(day,bot.fingerprint,mode)
    store.initialize()
    if (mode=='live' and store.legacy_exists(day)) or store.exists(key):return dict(status='DUPLICATE_BLOCKED',key=key,send_attempts=0)
    bot.verify_group()
    claim={'schema':'C3_PHOTO_ONLY_DELIVERY_V1','source_date':day,'mode':mode,'status':'CLAIMED_BEFORE_SEND','claimed_at':(clock or now_kst()).isoformat(),'card_sha256':hashes,'source_run_id':report.get('source_run_id'),'sender_code_sha':os.environ.get('GITHUB_SHA'),'sender_run_id':os.environ.get('GITHUB_RUN_ID'),'recipient_verified':True,'orders_enabled':False,'automatic_resend_allowed':False}
    if not store.reserve(key,claim):return dict(status='DUPLICATE_BLOCKED',key=key,send_attempts=0)
    try:result=dict(status='DELIVERED',**bot.send_album(paths))
    except Exception as e:result=dict(status='REVIEW_REQUIRED_NO_AUTOMATIC_RESEND',error_type=type(e).__name__)
    result.update(key=key,source_date=day,mode=mode,send_attempts=1,recorded_at=now_kst().isoformat(),sender_run_id=os.environ.get('GITHUB_RUN_ID'))
    try:store.finish(key,result)
    except Exception:result['receipt_write_status']='FAILED_CLAIM_REMAINS_NO_RESEND'
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('live','past_example','preview'),default='live');p.add_argument('--outdir',default='/tmp/c3-integrated-cards');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True);result=None;source=None;ref=None;report=None
    try:
        gh=GitHub(os.environ.get('GH_TOKEN',''))
        if a.mode in ('past_example','preview'):report=load_example(gh)
        else:
            report,summary,ref=report_pair(gh);source=json.loads(json.dumps(report));reason=report_error(report,summary,now_kst())
            if reason:
                result={'status':'SKIPPED','reason':reason,'source_asof':report.get('source_price_asof'),'attempted_asof':report.get('attempted_price_asof'),'send_attempts':0};return_code=0
            else:report=frozen_live_bars(gh,report,ref)
        if result is None:
            from c3_report_context import attach_context,DartClient
            context_key=os.environ.get('OPENDART_API_KEY','').strip()
            context_client=DartClient(context_key,out/'company_raw') if context_key else None
            report=attach_context(report,out,context_client)
            from c3_classic_theme import create_cards
            paths=create_cards(report,out)
            (out/'input_diagnostics.json').write_text(json.dumps({'source_asof':report['source_price_asof'],'example_only':bool(report.get('example_only')),'provenance':report.get('input_provenance'),'sources':gh.sources},ensure_ascii=False,indent=2)+'\n')
            hashes=validate_photos(paths)
            if a.dry_run:result={'status':'DRY_RUN_VALIDATED_NO_DELIVERY','photos':len(paths),'card_sha256':hashes,'send_attempts':0};return_code=0
            elif a.mode=='preview':result={'status':'PREVIEW_ONLY_NO_DELIVERY','photos':len(paths),'send_attempts':0};return_code=0
            else:
                bot=Telegram(os.environ.get('TELEGRAM_BOT_TOKEN','').strip(),os.environ.get('TELEGRAM_CHAT_ID','').strip())
                result=deliver(paths,report,ReceiptStore(gh),bot,a.mode)
                return_code=0 if result['status'] in ('DELIVERED','DUPLICATE_BLOCKED') and 'receipt_write_status' not in result else 1
    except Exception as e:result={'status':'INTERNAL_FAILURE_NO_TEXT_SENT','error_type':type(e).__name__,'send_attempts':0,'reason':str(e) if isinstance(e,ValueError) and re.fullmatch('[A-Z_0-9]{1,90}',str(e)) else 'TRANSPORT_OR_INPUT_FAILURE'};return_code=1
    if a.mode=='live' and source is not None:
        from c3_report_handoff import packet
        try:
            # Hash the original public report; attach only verified rendered facts.
            handoff=packet(report if report is not None else source,ref,result,now_kst(),out,a.dry_run)
            handoff['source_report_sha256']=sha(canonical(source))
            (out/'presentation.json').write_text(json.dumps(handoff,ensure_ascii=False,indent=2)+'\n')
        except Exception:
            result=dict(result,handoff_status='FAILED_NO_PUBLICATION');return_code=1
    (out/'delivery_status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result));return return_code

if __name__=='__main__':sys.exit(main())
