#!/usr/bin/env python3
"""Frozen C3 price-only watch and D+1/D+2 observation state machine.

Never authorizes a trade, infers a broker fill or certifies regular-only data.
Source is the original immutable completed October 30 KRX scan artifact.
"""
import argparse,csv,hashlib,io,json,math
from collections import Counter
from pathlib import Path
import pandas as pd
from c3_corridor_replay_v1 import read_bundle,load_and_audit,sha,analyze,FIELDS

SCHEMA='C3_PROSPECTIVE_PRICE_WATCH_V2_NO_ORDERS'
CHECKSUM_FIELDS=('schema','asof','source_run_id','source_stage_sha256',
                 'source_history_sha256','source_rank_sha256','cohort_origin',
                 'frozen_signals','source_regular_only_verified',
                 'trade_approved','orders_enabled')

def canonical_sha(o):
    return hashlib.sha256(json.dumps(o,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()

def prepare_freeze(source,replay_csv,replay_status):
    raw=read_bundle(source)
    asof,stage,registered,obs,hist,names=load_and_audit(raw)
    if stage.get('source_session_scope_certified') or registered.get('regular_only_scope_verified'):
        raise ValueError('UNEXPECTED_CERTIFIED_SCOPE_NEEDS_INDEPENDENT_REVIEW')
    meta=json.loads(Path(replay_status).read_text(encoding='utf-8'))
    path=Path(replay_csv)
    if sha(path.read_bytes())!=meta['csv_sha256']:
        raise ValueError('RANKED_REPLAY_CSV_DIGEST_MISMATCH')
    if str(meta['source_run_id'])!=str(stage['run_context']['run_id']) or meta['asof']!=asof:
        raise ValueError('REPLAY_SOURCE_RUN_OR_ASOF_MISMATCH')
    # An attacker can change a CSV *and* its reported hash. Re-derive from the
    # original source OHLCV prefix and compare bytes, not metadata alone.
    derived,_=analyze(asof,stage,registered,obs,hist,names)
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf,fieldnames=FIELDS)
    writer.writeheader();writer.writerows(derived)
    if sha(buf.getvalue().encode('utf-8-sig'))!=meta['csv_sha256']:
        raise ValueError('REPLAY_NOT_DERIVED_FROM_FROZEN_SOURCE')
    frame=pd.read_csv(path,dtype={'ticker':str}).fillna('')
    if len(frame)!=stage['price_stage_case_count'] or frame.ticker.duplicated().any():
        raise ValueError('REPLAY_COHORT_COUNT_OR_TICKER_INVALID')
    rows=[]
    for x in frame.itertuples(index=False):
        if not (x.registered_cohort in (True,'True','true') and
                x.research_stage=='GEOMETRY_NEAR_CLOSE_WATCH'):continue
        if not (x.primary_retest_low and x.primary_retest_high and
                x.model_stop and x.support and x.atr14 and x.nearest_pivot_high):
            continue
        r=dict(ticker=x.ticker,name=x.name,asof=asof,
          cohort_registered_prior_day=True,
          close=float(x.observed_close),atr14=float(x.atr14),
          support=float(x.support),support_confirmed_at=x.support_confirmed_at,
          stop=int(x.model_stop),first_resistance=float(x.nearest_pivot_high),
          watch_low=int(float(x.primary_retest_low)),
          watch_high=int(float(x.primary_retest_high)),
          conditional_strength_low=int(float(x.continuation_low)) if x.continuation_low else None,
          conditional_strength_high=int(float(x.continuation_high)) if x.continuation_high else None,
          geometry_score_not_final80=float(x.research_score_not_final80),
          security_type_verified=False,actual_turnover_verified=False,
          foreign_institution_flow_verified=False,regular_only_verified=False,
          buy_approved=False,orders_enabled=False)
        if not (0<r['stop']<r['support']<=r['close']<r['first_resistance']
          and r['stop']<r['watch_low']<=r['watch_high']<=r['close']):
            raise ValueError('UNTRUSTWORTHY_REPLAY_PRICE_GEOMETRY_'+x.ticker)
        r['signal_id']=canonical_sha(r)
        rows.append(r)
    rows.sort(key=lambda x:(-x['geometry_score_not_final80'],x['ticker']))
    if len(rows)!=meta['registered_near_close_watch_count']:
        raise ValueError('REGISTERED_NEAR_LANE_COUNT_MISMATCH')
    frozen=dict(schema=SCHEMA,asof=asof,
      source_run_id=str(stage['run_context']['run_id']),
      source_stage_sha256=stage['output_sha256']['c3_premove_observations_v1.csv'],
      source_history_sha256=stage['output_sha256']['c3_premove_history_v1.csv.gz'],
      source_rank_sha256=meta['csv_sha256'],
      cohort_origin='PRE_REGISTERED_2026_10_29_36_STOCKS_ONLY',
      frozen_signals=rows,source_regular_only_verified=False,
      trade_approved=False,orders_enabled=False)
    frozen['freeze_sha256']=canonical_sha({k:frozen[k] for k in CHECKSUM_FIELDS})
    return frozen

def validate_freeze(frozen):
    if (frozen.get('schema')!=SCHEMA or frozen.get('trade_approved') is not False
        or frozen.get('orders_enabled') is not False):
        raise ValueError('FROZEN_RESEARCH_ONLY_GUARDS_MISSING')
    if frozen.get('freeze_sha256')!=canonical_sha({k:frozen[k] for k in CHECKSUM_FIELDS}):
        raise ValueError('FREEZE_SHA256_MISMATCH')
    signals=frozen['frozen_signals']
    if not signals or len(signals)!=len({x['ticker'] for x in signals}):
        raise ValueError('INVALID_FROZEN_SIGNAL_COHORT')
    for x in signals:
        y={k:v for k,v in x.items() if k!='signal_id'}
        if x.get('signal_id')!=canonical_sha(y):
            raise ValueError('SIGNAL_SHA256_MISMATCH')
        if x['asof']!=frozen['asof'] or x['buy_approved'] is not False:
            raise ValueError('FROZEN_SIGNAL_METADATA_INVALID')
    return signals

def valid_bar(b):
    if not isinstance(b,dict):return False
    try:
        o,h,l,c,v=(float(b[k]) for k in ('open','high','low','close','volume'))
        return all(math.isfinite(x) for x in (o,h,l,c,v)) and (0<l<=min(o,c)<=max(o,c)<=h and v>=0)
    except (KeyError,TypeError,ValueError):return False

def recovery_state(s,d1):
    """D+1 *completed* daily candle; no same-day entry allowed."""
    if d1 is None:return 'PENDING_NEXT_OBSERVED_SESSION'
    if not valid_bar(d1):return 'INVALID_NEW_SOURCE_BAR'
    if d1['date']<=s['asof']:return 'NON_FUTURE_OBSERVATION_REJECTED'
    o,h,l,c=(float(d1[k]) for k in ('open','high','low','close'))
    stop,support,atr=(s[k] for k in ('stop','support','atr14'))
    if l<=stop or o<=stop:return 'STRUCTURE_STOP_TOUCHED_REJECT'
    if o<s['watch_low']:return 'GAP_BELOW_WATCH_CANCEL'
    if o>s['close']+min(.5*atr,.035*s['close']):return 'GAP_UP_NO_CHASE'
    if l>s['watch_high'] or h<s['watch_low']:return 'ZONE_NOT_TOUCHED'
    span=h-l
    if span<=0:return 'ZERO_RANGE_NO_CONFIRMATION'
    if not (c>max(o,support,stop,s['close']) and c>=l+.65*span):
        return 'CONTACT_WITHOUT_STRONG_CLOSE'
    return 'STRONG_CLOSE_CONFIRMED_WATCH_D2'

def next_open_state(s,d1,d2):
    state=recovery_state(s,d1)
    base=dict(ticker=s['ticker'],name=s['name'],signal_id=s['signal_id'],
      asof=s['asof'],observed_session_1=d1.get('date') if d1 else None,
      observed_session_2=d2.get('date') if d2 else None,
      d1_state=state,d2_state='D2_NOT_ELIGIBLE',
      hypothetical_entry=None,hypothetical_first_resistance_net_R=None,
      broker_fill=False,profit_realized=None,buy_approved=False,orders_enabled=False)
    if state!='STRONG_CLOSE_CONFIRMED_WATCH_D2':return base
    if d2 is None:return dict(base,d2_state='PENDING_D2_OBSERVED_SESSION')
    if not valid_bar(d2) or d2['date']<=d1['date']:
        return dict(base,d2_state='INVALID_D2_PRICE_OR_DATE')
    price=float(d2['open']);atr=s['atr14'];last=float(d1['close'])
    if price<=s['stop']:return dict(base,d2_state='OPEN_AT_OR_BELOW_STOP')
    if price>last+.35*atr or price<last-.30*atr:
        return dict(base,d2_state='D2_GAP_TOO_LARGE_NO_CHASE')
    risk=(price-s['stop'])/price
    r=(s['first_resistance']-price*(1+.0065))/(price-s['stop']+price*.0065)
    if risk>.08 or risk<=0 or r<2:
        return dict(base,d2_state='D2_RISK_OR_NET_2R_FAILED')
    return dict(base,d2_state='D2_OPEN_PRICE_ELIGIBLE_PAPER_ONLY',
      hypothetical_entry=price,hypothetical_first_resistance_net_R=round(r,3))

def update(frozen,d1_bars=None,d2_bars=None,session_order=None,
           regular_only_verified=False):
    signals=validate_freeze(frozen)
    d1_bars=d1_bars or {};d2_bars=d2_bars or {}
    if session_order is not None:
        if (len(session_order)!=len(set(session_order))
            or session_order!=sorted(session_order)):
            raise ValueError('SESSION_ORDER_INVALID')
        if frozen['asof'] not in session_order:
            raise ValueError('FROZEN_ASOF_NOT_IN_CALENDAR')
        ix=session_order.index(frozen['asof'])
        d1date=session_order[ix+1] if ix+1<len(session_order) else None
        d2date=session_order[ix+2] if ix+2<len(session_order) else None
    else:d1date=d2date=None
    out=[]
    for s in signals:
        b1=d1_bars.get(s['ticker']);b2=d2_bars.get(s['ticker'])
        if b1 and (d1date is None or b1.get('date')!=d1date):
            raise ValueError('D1_DATE_NOT_NEXT_OBSERVED_SESSION_'+s['ticker'])
        if b2 and (d2date is None or b2.get('date')!=d2date):
            raise ValueError('D2_DATE_NOT_SECOND_OBSERVED_SESSION_'+s['ticker'])
        out.append(next_open_state(s,b1,b2))
    return dict(schema='C3_PROSPECTIVE_PRICE_STATE_V2_NO_ORDERS',
      frozen_asof=frozen['asof'],freeze_sha256=frozen['freeze_sha256'],
      input_regular_only_verified=bool(regular_only_verified),
      source_regular_only_certified=False,
      tested=len(out),states=dict(Counter(x['d1_state'] for x in out)),
      d2_states=dict(Counter(x['d2_state'] for x in out)),cases=out,
      broker_fills=0,realized_returns_proven=False,
      trade_approved=False,orders_enabled=False)

def run(input_bundle,replay_csv,replay_status,output):
    frozen=prepare_freeze(input_bundle,replay_csv,replay_status)
    dest=Path(output);dest.mkdir(parents=True,exist_ok=True)
    (dest/'c3_forward_watch_v2_frozen.json').write_text(
      json.dumps(frozen,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    state=update(frozen)
    (dest/'c3_forward_watch_v2_pending.json').write_text(
      json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return frozen,state

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--replay-csv',required=True)
    p.add_argument('--replay-status',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    frozen,state=run(a.input,a.replay_csv,a.replay_status,a.output)
    print(json.dumps(dict(frozen=frozen['asof'],frozen_signals=len(frozen['frozen_signals']),
      freeze_sha256=frozen['freeze_sha256'],current_states=state['states'],
      trade_approved=False,orders_enabled=False),ensure_ascii=False,indent=2))
