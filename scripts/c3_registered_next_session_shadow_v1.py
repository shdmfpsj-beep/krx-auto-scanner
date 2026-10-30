#!/usr/bin/env python3
"""D+1 forward price-contact audit of an already registered C3 watch cohort.

Exact D-day prefix is reconstructed BEFORE observing D+1. Contact != fill;
D+1 recovery is a signal that can only be acted on no earlier than D+2.
Research only; regular-session provenance and broker executions are unknown.
"""
import argparse,csv,gzip,hashlib,io,json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import pandas as pd
from c3_corridor_replay_v1 import observed_unbroken_pivot_high,atr_14,sha
from c3_entry_corridor_v1 import build_corridors
from practical_entry_quotes_v619 import krx_round,completed_retest_signal

SCHEMA='C3_REGISTERED_DPLUS1_SHADOW_V1_RESEARCH_ONLY'
FILES=['c3_registered_reclaim_registry_v1.json','c3_registered_followup_status_v1.json','c3_registered_followup_history_v1.csv.gz']
def source(path):
    p=Path(path)
    if p.is_dir():return {n:(p/n).read_bytes() for n in FILES}
    with ZipFile(p) as z:return {n:z.read(n) for n in FILES}
def confirmed_floor(b):
    n=len(b)
    for i in range(n-3,max(1,n-16)-1,-1):
        w=b.low.iloc[i-2:i+3];lo=float(b.low.iloc[i])
        if len(w)==5 and lo==float(w.min()) and (w>lo).any() and float(b.low.iloc[i+1:].min())>=lo:
            return lo,str(b.date.iloc[i]),str(b.date.iloc[i+2])
    return None

def run(inp,outdir):
    raw=source(inp);reg=json.loads(raw[FILES[0]]);meta=json.loads(raw[FILES[1]])
    baseline=reg['baseline_price_asof'];nextday=meta['asof'];calendar=meta['observed_reference_dates']
    if not meta['capture_completed'] or meta['registered_count']!=len(reg['setups']) or meta['registry_id']!=reg['registry_id']:
        raise ValueError('REGISTERED_WATCH_ID_MISMATCH')
    if sha(raw[FILES[2]])!=meta['output_sha256'][FILES[2]]:
        raise ValueError('FOLLOWUP_HISTORY_SHA256_MISMATCH')
    if baseline>=nextday or baseline not in calendar or nextday not in calendar or calendar[calendar.index(baseline)+1]!=nextday:
        raise ValueError('NEXT_OBSERVED_SESSION_NOT_DPLUS1')
    frame=pd.read_csv(io.BytesIO(gzip.decompress(raw[FILES[2]])),dtype={'ticker':str})
    names={r['ticker']:r['name'] for r in reg['setups']}
    if frame.ticker.nunique()!=len(names) or len(frame)!=meta['history_rows']:
        raise ValueError('REGISTERED_HISTORY_INCOMPLETE')
    rows=[]
    for ticker in sorted(names):
        b=frame[frame.ticker==ticker].sort_values('date').reset_index(drop=True)
        d=b[b.date==nextday]
        if len(d)!=1 or b.date.iloc[-1]!=nextday or b.date.duplicated().any():
            raise ValueError('NEXT_SESSION_OBSERVATION_INVALID_'+ticker)
        last=d.iloc[0];prior=b[b.date<=baseline].reset_index(drop=True)
        row=dict(ticker=ticker,name=names[ticker],signal_date=baseline,outcome_date=nextday,
                 contact_state=None,recovery_confirmed_after_close=False,
                 earliest_theoretical_followup='AFTER_OUTCOME_CLOSE',actual_fill=False,
                 realized_profit=None,trade_approved=False,orders_enabled=False)
        floor=confirmed_floor(prior) if len(prior)>=120 else None
        if floor is None:row['contact_state']='NO_PRIOR_CONFIRMED_FLOOR'
        else:
            close=float(prior.close.iloc[-1]);atr=atr_14(prior)
            overhead,hi_date,hi_confirmed=observed_unbroken_pivot_high(prior,close,baseline)
            if overhead is None:row['contact_state']='NO_PRIOR_OVERHEAD'
            else:
                stop=krx_round(floor[0]-.15*atr,'down')
                plan=build_corridors(asof=baseline,close=close,atr14=atr,confirmed_support=floor[0],
                    structural_stop=stop,verified_first_resistance=overhead,support_confirmed_at=floor[2],
                    resistance_source='CONFIRMED_PIVOT_PRE_OUTCOME',regular_only_certified=False)
                quote=next((x for x in plan.get('corridors',[]) if x['mode']=='SUPPORT_RETEST' and x['tier']=='PRIMARY_UP_TO_5PCT'),None)
                if quote is None:row['contact_state']='NO_PRIOR_PRIMARY_CORRIDOR'
                else:
                    low,high=quote['low_krw'],quote['high_krw']
                    row.update(baseline_close=close,model_stop=stop,watch_low=low,watch_high=high,
                               next_open=float(last.open),next_low=float(last.low),next_high=float(last.high),next_close=float(last.close))
                    if last.open<=stop:row['contact_state']='OPEN_BELOW_STOP_CANCEL'
                    elif last.open<low:row['contact_state']='OPEN_GAP_THROUGH_CANCEL'
                    elif last.open>close+min(.5*atr,.035*close):row['contact_state']='OPEN_CHASE_CANCEL'
                    elif last.low<=high and last.high>=low:
                        row['contact_state']='TOUCHED_STOP_AMBIGUOUS' if last.low<=stop else 'WATCH_ZONE_PRICE_CONTACT'
                        if row['contact_state']=='WATCH_ZONE_PRICE_CONTACT':
                            row['recovery_confirmed_after_close']=completed_retest_signal(
                                float(last.open),float(last.high),float(last.low),float(last.close),floor[0],atr,stop)
                    else:row['contact_state']='NO_PRICE_CONTACT'
        rows.append(row)
    counts=dict(Counter(x['contact_state'] for x in rows))
    touched=sum(x['contact_state'] in ('WATCH_ZONE_PRICE_CONTACT','TOUCHED_STOP_AMBIGUOUS') for x in rows)
    recovery=sum(x['recovery_confirmed_after_close'] for x in rows)
    result=dict(schema=SCHEMA,baseline=baseline,next_observed_session=nextday,
        source_run_id=meta['run_context']['run_id'],registered_count=len(names),
        tested=len(rows),contact_state_counts=counts,zone_contacts_including_stop_ambiguity=touched,
        stop_ambiguous=counts.get('TOUCHED_STOP_AMBIGUOUS',0),
        completed_recovery_signals=recovery,broker_fills=0,realized_returns_available=False,
        regular_only_scope_certified=False,trade_approved=False,orders_enabled=False,
        next_session_prices_never_used_to_set_entry=True)
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    cols=sorted(set().union(*(r.keys() for r in rows)))
    with (out/'c3_registered_dplus1_shadow_v1.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
    (out/'c3_registered_dplus1_shadow_v1_status.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    x=p.parse_args();print(json.dumps(run(x.input,x.output),ensure_ascii=False,indent=2))
