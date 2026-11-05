"""Connect existing official collection, A/B selection and immutable shadow paths.

The CLI uses the real clock, never an override. Old decisions are not backfilled.
The optional index request reads public index data only; no model API or orders.
"""
import argparse,ast,csv,gzip,hashlib,json,math,statistics,urllib.request
from collections import Counter,defaultdict,deque
from datetime import datetime,timezone,timedelta
from pathlib import Path

from c3_current_candidates_v7 import fresh_snapshot
from c3_selection_scope_v5 import load_sources,classify,selection_features,digest,read_csv
from c3_selection_factors_v6 import load_indices,causal_factors,regime
from c3_entry_practical_v7 import ENTRIES,entry_plan,features
from c3_daily_top2_v4 import structure,atr14
from c3_forward_ledger_v8 import KST,stamp,hash_value,market_payload,freeze_market,register,read_record,signal_id,advance,execution_version,BUY,SELL,SLIP


def collect_indices(outdir,end,fetch=None):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);meta=dict(series={})
    for market in ("KOSPI","KOSDAQ"):
        url=f"https://api.finance.naver.com/siseJson.naver?symbol={market}&requestType=1&startTime=20250502&endTime={end.replace('-','')}&timeframe=day"
        if fetch is None:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 C3-ReadOnly-Research"})
            with urllib.request.urlopen(req,timeout=20) as f:body=f.read(1_500_000)
        else:body=fetch(url)
        received=datetime.now(timezone.utc).isoformat();values=ast.literal_eval(body.decode().strip());rows=[]
        for r in values[1:]:
            day=str(r[0]).strip();day=day[:4]+"-"+day[4:6]+"-"+day[6:8]
            if day>end:raise ValueError("FUTURE_INDEX_BAR")
            rows.append(dict(date=day,market=market,open=float(r[1]),high=float(r[2]),low=float(r[3]),close=float(r[4])))
        if not rows or [r["date"] for r in rows]!=sorted(set(r["date"] for r in rows)):raise ValueError("INDEX_DATE_ORDER_INVALID")
        path=root/(market+"_index.csv")
        with path.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
        (root/(market+"_raw.txt")).write_bytes(body)
        meta["series"][market]=dict(url=url,received_at=received,csv_sha256=digest(path),raw_sha256=hashlib.sha256(body).hexdigest(),rows=len(rows),end=rows[-1]["date"])
    (root/"index_manifest.json").write_text(json.dumps(meta,indent=2)+"\n")
    load_indices(root,[r["date"] for r in rows]);return meta


def histories(panel,audit,prices,snapshots,sessions,day):
    a=json.loads(Path(audit).read_text())
    if digest(panel)!=a["panel_sha256"]:raise ValueError("BOOTSTRAP_PANEL_HASH_MISMATCH")
    tails=defaultdict(lambda:deque(maxlen=100));events={(e["ticker"],e["date"]) for e in a["reference_rebase_candidates"]}
    with gzip.open(panel,"rt") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in prices and r["date"]<day:tails[r["ticker"]].append(r)
    grid={d:i for i,d in enumerate(sessions)};result={};excluded={}
    for t,price in prices.items():
        by={r["date"]:r for r in tails[t]}
        for d,s in snapshots.items():
            if d<day and t in s["rows"]:by[d]=s["rows"][t]
        by[day]=dict(price,date=day);past=[];prev=None
        for d,row in sorted(by.items()):
            if d not in grid:raise ValueError("PRICE_DATE_NOT_IN_BENCHMARK_GRID")
            vals={k:float(row[k]) for k in ("open","high","low","close","volume","turnover_krw")}
            valid=all(math.isfinite(v) for v in vals.values()) and 0<vals["low"]<=min(vals["open"],vals["close"])<=max(vals["open"],vals["close"])<=vals["high"] and vals["volume"]>0 and vals["turnover_krw"]>0
            reset=(t,d) in events or bool(row.get("action_boundary",False))
            if prev:reset=reset or grid[d]!=grid[prev["date"]]+1 or row["name"]!=prev["name"] or (prev["close"]>0 and abs(vals["close"]/prev["close"]-1)>.35)
            if reset or not valid:past=[]
            if valid:past.append(dict(vals,date=d,name=row["name"],segment=0))
            prev=dict(row,close=vals["close"])
        if len(past)>=65:result[t]=past[-90:]
        else:excluded[t]="CONTINUOUS_VALID_HISTORY_LT_65"
    return result,excluded


