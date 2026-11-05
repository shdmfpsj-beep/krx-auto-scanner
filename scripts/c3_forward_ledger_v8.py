"""Append-only research decisions and observations; never broker orders.

Original decisions, market receipts and observations are exclusive-create and
hash checked. Derived latest reports may be rebuilt. No retrospective decision
registration, no broker-fill claim, and no return inferred from absent prices.
"""
import gzip,hashlib,json,math,os,statistics
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path

from c3_daily_top2_v4 import BUY,SELL,SLIP
from c3_selection_factors_v6 import full_session_path
from c3_selection_scope_v5 import freeze_forward

KST=timezone(timedelta(hours=9));HORIZONS=(5,10,20)


def stamp(value):
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    return d


def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)
def hash_value(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def execution_version():
    root=Path(__file__).parent
    names=('c3_daily_top2_v4.py','c3_selection_factors_v6.py','c3_entry_benchmark_v1.py','c3_competition_v2.py')
    return hash_value({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names})


def immutable(path,payload):
    path=Path(path);record=dict(payload=payload,sha256=hash_value(payload))
    if path.exists():
        old=read_record(path)
        if canonical(old)!=canonical(payload):raise ValueError("IMMUTABLE_RECORD_CONFLICT:"+path.name)
        return False
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        body=(canonical(record)+"\n").encode()
        if 'lanes' in path.parts:
            from c3_supply_v11 import encrypt_bytes
            body=encrypt_bytes(body,os.environ.get('KRX_AUTH_KEY'))
        with path.open("xb") as f:f.write(body)
    except FileExistsError:
        if canonical(read_record(path))!=canonical(payload):raise ValueError("IMMUTABLE_RECORD_RACE")
        return False
    return True


def read_record(path):
    path=Path(path)
    body=path.read_bytes()
    if body.startswith(b'C3V11GCM1'):
        from c3_supply_v11 import open_sealed
        body=open_sealed(path,os.environ.get('KRX_AUTH_KEY',''))
    raw=gzip.decompress(body).decode() if path.suffix==".gz" else body.decode()
    r=json.loads(raw)
    if r["sha256"]!=hash_value(r["payload"]):raise ValueError("IMMUTABLE_RECORD_HASH_MISMATCH:"+path.name)
    return r["payload"]


def market_payload(prices,indices,sessions,meta):
    day=meta["asof"];rows={}
    if sessions!=sorted(set(sessions)) or day!=sessions[-1]:raise ValueError("SESSION_GRID_OR_ASOF_INVALID")
    if set(indices)!={"KOSPI","KOSDAQ"} or any(set(indices[m])!=set(sessions) for m in indices):raise ValueError("BENCHMARK_GRID_MISMATCH")
    if meta.get("price_basis")!="UNADJUSTED_AS_TRADED" or meta.get("source_scope") in ("MIXED","AFTERMARKET"):raise ValueError("PRICE_BASIS_OR_SCOPE_REJECTED")
    if not meta.get("authenticated"):
        from c3_market_supply_v11 import source_usable
        if meta.get('provider')!='C3_KRX_UNADJUSTED_SUPPLY_V12' or not source_usable(meta.get('supply_manifest',{})) or meta['supply_manifest'].get('asof')!=day:raise ValueError("UNAUTHENTICATED_MARKET_SNAPSHOT")
    for p in prices:
        t=p["ticker"]
        if t in rows:raise ValueError("DUPLICATE_SECURITY_BAR")
        if p["asof"]!=day or p["market"] not in indices:raise ValueError("BAR_DATE_OR_MARKET_MISMATCH")
        vals={k:float(p[k]) for k in ("open","high","low","close","volume","turnover_krw")}
        if not all(math.isfinite(v) for v in vals.values()):raise ValueError("NONFINITE_MARKET_VALUE")
        valid=0<vals["low"]<=min(vals["open"],vals["close"])<=max(vals["open"],vals["close"])<=vals["high"] and vals["volume"]>0 and vals["turnover_krw"]>0
        halt=vals["close"]>0 and vals["volume"]==0 and all(v>=0 for v in vals.values())
        rows[t]=dict(vals,name=p["name"],market=p["market"],date=day,tradable=valid,invalid_data=not(valid or halt),halt_like=halt,segment=0,action_boundary=bool(p.get("action_boundary",False)))
    if {p["market"] for p in rows.values()}!={"KOSPI","KOSDAQ"}:raise ValueError("INCOMPLETE_MARKET_COVERAGE")
    return dict(asof=day,rows=rows,indices=indices,sessions=sessions,source=meta)


def freeze_market(root,payload,now):
    source=payload["source"];local=stamp(now).astimezone(KST)
    if stamp(source["received_at"])>stamp(now):raise ValueError("FUTURE_SOURCE_RECEIPT")
    if payload["asof"]>local.date().isoformat() or (payload["asof"]==local.date().isoformat() and local.hour*60+local.minute<15*60+30):raise ValueError("MARKET_SESSION_NOT_COMPLETED")
    path=Path(root)/"markets"/(payload["asof"]+".json.gz")
    for p in sorted((Path(root)/"markets").glob("*.json.gz")):
        old=read_record(p)
        keys=('provider','price_basis','source_scope','authenticated','regular_only_certified')
        if any(old['source'].get(k)!=source.get(k) for k in keys):raise ValueError('MARKET_SOURCE_PROVIDER_OR_BASIS_CHANGED')
        if old["asof"]>=payload["asof"]:continue
        for market in old["indices"]:
            if any(payload["indices"][market].get(d)!=v for d,v in old["indices"][market].items()):raise ValueError("BENCHMARK_HISTORY_REVISED")
    if path.exists():
        old=read_record(path)
        # Retries may have a new retrieval receipt; retain the first receipt.
        content=lambda p:{k:p[k] for k in ("asof","rows","indices","sessions")}
        if hash_value(content(old))!=hash_value(content(payload)):
            if 'lanes' in Path(root).parts:
                correction(root,path,'SUPPLY_RECONCILIATION_DIFFERENCE',payload,now,source.get('source_run_id','UNKNOWN'))
            raise ValueError("MARKET_CORRECTION_REQUIRES_SEPARATE_RECORD")
        return old,False
    path.parent.mkdir(parents=True,exist_ok=True)
    record=dict(payload=payload,sha256=hash_value(payload))
    body=gzip.compress((canonical(record)+"\n").encode(),mtime=0)
    if 'lanes' in path.parts:
        from c3_supply_v11 import encrypt_bytes
        body=encrypt_bytes(body,os.environ.get('KRX_AUTH_KEY'))
    with path.open("xb") as f:f.write(body)
    return read_record(path),True


def register(root,batch,now):
    day=stamp(now).astimezone(KST).date().isoformat();price_day=batch['price_asof'];path=Path(root)/"decisions"/(price_day+".json")
    if batch["decision_date"]!=day:raise ValueError("CURRENT_SESSION_DECISION_REQUIRED")
    if price_day!=day:
        from c3_runtime_v9 import registration_window
        if batch.get('schema')!='C3_FORWARD_DECISION_V9' or not batch.get('allow_delayed_preopen'):raise ValueError('CURRENT_SESSION_DECISION_REQUIRED')
        if registration_window(price_day,stamp(now))!='DELAYED_BEFORE_NEXT_POSSIBLE_OPEN':raise ValueError('DELAYED_SOURCE_OUTSIDE_PROSPECTIVE_WINDOW')
    if path.exists():
        old=read_record(path)
        if old["schema"] not in ("C3_FORWARD_DECISION_V8","C3_FORWARD_DECISION_V9"):raise ValueError("DECISION_SCHEMA_CHANGED")
        substantive=lambda b:{m:[{k:r[k] for k in ("signal_id","ticker","rank","reference_close","entry_plans")} for r in rows] for m,rows in b["models"].items()}
        if substantive(old)!=substantive(batch):raise ValueError("DECISION_CORRECTION_REQUIRES_SEPARATE_RECORD")
        return old,False
    if batch.get("synthetic_source"):raise ValueError("SYNTHETIC_SOURCE_NOT_LIVE_DECISION")
    if batch.get("model_code_sha256") is None:raise ValueError("MODEL_CODE_HASH_REQUIRED")
    if stamp(batch["source_received_at"])>stamp(batch["known_at"]) or stamp(batch["known_at"])>stamp(now):raise ValueError("SOURCE_OR_KNOWLEDGE_IN_FUTURE")
    if any(r["registered_at"]!=now or r["decision_date"]!=day for rows in batch["models"].values() for r in rows):raise ValueError("SIGNAL_TIME_MISMATCH")
    if set(batch["models"])!={"A","B"}:raise ValueError("SELECTION_MODEL_SET_INVALID")
    for model,rows in batch["models"].items():
        if len(rows)>2 or len({r["ticker"] for r in rows})!=len(rows):raise ValueError("DUPLICATE_OR_TOO_MANY_SIGNALS")
        if any(r["signal_id"]!=signal_id(price_day,model,r["ticker"]) or r["rank"]!=i or r.get('source_price_asof',price_day)!=price_day for i,r in enumerate(rows,1)):raise ValueError("SIGNAL_ID_OR_RANK_INVALID")
    source=Path(root)/'markets'/(price_day+'.json.gz')
    if not source.exists():raise ValueError('DECISION_SOURCE_SNAPSHOT_REQUIRED')
    market=read_record(source)
    if batch['source_snapshot_hash']!=hash_value(market):raise ValueError('DECISION_SOURCE_SNAPSHOT_MISMATCH')
    for rows in batch['models'].values():
        for r in rows:
            b=market['rows'].get(r['ticker'])
            if not b or (r['reference_close'],r['name'],r['market'])!=(b['close'],b['name'],b['market']):raise ValueError('DECISION_REFERENCE_PRICE_OR_IDENTITY_MISMATCH')
    # Reuse the tested same-day / forward-start / next-open registration guard.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:freeze_forward(tmp,batch,now)
    payload=dict(batch,registered_at=now)
    immutable(path,payload);return payload,True


def correction(root,target,reason,proposed,now,run_id):
    base=Path(root).resolve();path=Path(target).resolve()
    if base not in path.parents or not reason.strip():raise ValueError("CORRECTION_TARGET_OR_REASON_INVALID")
    original=read_record(path);payload=dict(target=str(path.relative_to(base)),original_hash=hash_value(original),reason=reason,proposed=proposed,recorded_at=now,run_id=str(run_id),applied_to_original=False)
    output=base/"corrections"/(hash_value(payload)+".json");immutable(output,payload);return output


def signal_id(day,model,ticker):return "C3V8-"+hash_value([day,model,ticker])[:24]


def price_session(signal):return signal.get('source_price_asof',signal['decision_date'])


def rows_for(signal,markets,sessions):
    day=price_session(signal);ticker=signal["ticker"];prior=None;rows=[]
    for d in sessions:
        if d<day:continue
        p=markets.get(d);bar=p["rows"].get(ticker) if p else None
        if bar is None:continue
        bar=dict(bar)
        if bar["market"]!=signal["market"] or bar["name"]!=signal["name"]:bar["action_boundary"]=True
        if prior and prior["close"]>0 and bar["close"]>0 and abs(bar["close"]/prior["close"]-1)>.35:bar["action_boundary"]=True
        rows.append(bar);prior=bar
    return rows


def selection_observation(signal,rows,sessions,index,h):
    start=sessions.index(price_session(signal));out=dict(status="INCOMPLETE_WINDOW",horizon=h,price_move_pct=None,excess_pct=None)
    if start+h>=len(sessions):return out
    days=sessions[start:start+h+1];by={b["date"]:b for b in rows};bars=[by.get(d) for d in days]
    if any(b is None for b in bars):return dict(out,status="DATA_MISSING")
    if any(b["action_boundary"] for b in bars):return dict(out,status="CORPORATE_ACTION_OR_IDENTITY_UNRESOLVED")
    if any(b["invalid_data"] or not b["tradable"] for b in bars):return dict(out,status="HALT_OR_INVALID_PRICE")
    if any(d not in index for d in (days[0],days[-1])):return dict(out,status="BENCHMARK_MISSING")
    move=100*(bars[-1]["close"]/signal["reference_close"]-1);bench=100*(index[days[-1]]/index[days[0]]-1)
    return dict(out,status="COMPLETE",evaluation_date=days[-1],price_move_pct=move,benchmark_pct=bench,excess_pct=move-bench,
        rose=move>0,outperformed=move>bench,regime=signal["market_regime"],source_regular_only_certified=signal["source_regular_only_certified"])


def paper_observation(signal,variant,rows,sessions,h):
    item=signal["entry_plans"][variant];plan=item["plan"]
    if plan is None:return dict(status="NO_SIGNAL",reason=item["reason"],model_entry=False,net_pct=None)
    path=full_session_path(plan,rows,sessions,h);entry=path["entry"];exit=path["exit"]
    out=dict(status=entry["status"],model_entry=entry["status"]=="MODEL_ENTRY",entry=entry,exit=exit,
        realized_net_pct=exit["net_pct"] if exit else None,net_pct=None,actual_broker_fill=False,observations=path["observations"],
        censor_date=path["censor_date"],entry_day_order_uncertain=entry.get("order_unknown",False))
    if not out["model_entry"]:return out
    if path["censor_date"]:out["status"]="DATA_MISSING_OR_ACTION_CENSORED"
    elif path["maturity_date"] is None:out["status"]="OBSERVATION_WINDOW_INCOMPLETE"
    elif exit is None:out["status"]="EXIT_NEXT_TRADABLE_OPEN_PENDING"
    else:out.update(status="COMPLETE",net_pct=exit["net_pct"])
    return out


def advance(root,now,run_id):
    root=Path(root);markets={}
    for p in sorted((root/"markets").glob("*.json.gz")):
        value=read_record(p)
        if stamp(value["source"]["received_at"])>stamp(now):raise ValueError("FUTURE_MARKET_RECEIPT")
        markets[value["asof"]]=value
    decisions=[read_record(p) for p in sorted((root/"decisions").glob("*.json"))]
    if not markets:return [],dict(registered_decision_days=len(decisions),registered_signals=sum(len(rows) for b in decisions for rows in b["models"].values()),new_completed={str(h):0 for h in HORIZONS},selection={},paper={},current_action="CASH")
    latest=markets[max(markets)];sessions=latest["sessions"];indices=latest["indices"];out=[];clock={};entry_clock=set()
    for batch in decisions:
        if stamp(batch["registered_at"])>stamp(now):raise ValueError("FUTURE_DECISION_RECORD")
        if batch['execution_version']!=execution_version():raise ValueError('FROZEN_EXECUTION_ENGINE_CHANGED_RECONCILIATION_REQUIRED')
        if batch["price_asof"] not in markets or batch["source_snapshot_hash"]!=hash_value(markets[batch["price_asof"]]):raise ValueError("DECISION_SOURCE_SNAPSHOT_MISMATCH")
        for model,signals in batch["models"].items():
            for s in signals:
                anchor=price_session(s);idx=sessions.index(anchor);key=(model,s["ticker"]);overlap=idx<clock.get(key,-1)
                if not overlap:clock[key]=idx+20
                rows=rows_for(s,markets,sessions);paper={};aliases={}
                for variant,item in s["entry_plans"].items():
                    plan=item["plan"];trade_key=(model,s["ticker"],variant,plan["signal_key"]) if plan else None
                    aliases[variant]=trade_key in entry_clock if trade_key else False
                    observations={str(h):paper_observation(s,variant,rows,sessions,h) for h in HORIZONS};paper[variant]=observations
                    if trade_key and any(x["model_entry"] for x in observations.values()):entry_clock.add(trade_key)
                row=dict(signal_id=s["signal_id"],ticker=s["ticker"],name=s["name"],model=model,decision_date=s["decision_date"],source_price_asof=anchor,asof=latest["asof"],
                    overlap_with_prior_20_sessions=overlap,duplicate_entry_structure=aliases,selection={str(h):selection_observation(s,rows,sessions,indices[s["market"]],h) for h in HORIZONS},paper=paper)
                sources={d:hash_value(m) for d,m in markets.items() if d>=anchor}
                row.update(market_sources_sha256=sources,source_knowledge_at=max((m["source"]["received_at"] for d,m in markets.items() if d>=anchor),key=stamp))
                # Exclude changing execution receipt/run ID from deterministic observations.
                # Late outcome data appends a new knowledge version; neither the
                # original decision nor an earlier incomplete observation changes.
                immutable(root/"observations"/latest["asof"]/(s["signal_id"]+"-"+hash_value(sources)[:12]+".json"),row);out.append(row)
    summary=dict(registered_decision_days=len({b['decision_date'] for b in decisions}),registered_source_sessions=len(decisions),registered_signals=len(out),unique_registered_tickers=len({r["ticker"] for r in out}),latest_observed_session=latest["asof"],
        selection={},paper={},overlapping_selection_records=sum(r["overlap_with_prior_20_sessions"] for r in out),actual_broker_fills=0,orders_enabled=False,current_action="CASH",not_a_capital_constrained_portfolio=True)
    avg=lambda v:statistics.mean(v) if v else None
    for model in ("A","B"):
        rr=[r for r in out if r["model"]==model];summary["selection"][model]={};summary["paper"][model]={}
        for h in HORIZONS:
            completed=[r["selection"][str(h)] for r in rr if not r["overlap_with_prior_20_sessions"] and r["selection"][str(h)]["status"]=="COMPLETE"]
            summary["selection"][model][str(h)]=dict(total_records=len(rr),completed_nonoverlap=len(completed),incomplete_or_excluded=len(rr)-len(completed),
                mean_move_pct=avg([r["price_move_pct"] for r in completed]),mean_excess_pct=avg([r["excess_pct"] for r in completed]),rise_rate_pct=avg([100*r["rose"] for r in completed]),
                regimes={reg:dict(n=len(xs:=[r for r in completed if r["regime"]==reg]),mean_excess_pct=avg([r["excess_pct"] for r in xs])) for reg in ("UP","SIDEWAYS","DOWN")})
        variants=sorted({v for r in rr for v in r["paper"]})
        for variant in variants:
            summary["paper"][model][variant]={}
            for h in HORIZONS:
                eligible=[r for r in rr if not r["duplicate_entry_structure"].get(variant,False) and not r["overlap_with_prior_20_sessions"]]
                pp=[r["paper"][variant][str(h)] for r in eligible];complete=[p for p in pp if p["status"]=="COMPLETE"]
                labels=Counter()
                for r in eligible:
                    selected=r["selection"][str(h)];p=r["paper"][variant][str(h)]
                    if selected["status"]!="COMPLETE":label="SELECTION_NOT_YET_EVALUABLE"
                    elif selected["excess_pct"]<=0:label="SELECTION_FAILED_TO_OUTPERFORM"
                    elif not p["model_entry"]:label="SELECTED_OUTPERFORMER_NOT_ENTERED"
                    elif p["net_pct"] is None:label="SELECTED_OUTPERFORMER_TRADE_PENDING"
                    elif p["net_pct"]<=0:label="SELECTED_OUTPERFORMER_ENTRY_OR_EXIT_LOST"
                    else:label="SELECTED_OUTPERFORMER_AND_MODEL_PROFIT"
                    labels[label]+=1
                summary["paper"][model][variant][str(h)]=dict(status_counts=dict(Counter(p["status"] for p in pp)),completed=len(complete),
                    mean_net_pct=avg([p["net_pct"] for p in complete]),stop_exit_count=sum(p.get("exit") is not None and "STOP" in p["exit"]["reason"] for p in pp),attribution=dict(labels))
    return out,summary
