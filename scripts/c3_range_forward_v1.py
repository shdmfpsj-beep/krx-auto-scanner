"""Separate, immutable research observations and append-only dated outcomes.

No import of original ledger writer, trade order or Telegram client. A replay
is explicitly refused as a new forward observation. Atomic exclusive writes
are idempotent and reject changing an existing decision or stop.
"""
import hashlib,json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path

def canonical(obj):return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def hash_value(obj):return hashlib.sha256(canonical(obj)).hexdigest()

def immutable(path,doc):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);body=canonical(doc)+b'\n'
    try:
        # Hard-link a complete fsynced temp file. Another writer sees either
        # the whole immutable object or no object, never a partial JSON body.
        import tempfile
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
            temp=Path(f.name);f.write(body);f.flush();os.fsync(f.fileno())
        try:os.link(temp,path);return 'CREATED'
        except FileExistsError:
            if path.read_bytes()!=body:raise ValueError('IMMUTABLE_RESEARCH_RECORD_CONFLICT')
            return 'ALREADY_RECORDED'
        finally:temp.unlink(missing_ok=True)
    except Exception:raise

def register(root,record,clock,replay=False):
    if replay:return dict(status='REPLAY_NOT_REGISTERED_AS_FORWARD',writes=0)
    from c3_morning_source_v1 import prior_session
    if record['source_date']!=prior_session(clock)['requested_day']:raise ValueError('STALE_OR_NONCOMPLETED_FORWARD_SOURCE')
    stamp=datetime.fromisoformat(record['created_at'].replace('Z','+00:00'))
    received=datetime.fromisoformat(record['source_received_at'].replace('Z','+00:00'))
    closed=datetime.fromisoformat(record['source_date']+'T15:30:00+09:00')
    if stamp.tzinfo is None or received.tzinfo is None or not closed<=received<=stamp<=clock or clock-stamp>timedelta(hours=24):raise ValueError('INVALID_FORWARD_AVAILABILITY_TIME')
    for key in ('source_run_id','source_hash','model_version','ticker','reasons','market_regime','range','stop','r1','r2'):
        if key not in record:raise ValueError('FORWARD_PROVENANCE_FIELD_MISSING:'+key)
    # Stable identity independent of mutated stop/range: a changed model run
    # cannot silently create another observation for the same date/ticker.
    import re
    if not re.fullmatch('[A-Z0-9]{6}',record['ticker']) or not re.fullmatch('[A-Z0-9_]+',record['model_version']):raise ValueError('INVALID_RESEARCH_IDENTITY')
    key=record['model_version']+'/'+record['source_date']+'/'+record['ticker']
    digest=hash_value(record);result=immutable(Path(root)/'observations'/(key+'.json'),dict(record=record,sha256=digest))
    return dict(status=result,key=key,sha256=digest)

def observe(record,bars,index,sessions,asof):
    """Selection-close returns/excess, plus independent reference-price outcomes.

    Price bars crossing an action/halt/gap boundary cannot yield a result.
    Intraday execution remains a conservative daily-bar model, not a fill.
    """
    from c3_dynamic_entry_v2 import evaluate_trade
    from c3_single_entry_range_v1 import single_scenario
    day=record['source_date'];by={b['date']:b for b in bars};start=sessions.index(day);out={}
    p=record.get('plan');bi=next((i for i,b in enumerate(bars) if b['date']==day),None)
    for horizon in (5,10,20):
        if start+horizon>=len(sessions) or sessions[start+horizon]>asof:
            out[str(horizon)]=dict(status='PENDING_FUTURE_SESSIONS',selection_return_pct=None);continue
        dates=sessions[start:start+horizon+1];path=[by.get(d) for d in dates]
        if not path[0] or any(not b or not b.get('tradable',True) or b.get('action_boundary') or b['segment']!=path[0]['segment'] for b in path):
            out[str(horizon)]=dict(status='UNVERIFIED_MISSING_HALT_OR_ACTION_BOUNDARY');continue
        end=dates[-1];ret=100*(path[-1]['close']/path[0]['close']-1)
        benchmark=100*(index[end]/index[day]-1) if day in index and end in index else None
        out[str(horizon)]=dict(status='OBSERVED_PRICE_ONLY',selection_return_pct=ret,benchmark_return_pct=benchmark,
            excess_pct=ret-benchmark if benchmark is not None else None,daily_execution_confirmed=False,
            price_choices={choice:{str(v):evaluate_trade(single_scenario(p,choice),bars,bi,sessions,v,horizon,asof)
                for v in (1,2,3)} for choice in ('upper','middle','lower')} if p else {})
    return dict(source_date=day,ticker=record['ticker'],asof=asof,horizons=out,
        observation_hash=hash_value(record),original_signal_modified=False,actual_fill_claimed=False)

def append_outcome(root,record,outcome):
    key=record['model_version']+'/'+record['source_date']+'/'+record['ticker']+'/'+outcome['asof']
    return immutable(Path(root)/'outcomes'/(key+'.json'),outcome)

def update_existing(root,bars_by_ticker,index_by_ticker,sessions,asof):
    """Daily callable: never rewrites an observation, only new dated outcomes.

    Persistence and scheduler wiring must be supplied by the approved caller;
    this research utility never modifies a production ledger or workflow.
    """
    results=[]
    for path in sorted((Path(root)/'observations').glob('*/*/*.json')):
        saved=json.loads(path.read_text());record=saved['record']
        if saved.get('sha256')!=hash_value(record):raise ValueError('FORWARD_OBSERVATION_HASH_MISMATCH')
        t=record['ticker']
        if t not in bars_by_ticker or t not in index_by_ticker:
            results.append(dict(ticker=t,status='UNAVAILABLE_PRICE_OR_BENCHMARK'));continue
        outcome=observe(record,bars_by_ticker[t],index_by_ticker[t],sessions,asof)
        results.append(dict(ticker=t,status=append_outcome(root,record,outcome),horizons=outcome['horizons']))
    return dict(asof=asof,observations=len(results),results=results,original_records_modified=False)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--records',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--asof',required=True);a=p.parse_args();doc=json.loads(a.inputs.read_text())
    print(json.dumps(update_existing(a.records,doc['bars_by_ticker'],doc['index_by_ticker'],doc['sessions'],a.asof),ensure_ascii=False))