def support_diagnostic(past,plans):
    s=structure(past)
    if s is None:return dict(status="NO_CONFIRMED_VALID_STRUCTURE",buy_approved=False)
    days=[b["date"] for b in past];close=past[-1]["close"];current_atr=atr14(past)
    return dict(status="MOST_RECENT_ALREADY_CONFIRMED_PIVOT",pivot_date=s["pivot_date"],confirmed_on=s["confirmed_on"],
        pivot_age_sessions=len(days)-1-days.index(s["pivot_date"]),confirmation_age_sessions=len(days)-1-days.index(s["confirmed_on"]),
        support=s["support"],structure_stop=s["stop"],distance_from_close_pct=100*(close-s["stop"])/close,
        distance_from_close_current_atr=(close-s["stop"])/current_atr,
        plans={v:dict(distance_pct=p["plan"].get("risk_pct"),costed_r1_rr=p["plan"].get("net_r1_rr"),r1_unknown=p["plan"]["resistance"] is None) for v,p in plans.items() if p["plan"]},
        stop_moved_for_existing_signal=False,buy_approved=False,not_a_new_profitability_rule=True)


def choose(prices,past,basics,kind,secondary,indices,sessions,known_at,meta,run_id,code_hash):
    if sessions[-1]!=meta["asof"] or any(rows[-1]["date"]!=meta["asof"] or any(b["date"]>meta["asof"] for b in rows) for rows in past.values()):raise ValueError("FUTURE_OR_STALE_SELECTION_HISTORY")
    counts=Counter();pool=[]
    for t,p in sorted(prices.items()):
        reason=classify(p,basics.get(t),kind.get(t),secondary[t]);counts[reason]+=1
        if reason!="VERIFIED_NONBIO_COMMON_AS_REPORTED" or t not in past:continue
        bars=past[t];market=p["market"];index=indices[market]
        mret=100*(index[p["asof"]]/index[bars[-21]["date"]]-1);f=selection_features(bars,mret)
        if f is None:continue
        pool.append(dict(ticker=t,name=p["name"],market=market,industry=secondary[t][0]["sector"],market_regime=regime([index[d] for d in sessions]),
            **f,**causal_factors(bars,index)))
    pool.sort(key=lambda r:(-r["turnover20"],-r["rs20"],r["ticker"]))
    selected={"A":pool[:2],"B":[r for r in pool if r["own_rs20"]>0 and r["rs_accel5"]>0][:2]};models={}
    for model,rows in selected.items():
        models[model]=[]
        for rank,r in enumerate(rows,1):
            bars=past[r["ticker"]];mret=100*(indices[r["market"]][meta["asof"]]/indices[r["market"]][bars[-21]["date"]]-1)
            f,error=features(bars,mret);plans={}
            for variant in ENTRIES:
                p,why=entry_plan(r["ticker"],bars,f,variant,r["market_regime"]) if f else (None,error)
                plans[variant]=dict(plan=p,reason=why)
            models[model].append(dict(r,signal_id=signal_id(meta["asof"],model,r["ticker"]),model=model,model_version="V7_CURRENT_NATIVE_BOARD",rank=rank,
                decision_date=meta["asof"],registered_at=known_at,source_received_at=meta["received_at"],source_run_id=str(run_id),source_price_asof=meta["asof"],
                reference_close=r["close"],selection_reasons=["CLOSE_GT_MA20_GT_MA50","POSITIVE_OWN_BOARD_RS20","TURNOVER20_RANK"]+(["OWN_BOARD_RS_IMPROVING_5"] if model=="B" else []),
                entry_plans=plans,support_review=support_diagnostic(bars,plans),order_validity_sessions=1,
                invalidation=["CLOSE_BELOW_FROZEN_STOP_THEN_NEXT_TRADABLE_OPEN","EXPIRED_ONE_ENTRY_SESSION","MISSING_OR_ACTION_DATA_CENSORED"],
                source_regular_only_certified=meta["regular_only_certified"],price_basis=meta["price_basis"],buy_approved=False,live_action="CASH",chart_bars=bars[-90:]))
    return models,dict(price_rows=len(prices),classification_counts=dict(counts),continuous_history=len(past),
        analysis_eligible=sum(classify(prices[t],basics.get(t),kind.get(t),secondary[t])=="VERIFIED_NONBIO_COMMON_AS_REPORTED" for t in past),
        a_candidates=len(pool),b_candidates=sum(r["own_rs20"]>0 and r["rs_accel5"]>0 for r in pool),history_excluded=len(prices)-len(past))


def next_execution(day,sessions):
    # Only require the next known clock for same-day registration. This is a
    # deadline, NOT a fabricated trading session: exchange-open validation is
    # supplied by subsequent actual index/market dates before any model fill.
    d=datetime.fromisoformat(day).date()+timedelta(days=1)
    while d.weekday()>=5:d+=timedelta(days=1)
    return d.isoformat()+"T09:00:00+09:00"


