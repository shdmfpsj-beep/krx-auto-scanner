"""Current structural entry windows, not return research or order approval.

Reuse V4 zones/stops and its existing distance budgets. A repeated support
cannot renew its expiry or be repriced upwards into a new opportunity.
Source/financial certification is a separate fail-closed approval status.
"""
import hashlib,json,math
from collections import Counter,defaultdict
from datetime import date,timedelta
from pathlib import Path

STATUSES=('ENTRY_READY','NEAR_ENTRY','WAIT_PULLBACK','MISSED_ENTRY','OVEREXTENDED','INVALID_SETUP','DATA_HOLD')
ACTIVE=('ENTRY_READY','NEAR_ENTRY')

def sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def calendar_grid(day,observed):
    """Future session dates only, never future prices or an official attestation."""
    import exchange_calendars as xc
    d=date.fromisoformat(day);cal=xc.get_calendar('XKRX',start=str(d-timedelta(days=800)),end=str(d+timedelta(days=25)))
    reference=[x.strftime('%Y-%m-%d') for x in cal.sessions if day<x.strftime('%Y-%m-%d')]
    if not observed or observed[-1]!=day or observed!=sorted(set(observed)):raise ValueError('WINDOW_OBSERVED_CALENDAR_MISMATCH')
    return list(observed)+reference

def anchor(plan):
    ev=plan.get('evidence') or {};sr=plan.get('stop_reliability') or {}
    ds=[ev.get(k) for k in ('retest_date','touch_date','low_date','pivot_date') if ev.get(k)]
    if not ds:ds=[p['date'] for p in ev.get('confirmed_pivots',[]) if p.get('date')]
    when=max(ds) if ds else None
    level=plan.get('invalidation_low',sr.get('original_low',plan.get('support')))
    return dict(date=when,level=level,structure=plan.get('structure_type',plan.get('method')))

def setup_key(ticker,plan):return sha(dict(ticker=ticker,anchor=anchor(plan)))

def price_signature(plan):
    r=plan.get('range') or {}
    return dict(low=r.get('low',plan.get('structural_low')),high=r.get('high',plan.get('structural_high')),
        stop=plan.get('stop'),r1=plan.get('r1'),r2=plan.get('r2'))

def confirmed_asof(plan,day):
    ev=plan.get('evidence') or {};sr=plan.get('stop_reliability') or {}
    dates=[plan.get('support_known_on'),sr.get('confirmed_on')]+[p.get('known_on') for p in ev.get('confirmed_pivots',[])]
    return all(d<=day for d in dates if d) and (anchor(plan)['date'] is None or anchor(plan)['date']<=day)

def add_sessions(day,n,grid):
    if type(n) is not int or n<1 or n>3:raise ValueError('WINDOW_EXISTING_VALIDITY_INVALID')
    if day not in grid or grid.index(day)+n>=len(grid):raise ValueError('WINDOW_EXPIRY_CALENDAR_UNAVAILABLE')
    return grid[grid.index(day)+n]

def originals(state,day):
    """Read hash-verified immutable selections; never rewrite a registered plan."""
    from c3_forward_ledger_v8 import read_record,hash_value
    result=defaultdict(list)
    paths=Path(state)/'reports/c3_forward_v8/lanes/krx_unadjusted_v12/decisions'
    for path in sorted(paths.glob('*.json')):
        doc=read_record(path);source_day=doc.get('price_asof')
        if not source_day or source_day>=day:continue
        models=doc.get('models',{});selected={}
        for model in ('A','B'):
            for row in models.get(model,[]):
                p=(row.get('entry_plans',{}).get('A_SUPPORT_LIMIT') or {}).get('plan')
                if p is None:continue
                if not 0<p['stop']<p['low']<=p['high']:continue
                selected[row['ticker']]=dict(ticker=row['ticker'],name=row['name'],source_date=source_day,
                    source_run_id=row.get('source_run_id'),model=model,signal_id=row.get('signal_id'),
                    low=p['low'],high=p['high'],stop=p['stop'],r1=p.get('resistance'),r2=p.get('resistance2'),
                    support_date=p.get('support_date'),validity_sessions=row.get('order_validity_sessions',1),
                    record_path=path.relative_to(Path(state)).as_posix(),record_payload_sha256=hash_value(doc),plan_sha256=sha(p),
                    immutable_original=True,original_plan_modified=False)
        for t,value in selected.items():result[t].append(value)
    return dict(result)

