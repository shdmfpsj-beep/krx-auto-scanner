"""Preserve pre-move observations independently of the legacy late-stage filter.

Price observations have no company-health, instrument-type or trade approval.
The completed reference ETF supplies a session grid, not regular-only proof.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import csv,gzip,hashlib,io,json,math,os,re
from copy import deepcopy
import pandas as pd
from c3_premove_stage_v1 import classify_contextual,valid_price_tail,STAGE_POLICY,WORK_ORIGIN_SHA256

CSV_NAME='c3_premove_observations_v1.csv'
HISTORY_NAME='c3_premove_history_v1.csv.gz'
STATUS_NAME='c3_premove_observation_status_v1.json'
FIELDS=['ticker','asof','observation_status','track','price_stage_pass','close','source',
    'ret5','ret20','ret60','ret120','ret252','rsi14','slow_k','slow_d','rsi_change3','k_change3',
    'above_ma20_atr','from_floor_atr','range10_previous20','retained_sessions',
    'floor_date','floor_confirmed_at','floor_low','annual_context_known',
    'normalized_frame_sha256','raw_reported_turnover_value','raw_reported_turnover_column',
    'turnover_scope_certified','company_health_verified','instrument_type_verified','buy_approved','reason']
HISTORY_FIELDS=['ticker','date','open','high','low','close','volume','source']
WATCH_HISTORY='c3_registered_followup_history_v1.csv.gz'
WATCH_STATUS='c3_registered_followup_status_v1.json'
WATCH_REGISTRY='c3_registered_reclaim_registry_v1.json'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def atomic(path,raw):
    p=Path(path);tmp=p.with_suffix(p.suffix+'.pending');tmp.write_bytes(raw);tmp.replace(p)
def csv_bytes(rows,fields):
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    return s.getvalue().encode('utf-8-sig')
def normalized(source):
    b=source.copy(deep=True)
    rename={'시가':'Open','고가':'High','저가':'Low','종가':'Close','거래량':'Volume'}
    b=b.rename(columns=rename)
    if 'Date' not in b:
        b['Date']=[pd.Timestamp(x).date().isoformat() for x in b.index]
    b['Date']=b.Date.astype(str)
    required=['Date','Open','High','Low','Close','Volume']
    if not set(required)<=set(b):raise ValueError('SOURCE_OHLCV_COLUMNS_MISSING')
    return b[required].reset_index(drop=True)
def clean_number(x):
    if isinstance(x,float) and not math.isfinite(x):return None
    return x

def object_digest(value):
    return digest(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())

def validate_registered_watch(value):
    payload=deepcopy(value);identity=payload.pop('registry_id',None)
    if payload.get('schema')!='C3_REGISTERED_RECLAIM_COHORT_V1' or identity!=object_digest(payload):
        raise ValueError('REGISTERED_COHORT_DIGEST_MISMATCH')
    setup_ids=set();tickers=set()
    for original in payload.get('setups',[]):
        f=deepcopy(original);record_key=f.pop('record_id',None);key=f.get('setup_id');t=f.get('ticker')
        if record_key!=object_digest(f) or not re.fullmatch(r'[0-9a-f]{64}',str(key)) or not re.fullmatch(r'\d{6}',str(t)):
            raise ValueError('FROZEN_SETUP_DIGEST_OR_TICKER_INVALID')
        clock=datetime.fromisoformat(f['registered_at_utc'])
        if clock.tzinfo is None:raise ValueError('REGISTRATION_TIMEZONE_REQUIRED')
        if key in setup_ids or t in tickers:raise ValueError('DUPLICATE_REGISTERED_SETUP')
        if f['price_asof']!=payload['baseline_price_asof'] or f['registered_at_utc']!=payload['registered_at_utc']:
            raise ValueError('MIXED_REGISTRATION_COHORT')
        setup_ids.add(key);tickers.add(t)
    if not tickers or len(tickers)!=payload['registered_count']:raise ValueError('REGISTERED_COUNT_MISMATCH')
    return deepcopy(value)

def load_registered_watch(path):
    return validate_registered_watch(json.loads(Path(path).read_text(encoding='utf-8')))

def registered_failure(outdir,cutoff,error,run_context=None):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    result=dict(schema='C3_REGISTERED_FOLLOWUP_CAPTURE_V1',capture_completed=False,
        requested_cutoff=str(cutoff),error=type(error).__name__+':'+str(error),
        run_context=run_context or {k:os.environ.get(v) for k,v in [
            ('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT'),('commit','GITHUB_SHA')]},
        stale_previous_outputs_not_accepted=True,approved_buy_count=0,orders_enabled=False)
    atomic(out/WATCH_STATUS,(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    return result

def export_registered_watch(observer,out,asof,calendar,calendar_source,rows,calendar_ok):
    registry=observer.registered_watch
    if registry is None:return None
    states=[];history=[];by={r['ticker']:r for r in rows}
    for f in registry['setups']:
        t=f['ticker'];item=dict(ticker=t,setup_id=f['setup_id'],name=f['name'],
            registered_at_utc=f['registered_at_utc'],baseline_price_asof=f['price_asof'],
            observed=False,history_rows=0,source_response=None,regular_only_scope_verified=False,
            current_price_stage_pass=bool(by.get(t,{}).get('price_stage_pass',False)),
            raw_history_is_not_buy_approval=True)
        if t in observer.received:
            b,source,amount,col=observer.received[t]
            item.update(observed=True,source_label=source,history_rows=len(b),
                state='RAW_HISTORY_RECORDED_INDEPENDENT_OF_STAGE',
                raw_frame_csv_sha256=digest(b.to_csv(index=False).encode()),
                latest_raw_date=str(b.Date.iloc[-1]) if len(b) else None,
                source_response=deepcopy(observer.source_responses.get(t)),
                price_tail_state=by.get(t,{}).get('observation_status'))
            try:
                canonical=b[['Date','Open','High','Low','Close','Volume']].copy()
                for column in ['Open','High','Low','Close','Volume']:canonical[column]=canonical[column].astype(float)
                item['canonical_history_sha256']=digest(json.dumps(canonical.to_dict('records'),sort_keys=True,
                    separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
            except (ValueError,TypeError,OverflowError):
                item['canonical_history_sha256']=None
            # Retain the response even if the current price stage fails or its
            # bars are invalid. The consumer must audit it before using it.
            history.extend(dict(ticker=t,date=r.Date,open=r.Open,high=r.High,
                low=r.Low,close=r.Close,volume=r.Volume,source=source) for r in b.itertuples(index=False))
        else:
            item.update(state='REGISTERED_SOURCE_UNAVAILABLE',reason=observer.errors.get(t,'NOT_RETURNED_IN_SCANNED_UNIVERSE'))
        states.append(item)
    body=gzip.compress(csv_bytes(history,HISTORY_FIELDS),mtime=0)
    registry_bytes=(json.dumps(registry,ensure_ascii=False,indent=2)+'\n').encode()
    atomic(out/WATCH_HISTORY,body);atomic(out/WATCH_REGISTRY,registry_bytes)
    result=dict(schema='C3_REGISTERED_FOLLOWUP_CAPTURE_V1',capture_completed=True,asof=asof,
        requested_cutoff=observer.cutoff,run_context=observer.run_context,registry_id=registry['registry_id'],
        registered_count=len(states),observed_count=sum(s['observed'] for s in states),
        unavailable_count=sum(not s['observed'] for s in states),rows=states,history_rows=len(history),
        observed_reference_dates=list(calendar),reference_calendar_valid=calendar_ok,calendar_reference=calendar_source,
        original_reference_calendar_is_not_regular_scope_proof=True,regular_only_scope_verified=False,
        retained_even_if_price_stage_fails=True,actual_fills=0,approved_buy_count=0,orders_enabled=False,
        output_sha256={WATCH_HISTORY:digest(body),WATCH_REGISTRY:digest(registry_bytes)})
    atomic(out/WATCH_STATUS,(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
    return result

class PremoveObserver:
    def __init__(self,cutoff,captured_at_utc=None,run_context=None,registered_watch=None):
        self.cutoff=str(cutoff);self.received={};self.errors={}
        self.registered_watch=validate_registered_watch(registered_watch) if registered_watch is not None else None
        self.source_responses={}
        self.captured_at_utc=captured_at_utc or datetime.now(timezone.utc).isoformat()
        self.run_context=run_context or {k:os.environ.get(v) for k,v in [
            ('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT'),('commit','GITHUB_SHA')]}
    def observe(self,ticker,frame,source):
        if not re.fullmatch(r'\d{6}',str(ticker)):raise ValueError('SIX_DIGIT_TICKER_REQUIRED')
        if ticker in self.received or ticker in self.errors:raise ValueError('DUPLICATE_OBSERVATION')
        try:
            b=normalized(frame)
            # Preserve the reported field if present; never replace it with C*V.
            col='거래대금' if '거래대금' in frame else 'Turnover' if 'Turnover' in frame else None
            raw=frame[col].iloc[-1] if col and len(frame) else None
            try:
                amount=int(raw) if raw is not None and not isinstance(raw,bool) and pd.notna(raw) and float(raw)>=0 and float(raw).is_integer() else None
            except (ValueError,TypeError,OverflowError):amount=None
            self.received[ticker]=(b,str(source),amount,col)
            if self.registered_watch is not None:
                self.source_responses[ticker]=deepcopy(frame.attrs.get('c3_source_response'))
        except (ValueError,TypeError,OverflowError,KeyError) as ex:
            self.errors[ticker]=type(ex).__name__+':'+str(ex)
    def finish(self,outdir,reference_date,reference_calendar,calendar_source):
        out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
        rows=[];history=[];audits={};asof=str(reference_date)
        cal=list(reference_calendar)
        calendar_ok=bool(cal and cal==sorted(set(cal)) and cal[-1]==asof and asof<=self.cutoff)
        for ticker,(raw,source,amount,col) in sorted(self.received.items()):
            row=dict(ticker=ticker,asof=asof,observation_status='UNVERIFIED',track='PRICE_UNVERIFIED',
                price_stage_pass=False,source=source,annual_context_known=None,
                raw_reported_turnover_value=amount,raw_reported_turnover_column=col,
                turnover_scope_certified=False,company_health_verified=False,
                instrument_type_verified=False,buy_approved=False)
            row['normalized_frame_sha256']=digest(raw.to_csv(index=False).encode())
            try:
                if not calendar_ok:raise ValueError('COMPLETED_REFERENCE_CALENDAR_UNAVAILABLE')
                b,audit=valid_price_tail(raw,asof,cal);audits[ticker]=audit
                if b is None:raise ValueError('INSUFFICIENT_VALID_CONTIGUOUS_HISTORY')
                stage=classify_contextual(b,asof);m=stage['metrics'];floor=stage['floor']
                row.update(observation_status='PRICE_ONLY_OBSERVED',track=stage['track'],
                    price_stage_pass=stage['research_stage_pass'],close=m['Close'],retained_sessions=len(b),
                    annual_context_known=m['ret252'] is not None,
                    floor_date=floor['pivot_date'] if floor else None,
                    floor_confirmed_at=floor['confirmed_date'] if floor else None,
                    floor_low=floor['low'] if floor else None)
                for key in ['ret5','ret20','ret60','ret120','ret252','rsi14','slow_k','slow_d',
                    'rsi_change3','k_change3','above_ma20_atr','from_floor_atr','range10_previous20']:
                    row[key]=clean_number(m.get(key))
                if row['price_stage_pass']:
                    # Keep every accepted price-stage case, with its full valid
                    # prefix. There is no arbitrary top-N or legacy setup gate.
                    history.extend(dict(ticker=ticker,date=r.Date,open=r.Open,high=r.High,
                        low=r.Low,close=r.Close,volume=r.Volume,source=source) for r in b.itertuples(index=False))
            except (ValueError,TypeError,KeyError,IndexError) as ex:
                row.update(reason=type(ex).__name__+':'+str(ex))
            rows.append(row)
        for ticker,error in sorted(self.errors.items()):
            rows.append(dict(ticker=ticker,asof=asof,observation_status='SOURCE_INVALID',
                track='PRICE_UNVERIFIED',price_stage_pass=False,reason=error,buy_approved=False,
                company_health_verified=False,instrument_type_verified=False,turnover_scope_certified=False))
        body=csv_bytes(rows,FIELDS);hist=gzip.compress(csv_bytes(history,HISTORY_FIELDS),mtime=0)
        atomic(out/CSV_NAME,body);atomic(out/HISTORY_NAME,hist)
        result=dict(schema='C3_PREMOVE_OBSERVATION_HANDOFF_V1',observation_audit_completed=True,
            asof=asof,requested_cutoff=self.cutoff,captured_at_utc=self.captured_at_utc,run_context=self.run_context,
            stage_policy=STAGE_POLICY,mirrored_work_source_sha256=WORK_ORIGIN_SHA256,
            reference_calendar_available=calendar_ok,calendar_reference=calendar_source,
            official_holiday_calendar_certified=False,source_session_scope_certified=False,
            evaluated_ticker_count=len(self.received)+len(self.errors),
            observed_source_count=len(self.received),source_validation_error_count=len(self.errors),
            price_valid_count=sum(r['observation_status']=='PRICE_ONLY_OBSERVED' for r in rows),
            price_stage_case_count=sum(r['price_stage_pass'] for r in rows),
            track_counts=dict(Counter(r['track'] for r in rows)),history_rows=len(history),
            no_legacy_breakout_filter=True,all_stage_pass_histories_preserved=True,
            company_health_verified_count=0,approved_buy_count=0,orders_enabled=False,
            actual_source_turnover_field_count=sum(r.get('raw_reported_turnover_value') is not None for r in rows),
            actual_turnover_unit_and_regular_scope_certified_count=0,
            output_sha256={CSV_NAME:digest(body),HISTORY_NAME:digest(hist)},
            code_sha256={p.name:digest(p.read_bytes()) for p in [Path(__file__),Path(__file__).with_name('c3_premove_stage_v1.py')]},
            price_tail_audits=audits,profitability_proven=False,stops_created=False)
        atomic(out/STATUS_NAME,(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
        export_registered_watch(self,out,asof,cal,calendar_source,rows,calendar_ok)
        return result

def record_failure(outdir,cutoff,error):
    result=dict(schema='C3_PREMOVE_OBSERVATION_HANDOFF_V1',observation_audit_completed=False,
        asof=str(cutoff),error=type(error).__name__+':'+str(error),approved_buy_count=0,orders_enabled=False,
        stale_previous_outputs_not_accepted=True)
    atomic(Path(outdir)/STATUS_NAME,(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    return result

