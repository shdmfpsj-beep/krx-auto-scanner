"""Current-only, dated whole-scope research candidates. Never a BUY approval."""
import argparse,csv,hashlib,json,math,statistics
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path

from c3_selection_scope_v5 import load_sources,current_histories,classify,selection_features,read_csv,unique_index,digest,freeze_forward
from c3_daily_report_v4 import known_by
from c3_selection_factors_v6 import load_indices,causal_factors,regime,review_packet,validate_review
from c3_entry_practical_v7 import ENTRIES,entry_plan,features


def fresh_snapshot(folder):
    path=Path(folder)/"krx_v65_collect_status.json"
    if not path.exists():return None,dict(status="FRESH_SOURCE_NOT_PROVIDED")
    meta=json.loads(path.read_text())
    if not meta.get("krx_eod_authenticated") or not meta.get("official_market_rows"):
        return None,dict(status=meta.get("status","FRESH_SOURCE_UNAVAILABLE"),asof=meta.get("asof"),rows=meta.get("official_market_rows",0))
    rows=[]
    for market in ("KOSPI","KOSDAQ"):
        p=path.parent/(market+"_official.csv")
        if digest(p)!=meta["market_file_sha256"][market]:raise ValueError("FRESH_PRICE_HASH_MISMATCH")
        rr=read_csv(p)
        if any(r["market"]!=market or r["asof"]!=meta["asof"] for r in rr):raise ValueError("FRESH_PRICE_DATE_OR_MARKET_MISMATCH")
        rows+=rr
    if len(rows)!=meta["official_market_rows"]:raise ValueError("FRESH_PRICE_COUNT_MISMATCH")
    return unique_index(rows),meta


def append_current(history,row,previous_day,index_dates):
    day=row["asof"]
    if day not in index_dates or previous_day not in index_dates or index_dates.index(day)!=index_dates.index(previous_day)+1:return None,"NOT_NEXT_MATCHED_SESSION"
    if row["name"]!=history[-1]["name"]:return None,"IDENTITY_CHANGED"
    values={k:float(row[k]) if row[k] not in (None,"","None") else None for k in ("open","high","low","close","volume","turnover_krw")}
    if row["valid_daily_bar"]!="True" or not all(v is not None and math.isfinite(v) for v in values.values()):return None,"LATEST_BAR_INVALID"
    if not 0<values["low"]<=min(values["open"],values["close"])<=max(values["open"],values["close"])<=values["high"] or values["volume"]<=0 or values["turnover_krw"]<=0:return None,"LATEST_BAR_NOT_TRADABLE"
    if abs(values["close"]/history[-1]["close"]-1)>.35:return None,"UNRESOLVED_PRICE_UNIT_CHANGE"
    return history+[dict(values,date=day,name=row["name"],segment=0)],None


def bull_bear_review(packet,review,recorded_at):
    if not packet.get("execution_open_at"):raise ValueError("EXECUTION_OPEN_NOT_DECLARED")
    bull=review.get("bull_evidence_keys",[]);bear=review.get("bear_evidence_keys",[])
    if review.get("decision")!="ABSTAIN" and (not bull or not bear):raise ValueError("BOTH_BULL_AND_BEAR_EVIDENCE_REQUIRED")
    if set(review.get("evidence_keys",[]))!=set(bull)|set(bear):raise ValueError("REVIEW_EVIDENCE_UNION_MISMATCH")
    return validate_review(packet,review,recorded_at)