def research_history(state,day):
    result=defaultdict(list)
    for path in sorted((Path(state)/'reports/c3_new_session_v1/reviews').glob('*/*.json')):
        r=json.loads(path.read_text());d=r.get('source_date')
        if not d or d>day:continue
        body=dict(r);digest=body.pop('report_payload_sha256',None)
        if sha(body)!=digest:raise ValueError('ENTRY_WINDOW_PRIOR_REVIEW_HASH_MISMATCH')
        saved=r.get('entry_window_evaluations',{})
        for t,w in saved.items():
            if w.get('setup_key'):
                result[t].append(dict(setup_key=w['setup_key'],first_observed_on=w['first_observed_on'],
                    first_observed_at=w.get('first_observed_at',r.get('generated_at')),
                    frozen_price_signature=w['frozen_price_signature'],report_hash=digest,source_date=d))
        # Existing V4 reviews contain a frozen price plan even before this
        # status layer existed. Preserve its first observed day and prices.
        for row in r.get('final_research_top2',[]):
            p=row.get('display_plan')
            if p:result[row['ticker']].append(dict(setup_key=setup_key(row['ticker'],p),first_observed_on=d,
                first_observed_at=r.get('generated_at'),
                frozen_price_signature=price_signature(p),report_hash=digest,source_date=d))
    return dict(result)

