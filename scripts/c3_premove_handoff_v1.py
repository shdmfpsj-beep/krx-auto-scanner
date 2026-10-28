"""Preserve pre-move observations independently of the legacy late-stage filter.

Price observations have no company-health, instrument-type or trade approval.
The completed reference ETF supplies a session grid, not regular-only proof.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import csv,gzip,hashlib,io,json,math,os,re
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

class PremoveObserver:
    def __init__(self,cutoff,captured_at_utc=None,run_context=None):
        self.cutoff=str(cutoff);self.received={};self.errors={}
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
        return result

def record_failure(outdir,cutoff,error):
    result=dict(schema='C3_PREMOVE_OBSERVATION_HANDOFF_V1',observation_audit_completed=False,
        asof=str(cutoff),error=type(error).__name__+':'+str(error),approved_buy_count=0,orders_enabled=False,
        stale_previous_outputs_not_accepted=True)
    atomic(Path(outdir)/STATUS_NAME,(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    return result