def run(panel,audit,latest,basic,scope,indices_dir,fresh,outdir,execution_open_at=None):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);now=datetime.now(timezone.utc).isoformat()
    prices,basics,kind,secondary,sources=load_sources(latest,basic,scope,now)
    histories,_=current_histories(panel,audit,prices);old_day=sources["price"]["asof"]
    meta=json.loads((Path(indices_dir)/"index_manifest.json").read_text());index_dates=[r["date"] for r in read_csv(Path(indices_dir)/"KOSPI_index.csv")]
    if any(not known_by(r["received_at"],now) for r in meta["series"].values()):raise ValueError("INDEX_NOT_YET_KNOWN")
    indices,_=load_indices(indices_dir,index_dates)
    eligible={t:p for t,p in histories.items() if classify(prices[t],basics.get(t),kind.get(t),secondary[t])=="VERIFIED_NONBIO_COMMON_AS_REPORTED"}
    base_count=len(eligible);rejected=Counter();fresh_prices,fresh_meta=fresh_snapshot(fresh) if fresh else (None,dict(status="NOT_PROVIDED"))
    if fresh_prices:
        local=datetime.fromisoformat(now).astimezone(timezone(timedelta(hours=9)))
        if not known_by(fresh_meta["retrieval_utc"],now):raise ValueError("FRESH_SOURCE_NOT_YET_KNOWN")
        if fresh_meta["asof"]>local.date().isoformat() or (fresh_meta["asof"]==local.date().isoformat() and (local.hour,local.minute)<(15,30)):raise ValueError("FRESH_SESSION_NOT_COMPLETED")
    quote_day=old_day
    if fresh_prices and fresh_meta["asof"]>old_day and all(fresh_meta["asof"] in indices[m] for m in indices):
        new={}
        for t,past in eligible.items():
            if t not in fresh_prices:rejected["MISSING_FRESH_SECURITY"]+=1;continue
            if classify(fresh_prices[t],basics.get(t),kind.get(t),secondary[t])!="VERIFIED_NONBIO_COMMON_AS_REPORTED":rejected["CURRENT_CLASSIFICATION_UNVERIFIED"]+=1;continue
            value,reason=append_current(past,fresh_prices[t],old_day,index_dates)
            if value:new[t]=value
            else:rejected[reason]+=1
        eligible=new;prices=fresh_prices;quote_day=fresh_meta["asof"]
    elif fresh_prices:rejected["FRESH_INDEX_DATE_UNAVAILABLE_OR_NOT_NEWER"]+=1
    pool=[];a_count=0
    for t,past in sorted(eligible.items()):
        market=prices[t]["market"];index=indices[market]
        mret=100*(index[quote_day]/index[past[-21]["date"]]-1);a=selection_features(past,mret)
        if a is None:continue
        a_count+=1;f=causal_factors(past,index)
        if f["own_rs20"]<=0 or f["rs_accel5"]<=0:continue
        pool.append(dict(ticker=t,name=prices[t]["name"],market=market,price_asof=quote_day,close=past[-1]["close"],
            turnover20=a["turnover20"],rs20=a["rs20"],market_regime=regime([index[d] for d in index_dates if d<=quote_day]),
            industry=secondary[t][0]["sector"],**f))
    pool.sort(key=lambda r:(-r["turnover20"],-r["rs20"],r["ticker"]))
    top=[];packets=[]
    source_hashes=dict(panel=digest(panel),old_price_manifest=digest(Path(latest)/"krx_v65_collect_status.json"),
        classification=digest(Path(scope)/"classification_sources.json"),indices=digest(Path(indices_dir)/"index_manifest.json"),code=digest(__file__))
    if fresh_prices:source_hashes["fresh_price_manifest"]=digest(Path(fresh)/"krx_v65_collect_status.json")
    source_id=hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode()).hexdigest()
    for rank,r in enumerate(pool[:2],1):
        past=eligible[r["ticker"]];index=indices[r["market"]];mret=100*(index[quote_day]/index[past[-21]["date"]]-1)
        f,reason=features(past,mret);plans={}
        if f:
            for variant in ENTRIES:
                p,why=entry_plan(r["ticker"],past,f,variant,r["market_regime"]);plans[variant]=dict(plan=p,reason=why)
        top.append(dict(r,rank=rank,entry_plans=plans,structure_reason=reason,technical_only=True,trade_approved=False))
        packet=review_packet(r,source_id,now,execution_open_at)
        if f:packet["features"].update(structure_stop=f["structure"]["stop"],reference_close=past[-1]["close"],first_resistance=f["geometry"]["first_resistance"])
        packet["features"]["source_is_latest_expected_session"]=quote_day=="2026-11-05"
        packets.append(dict(research_rank=rank,packet=packet))
    # All prices have one date. No last-day rows from the secondary quote feed.
    result=dict(schema="C3_CURRENT_CANDIDATES_V7",generated_at=now,known_at=now,price_asof=quote_day,
        baseline_scope=base_count,currently_analyzable=len(eligible),fresh_source_status=fresh_meta.get("status"),fresh_exclusions=dict(rejected),
        a_native_index_candidates=a_count,b_native_index_candidates=len(pool),candidate_pool=pool,research_top2=top,
        historical_95_performance_not_generalized=True,current_native_index_gate_differs_from_old_cohort_proxy_gate=True,
        chart_bars={r["ticker"]:eligible[r["ticker"]][-90:] for r in top},
        regular_only_certified=False,corporate_actions_fully_verified=False,approved_top2=[],current_action="CASH",orders_enabled=False,
        new_unseen_completed={str(h):0 for h in (5,10,20)},forward_registration="NOT_REGISTERED_RESEARCH_SNAPSHOT_ONLY",source_hashes=source_hashes)
    (root/"current_candidates.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    (root/"gpt_review_packets.json").write_text(json.dumps(dict(actual_model_runs=0,paid_api_calls=0,packets=packets,
        required_output_fields=["packet_sha256","produced_at","reviewer","model_version","decision","bull_evidence_keys","bear_evidence_keys","evidence_keys","external_data_used"],
        output_template_is_not_a_model_result=True,performance_status="NOT_EXECUTED"),ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("price_asof","baseline_scope","currently_analyzable","a_native_index_candidates","b_native_index_candidates","current_action")}))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("panel","audit","latest","basic","scope","indices","outdir"):p.add_argument("--"+k,required=True)
    p.add_argument("--fresh",default="");p.add_argument("--register-forward",default="");p.add_argument("--expected-last-session",default="");p.add_argument("--execution-open-at",default="")
    a=p.parse_args();r=run(a.panel,a.audit,a.latest,a.basic,a.scope,a.indices,a.fresh,a.outdir,a.execution_open_at or None)
    if a.register_forward:
        stamp=datetime.now(timezone.utc);day=stamp.astimezone(timezone(timedelta(hours=9))).date().isoformat()
        freeze_forward(a.register_forward,dict(r,decision_date=day,expected_last_completed_session=a.expected_last_session,execution_open_at=a.execution_open_at),stamp.isoformat())