def classify(row,bars,day,grid,prior=(),history=(),protocol=None):
    protocol=protocol or {};t=row['ticker'];close=row.get('close');reasons=[]
    result=dict(ticker=t,name=row['name'],asof=day,status='DATA_HOLD',reason_codes=reasons,
        scope='RESEARCH_PRICE_POSITION_NOT_BUY_APPROVAL',approval_status='DATA_HOLD',buy_approved=False,
        actual_orders=0,research_fit_eligible=False,first_observed_on=None,valid_until_session=None,
        setup_key=None,frozen_price_signature=None,old_entry_window=None,second_entry_status='NOT_VALIDATED_NOT_PROVIDED',
        current_price_is_completed_daily_close=True,profitability_study_executed=False,
        official_regular_and_financial_pit_certified=False)
    if not bars or bars[-1]['date']!=day or not isinstance(close,(int,float)) or not math.isfinite(close) or close<=0 or close!=bars[-1]['close']:
        reasons.append('PRICE_DATE_OR_CLOSE_UNVERIFIED');return result
    if any(b['date']>day for b in bars):raise ValueError('WINDOW_FUTURE_PRICE_NOT_ALLOWED')
    q=row.get('financial',{})
    if not q.get('required_metrics_complete'):
        reasons.append('FINANCIAL_DATA_MISSING_NOT_COMPANY_FAILURE');return result
    if len(bars)<65:reasons.append('PRICE_HISTORY_INSUFFICIENT');return result
    if day not in grid or grid.index(day)+1>=len(grid):reasons.append('NEXT_REFERENCE_SESSION_UNAVAILABLE');return result
    next_day=grid[grid.index(day)+1];result['next_reference_execution_session']=next_day
    previous=max((p for p in prior if p['source_date']<day),key=lambda p:p['source_date'],default=None)
    if previous:
        previous=dict(previous);previous['valid_until_session']=add_sessions(previous['source_date'],previous['validity_sessions'],grid)
        previous['expired_for_next_entry']=next_day>previous['valid_until_session'];result['old_entry_window']=previous
    review=row.get('range_review') or {};best=review.get('best');plans=review.get('plans') or []
    eligible_data=bool(q.get('observed_positive') and row.get('momentum_pass') and row.get('liquidity_pass'))
    result['quality_momentum_liquidity_eligible']=eligible_data
    valid=bool(best and best.get('range_valid') and best.get('stop_reliability',{}).get('research_eligible'))
    if valid:
        p=best;r=p['range'];a=anchor(p);key=setup_key(t,p);signature=price_signature(p)
        if not confirmed_asof(p,day):
            reasons.append('SUPPORT_CONFIRMATION_NOT_YET_KNOWN');result['status']='INVALID_SETUP';return result
        same=sorted((h for h in history if h['setup_key']==key),key=lambda h:h['first_observed_on'])
        first=same[0]['first_observed_on'] if same else day;frozen=same[0]['frozen_price_signature'] if same else signature
        if first>day:raise ValueError('WINDOW_FIRST_OBSERVATION_FROM_FUTURE')
        validity=p.get('default_validity_sessions',1);expires=add_sessions(first,validity,grid)
        result.update(setup_key=key,first_observed_on=first,valid_until_session=expires,
            first_observed_source_date=first,first_observed_at=same[0].get('first_observed_at') if same else None,
            frozen_price_signature=frozen,anchor=a,range=[r['low'],r['high']],stop=p['stop'],r1=p['r1'],r2=p.get('r2'),
            width_atr=r.get('width_atr'),stop_reliability=p['stop_reliability']['status'])
        if not a['date'] or a['date']>day:
            reasons.append('CONFIRMED_SUPPORT_EVENT_DATE_MISSING');result['status']='INVALID_SETUP';return result
        if signature!=frozen:
            reasons.append('SAME_SUPPORT_REPRICING_IS_NOT_A_NEW_ENTRY');result['status']='INVALID_SETUP';return result
        if next_day>expires:
            reasons.append('ORIGINAL_RESEARCH_ENTRY_WINDOW_EXPIRED');result['status']='MISSED_ENTRY';return result
        if previous and not same and a['date']<=previous['source_date']:
            reasons.append('OLD_SUPPORT_CANNOT_RESTART_AN_EXPIRED_ENTRY_WINDOW');result['status']='MISSED_ENTRY';return result
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (p.get('stop'),r.get('low'),r.get('high'),p.get('r1'))) or not 0<p['stop']<r['low']<=r['high']<p['r1'] or close<p['stop']:
            reasons.append('STRUCTURE_OR_RESISTANCE_INVALID');result['status']='INVALID_SETUP';return result
        atr=p['atr14'];distance=max(0,close-r['high']);pct=100*distance/close;atr_distance=distance/atr if atr>0 else None
        result.update(distance_to_upper_pct=pct,distance_to_upper_atr=atr_distance,
            upper_stop_risk_pct=r['endpoints']['upper']['stop_risk_pct'],min_net_r1_rr=r['min_net_r1_rr'],
            new_support_after_original=bool(previous and a['date']>previous['source_date']))
        if r['low']<=close<=r['high']:
            result['status']='ENTRY_READY';reasons.append('CLOSE_INSIDE_VALIDATED_RESEARCH_RANGE')
        elif close>r['high'] and pct<=protocol['max_distance_pct'] and atr_distance is not None and atr_distance<=protocol['max_distance_atr']:
            result['status']='NEAR_ENTRY';reasons.append('NEAREST_RANGE_EDGE_INSIDE_EXISTING_DISTANCE_BUDGET')
        elif close<r['low']:
            result['status']='INVALID_SETUP';reasons.append('CLOSE_BELOW_RESEARCH_RANGE_NO_CATCHING_A_FALL')
        else:result['status']='WAIT_PULLBACK';reasons.append('RANGE_NOT_CURRENTLY_ACCESSIBLE')
        result['research_fit_eligible']=result['status'] in ACTIVE and eligible_data and len(bars)>=119
        if len(bars)<119:reasons.append('FULL_VISIBLE_MA60_HISTORY_LT_119')
        if not eligible_data:reasons.append('EXISTING_COMPANY_MOMENTUM_OR_LIQUIDITY_GATE_FAIL')
        return result
    # No current valid setup: old levels are explanatory history, not new orders.
    if previous and close<previous['stop']:
        result['status']='INVALID_SETUP';reasons.append('FROZEN_ORIGINAL_SUPPORT_INVALIDATED');return result
    if previous and previous.get('r1') is not None and close>=previous['r1']:
        result['status']='MISSED_ENTRY';reasons.append('ORIGINAL_R1_ALREADY_REACHED_WITHOUT_NEW_VALID_SUPPORT');return result
    zones=[]
    for p in plans:
        sr=p.get('stop_reliability') or {};upper=p.get('structural_high');atr=p.get('atr14')
        if sr.get('research_eligible') and confirmed_asof(p,day) and isinstance(upper,(int,float)) and 0<upper<close and isinstance(atr,(int,float)) and atr>0:
            zones.append(dict(high=upper,low=p.get('structural_low'),distance_pct=100*(close-upper)/close,
                distance_atr=(close-upper)/atr,anchor=anchor(p),stop=p.get('stop')))
    nearest=min(zones,key=lambda z:z['distance_atr'],default=None);result['nearest_confirmed_structure']=nearest
    from c3_watch_quality_audit_v1 import price_metrics
    pm=price_metrics(bars,day);result['ma20_extension_pct']=pm['ma20_extension_pct'];result['ma20_extension_atr']=pm['ma20_extension_atr']
    if nearest and (nearest['distance_pct']>protocol['max_distance_pct'] or nearest['distance_atr']>protocol['max_distance_atr']) and (pm['ma20_extension_atr'] or 0)>protocol['max_distance_atr']:
        result['status']='OVEREXTENDED';reasons.append('NO_VALID_NEAR_SUPPORT_AND_PRICE_EXTENDED_BEYOND_EXISTING_ATR_BUDGET');return result
    if previous and previous['expired_for_next_entry']:
        result['status']='MISSED_ENTRY';reasons.append('ORIGINAL_ENTRY_VALIDITY_EXPIRED_NO_NEW_VALID_SUPPORT');return result
    if nearest:
        result['status']='WAIT_PULLBACK';reasons.append('CONFIRMED_SUPPORT_EXISTS_BUT_CURRENT_RANGE_NOT_VALID')
    else:result['status']='INVALID_SETUP';reasons.append('NO_VALID_STRUCTURAL_STOP_AND_RANGE')
    return result