def run(panel,audit,baseline,basic,scope,indices_dir,fresh,root,outdir,run_id):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True);root=Path(root)
    now=datetime.now(timezone.utc).isoformat();local=stamp(now).astimezone(KST);today=local.date().isoformat();errors=[];batch=None;counts=None;added=False
    timing='NO_COMPLETED_PRICE_SOURCE'
    if today<"2026-11-06":errors.append("FORWARD_NOT_STARTED_NO_RETROACTIVE_DECISION")
    prices,fresh_meta=fresh_snapshot(fresh);probe_meta=json.loads((Path(fresh)/"krx_v65_collect_status.json").read_text())
    if prices is None:errors.append(fresh_meta["status"])
    dates=[r["date"] for r in read_csv(Path(indices_dir)/"KOSPI_index.csv")];indices,index_meta=load_indices(indices_dir,dates)
    if any(stamp(v["received_at"])>stamp(now) for v in index_meta["series"].values()):raise ValueError("FUTURE_INDEX_RECEIPT")
    source_hashes=dict(panel=digest(panel),audit=digest(audit),classification=digest(Path(scope)/"classification_sources.json"),index_manifest=digest(Path(indices_dir)/"index_manifest.json"),
        pipeline_code=digest(__file__),ledger_code=digest(Path(__file__).with_name("c3_forward_ledger_v8.py")),entry_code=digest(Path(__file__).with_name("c3_entry_practical_v7.py")),protocol=digest('config/c3_forward_v8_protocol.json'),runtime_protocol=digest('config/c3_runtime_v9_protocol.json'))
    protocol=json.loads(Path('config/c3_forward_v8_protocol.json').read_text())
    if protocol['entry_methods']!=list(ENTRIES) or protocol['costs']!={'buy':BUY,'sell':SELL,'slippage_each_side':SLIP}:raise ValueError('FROZEN_RESEARCH_PROTOCOL_MISMATCH')
    # Missing warmup sessions may be collected now as price receipts. They are
    # never registered as past decisions or retroactive fills.
    for folder in sorted(Path(fresh).parent.glob("????-??-??")):
        pm=folder/"krx_v65_collect_status.json"
        if not pm.exists() or folder.name>=today:continue
        pp,mm=fresh_snapshot(folder)
        if pp and mm["asof"] in dates:
            dd=[d for d in dates if d<=mm["asof"]];ix={m:{d:v for d,v in vv.items() if d<=mm["asof"]} for m,vv in indices.items()}
            sm=dict(asof=mm["asof"],received_at=mm["retrieval_utc"],provider="KRX_OFFICIAL_EOD",price_basis="UNADJUSTED_AS_TRADED",source_scope="OFFICIAL_EOD_REGULAR_SCOPE_UNCERTIFIED",authenticated=True,
                regular_only_certified=bool(mm.get("independent_1530_regular_session_certified",False)),source_run_id=str(run_id),source_manifest_sha256=digest(pm))
            freeze_market(root,market_payload(list(pp.values()),ix,dd,sm),now)
    if prices:
        from c3_runtime_v9 import registration_window
        day=fresh_meta["asof"]
        timing=registration_window(day,stamp(now));eligible=timing in ('SAME_COMPLETED_SESSION','DELAYED_BEFORE_NEXT_POSSIBLE_OPEN')
        if not eligible:errors.append(timing)
        if day>today or (day==today and local.hour*60+local.minute<930):errors.append('PRICE_SESSION_NOT_COMPLETED')
        elif day not in indices["KOSPI"] or day not in indices["KOSDAQ"]:errors.append("CURRENT_BENCHMARK_MISSING")
        else:
            dates=[d for d in dates if d<=day];indices={m:{d:v for d,v in ix.items() if d<=day} for m,ix in indices.items()}
            meta=dict(asof=day,received_at=fresh_meta["retrieval_utc"],provider="KRX_OFFICIAL_EOD",price_basis="UNADJUSTED_AS_TRADED",source_scope="OFFICIAL_EOD_REGULAR_SCOPE_UNCERTIFIED",
                authenticated=True,regular_only_certified=bool(fresh_meta.get("independent_1530_regular_session_certified",False)),source_run_id=str(run_id),source_manifest_sha256=digest(Path(fresh)/"krx_v65_collect_status.json"))
            market=market_payload(list(prices.values()),indices,dates,meta);market,_=freeze_market(root,market,now)
            # Dated prior price receipts warm the current universe. They are
            # source caches, never retroactively registered selection signals.
            snapshots={read_record(p)["asof"]:read_record(p) for p in (root/"markets").glob("*.json.gz")}
            old,oldmeta=fresh_snapshot(baseline)
            if old:
                bday=oldmeta["asof"];snapshots[bday]=dict(rows={t:dict(r,date=bday) for t,r in old.items()})
            allprices,basics,kind,secondary,sources=load_sources(fresh,basic,scope,now)
            past,excluded=histories(panel,audit,allprices,snapshots,dates,day)
            models,counts=choose(allprices,past,basics,kind,secondary,indices,dates,now,meta,run_id,source_hashes["pipeline_code"])
            batch=dict(schema="C3_FORWARD_DECISION_V8",decision_date=day,price_asof=day,known_at=now,source_received_at=meta["received_at"],expected_last_completed_session=day,
                execution_open_at=next_execution(day,dates),execution_date_is_provisional_until_observed=True,models=models,scope=counts,source_hashes=source_hashes,
                source_snapshot_hash=hash_value(market),model_code_sha256=source_hashes["pipeline_code"],execution_version=execution_version(),synthetic_source=False,orders_enabled=False,live_action="CASH")
            if counts["analysis_eligible"]==0:errors.append("INSUFFICIENT_CONTINUOUS_HISTORY_NO_DECISION")
            elif eligible:
                if day!=today:
                    batch.update(schema='C3_FORWARD_DECISION_V9',decision_date=today,allow_delayed_preopen=True,registration_timing=timing)
                    for rows in batch['models'].values():
                        for r in rows:r.update(decision_date=today,source_price_asof=day,registration_timing=timing)
                batch,added=register(root,batch,now)
    observations,performance=advance(root,now,run_id)
    previous=json.loads(Path('reports/c3_work7_20261105/current/current_candidates.json').read_text())
    preview=(batch["models"]["B"] if batch else [dict(r,chart_bars=previous["chart_bars"].get(r["ticker"],[])) for r in previous["research_top2"]])
    source_registered=bool(batch and (root/'decisions'/(batch['price_asof']+'.json')).exists())
    registered=bool(source_registered and batch['decision_date']==today)
    if not source_registered:preview=[dict(r,registered_at=None,analysis_known_at=now,trade_approved=False) for r in preview]
    result=dict(schema="C3_DAILY_RESEARCH_V8",generated_at=now,report_day_kst=today,source_run_id=str(run_id),
        source_price_asof=fresh_meta.get("asof") if prices else None,source_received_at=fresh_meta.get("retrieval_utc") if prices else None,
        attempted_price_asof=probe_meta.get("asof"),probe_received_at=probe_meta.get("retrieval_utc"),last_confirmed_price_asof=fresh_meta['asof'] if prices else previous["price_asof"],
        source_diagnostics=probe_meta.get('response_diagnostics',[]),source_collection_status=probe_meta.get('status'),
        current_scope=counts,last_confirmed_scope=previous["currently_analyzable"],errors=errors,new_decision_registered=added,
        new_registered_signals=sum(len(x) for x in batch["models"].values()) if added else 0,new_registered_unique_tickers=len({r["ticker"] for rows in batch["models"].values() for r in rows}) if added else 0,
        research_top2=preview,research_top2_is_registered_today=registered,
        research_top2_registered_for_source_session=source_registered,registration_timing=timing,
        preview_price_asof=batch["price_asof"] if batch else previous["price_asof"],performance=performance,observations=observations,
        forward_start="2026-11-06",current_action="CASH",approved_top2=[],gpt_actual_model_runs=0,paid_api_calls=0,orders_enabled=False,
        scheduler_deployed=False,default_branch_modified=False,notifications_modified=False,source_hashes=source_hashes)
    (outdir/"latest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("report_day_kst","source_price_asof","preview_price_asof","new_registered_signals","new_decision_registered","errors","current_action")},ensure_ascii=False));return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("panel","audit","baseline","basic","scope","indices","fresh","ledger","outdir"):p.add_argument("--"+k,required=True)
    p.add_argument("--run-id",default="LOCAL_READ_ONLY");p.add_argument("--refresh-indices",action="store_true");p.add_argument('--invocation',default='')
    a=p.parse_args()
    if a.refresh_indices:
        try:collect_indices(a.indices,datetime.now(KST).date().isoformat())
        except Exception as exc:
            import shutil
            shutil.copytree('reports/c3_work7_20261105/sources',a.indices,dirs_exist_ok=True)
            Path(a.indices,'collection_error.json').write_text(json.dumps(dict(status='INDEX_COLLECTION_FAILED_USING_DATED_CACHE',error_type=type(exc).__name__))+"\n")
    result=run(a.panel,a.audit,a.baseline,a.basic,a.scope,a.indices,a.fresh,a.ledger,a.outdir,a.run_id)
    if a.invocation:
        result['invocation']=json.loads(Path(a.invocation).read_text());result['invocation']['run_id']=a.run_id
        (Path(a.outdir)/'latest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