def evaluate(rows,current,day,observed,state,protocol,observed_at=None):
    grid=calendar_grid(day,observed);prior=originals(state,day);history=research_history(state,day)
    values={r['ticker']:classify(r,current[r['ticker']],day,grid,prior.get(r['ticker'],()),history.get(r['ticker'],()),protocol) for r in rows}
    for w in values.values():
        if w.get('setup_key') and w.get('first_observed_at') is None:w['first_observed_at']=observed_at
    return dict(schema='C3_ENTRY_WINDOW_EVALUATIONS_V1',asof=day,rows=values,
        counts=dict(Counter(v['status'] for v in values.values())),approved_buy_count=0,
        policy='REUSE_V4_STRUCTURE_DISTANCE_AND_VALIDITY_NO_PRICE_UPWARD_ADJUSTMENT',
        price_and_financial_certification='DATA_HOLD',orders_enabled=False,telegram_requests=0,
        reference_calendar_not_official_attestation=True,performance_research_executed=False)

def select_entry_fit(pool,by,windows,limit=2):
    selected=[]
    for stock in pool:
        t=stock['ticker'];w=windows[t];row=by[t];p=row['range_review']['best']
        if not w['research_fit_eligible'] or w['status'] not in ACTIVE or p is None:continue
        if row.get('history_rows',119)<119:continue
        selected.append(dict(row,display_plan=p,status=w['status'],entry_window=w,data_status='UNVERIFIED',
            buy_approved=False,research_rank=len(selected)+1,selection_scope='FULL_QUALITY_POOL_CURRENT_ENTRY_WINDOW'))
        if len(selected)>=limit:break
    return selected

def report_order(entry_cards,watch_cards,report):
    primary=[dict(c,role='ENTRY_FIT' if c.get('ticker') else 'PRIMARY_STATUS',relative_to_analysis='cards/'+c['png']) for c in entry_cards]
    used={c.get('ticker') for c in primary};secondary=[dict(c,role='WATCH_ONLY',relative_to_analysis='watch_cards/'+c['png']) for c in watch_cards if c.get('ticker') not in used]
    return dict(schema='C3_ENTRY_FIRST_REPORT_ORDER_V1',primary_section='ENTRY_FIT',asof=report['source_date'],
        source_run_id=report['source_run_id'],source_hash=report['source_hash'],report_hash=report['report_payload_sha256'],
        ordered_images=primary+secondary,approval_status='DATA_HOLD',buy_approved=False,telegram_requests=0)

def data_hold_card(report,path):
    """A failed/incomplete selection is never illustrated as zero qualified stocks."""
    from PIL import Image,ImageDraw,PngImagePlugin
    from c3_classic_theme import W,H,PAPER,INK,GOLD,RED,SUB,text,wrap
    im=Image.new('RGB',(W,H),PAPER);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,98),fill=INK);text(d,52,26,'강현AI PRO | C3 TOP2',46,'#F3E6CD',True)
    text(d,1345,37,report['source_date'],31,'#EEEAE2',anchor='ra')
    text(d,700,300,'DATA_HOLD',100,GOLD,True,anchor='ma')
    text(d,700,505,'자료 검증 보류 · 종목 선정 미완료',46,INK,True,anchor='ma')
    for i,value in enumerate(['후보 없음 확정과 자료 부족을 구분합니다.','가격·재무 자료가 확인되기 전 매수 승인은 CASH입니다.','이전 거래일 후보를 현재 후보로 대체하지 않습니다.','실제 주문·Telegram 전송은 없습니다.']):
        for k,line in enumerate(wrap(d,value,1200,34,3)):text(d,100,800+i*230+k*44,line,34,SUB)
    text(d,700,2200,'연구용 · BUY 승인 없음',34,RED,True,anchor='ma')
    payload=dict(price_asof=report['source_date'],status='DATA_HOLD',selection_completed=False,
        source_run_id=report['source_run_id'],source_hash=report['source_hash'],report_hash=report['report_payload_sha256'],buy_approved=False)
    info=PngImagePlugin.PngInfo();info.add_text('C3_manifest',json.dumps(payload,ensure_ascii=False,sort_keys=True))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);im.save(path,pnginfo=info,optimize=True)
    return dict(payload,png=path.name,png_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
