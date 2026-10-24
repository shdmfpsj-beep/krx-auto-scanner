#!/usr/bin/env python3
"""v6.3 immutable as-of research signals + strictly later dated observation.

Freeze all 3-method decisions from a completed v5.8 run and preserve both
alternative limits. Forward observations are loaded ONLY from separately
dated and fingerprinted market-wide collection artifacts received AFTER
the freeze. Historic selected-universe backtests are never credited as forward
results. Regular-only price, PIT universe, calendar, and orders remain UNVERIFIED.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from entry_strategy_v58 import METHODS,nearest_ceiling
from free_structural_v52 import history_check
from first_pullback_v55 import net_reward_risk
from shadow_five_day_v59 import simulate

SCHEMA="C3_K100_FORWARD_LEDGER_V63"
VERSION=1
PROVENANCE="FROZEN_ASOF_UNCERTIFIED"
REQUIRED_METHODS=set(METHODS)
HORIZON=7  # 2-session limit validity + five-session maximum holding
EXCLUDE=("바이오","제약","PHARMA","BIOTECH")
POLICIES=("FIRST","SECOND")
FIELDS=("asof","ticker","name","method","variant","signal_condition",
        "signal_close_reference","research_entry_reference",
        "daily_structure_stop_reference","nearest_target_repriced_reference",
        "legacy_first_target_not_trusted","net_rr_repriced",
        "geometry_gate_pass","stock_exclusion_reasons","source_blockers",
        "result_status","filled_at","exit_date","net_return_pct",
        "net_r","trade_approved","orders_enabled")
def digest(payload):
    return hashlib.sha256(payload).hexdigest()
def canonical(d):
    return json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(",",":"),
        allow_nan=False).encode("utf-8")
def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
def read_csv(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))
def number(v):
    try:
        if isinstance(v,bool) or v in ("",None):return None
        n=float(v)
        return n if math.isfinite(n) and n>0 else None
    except (ValueError,TypeError):return None
def parse_date(v):
    try:
        d=date.fromisoformat(v)
        if d.isoformat()==v:return d
    except (TypeError,ValueError):pass
    raise ValueError("INVALID_MARKET_DATE")
def parse_utc(v):
    try:
        a=datetime.fromisoformat(v.replace("Z","+00:00"))
    except (ValueError,TypeError,AttributeError):
        raise ValueError("UTC_TIMESTAMP_INVALID")
    if a.tzinfo is None or a.utcoffset()!=timezone.utc.utcoffset(a):
        raise ValueError("UTC_TIMESTAMP_NOT_UTC")
    return a

def freeze(v58,recovery,source_ids,frozen_at):
    st=read_json(v58/"entry_strategy_v58_status.json")
    cand=read_csv(v58/"entry_strategy_v58_all.csv")
    rec=read_json(recovery/"status.json")
    history=read_csv(recovery/"candidate_daily_history_v52.csv")
    asof=parse_date(st.get("asof"))
    if (st.get("schema")!="C3_K100_FREE_ENTRY_V58"
        or rec.get("market_data_date")!=str(asof)
        or not rec.get("scan_complete") or not rec.get("data_date_verified")
        or st.get("source_errors")!=[]
        or st.get("trade_approved") is not False
        or st.get("orders_enabled") is not False
        or st.get("regular_only_session_certified") is not False
        or len(cand)!=st.get("evaluated_method_rows")
        or len(cand)!=3*st.get("candidates")):
        raise ValueError("V58_RECOVERY_DATED_COMPLETENESS_FAILED")
    ts=parse_utc(frozen_at)
    if ts.date()<asof:
        raise ValueError("FREEZE_PRECEDES_COMPLETED_SESSION")
    if (not isinstance(source_ids,dict) or
        set(source_ids)!={"v58_run_id","recovery_run_id"} or
        any(not str(s).isdigit() for s in source_ids.values())):
        raise ValueError("EXACT_UPSTREAM_RUN_IDS_REQUIRED")
    seen=set();triggers=[];groups=defaultdict(list)
    for bar in history:groups[bar["ticker"]].append(bar)
    for r in cand:
        k=(r.get("ticker"),r.get("method"))
        if (k in seen or k[1] not in REQUIRED_METHODS
            or len(k[0] or "")!=6 or not k[0].isdigit()
            or r.get("asof")!=str(asof)
            or r.get("trade_approved")!="False"
            or r.get("orders_enabled")!="False"):
            raise ValueError("DUPLICATE_OR_UNSAFE_ASOF_ROWS")
        seen.add(k)
        if r.get("setup")=="RESEARCH_TRIGGER_CONFIRMED_ASOF":
            triggers.append(r)
    if len(seen)!=len(cand) or len(triggers)!=sum(st["method_trigger_counts"].values()):
        raise ValueError("TRIGGER_TOTAL_DIVERGES")
    if Counter(r["method"] for r in triggers)!=Counter({
        k:v for k,v in st["method_trigger_counts"].items() if v}):
        raise ValueError("METHOD_TRIGGER_COUNTS_MISMATCH")
    plans=[]
    for r in sorted(triggers,key=lambda x:(x["ticker"],x["method"])):
        ticker=r["ticker"]
        bars,error=history_check(groups.get(ticker,[]),ticker,asof)
        if error:raise ValueError("TRIGGER_HISTORY_INVALID_"+error)
        signal_close=number(r.get("asof_close_research"))
        stop=number(r.get("stop_reference"))
        if signal_close is None or signal_close!=bars[-1]["close"]:
            raise ValueError("TRIGGER_HISTORY_CLOSE_MISMATCH")
        exclusions=[s for s in EXCLUDE if s in r.get("name","").upper()]
        for variant in POLICIES:
            entry=number(r.get("first_entry_reference" if variant=="FIRST"
                                else "second_entry_reference"))
            target=nearest_ceiling(bars,entry) if entry else None
            rr=(net_reward_risk(entry,stop,target,0.5)
                if entry is not None and stop is not None and
                target is not None and stop<entry<target else None)
            risk=(100*(entry-stop)/entry if entry and stop and entry>stop else None)
            atr=number(r.get("atr14"))
            gap=((signal_close-entry)/atr if entry and atr else None)
            good=bool(rr is not None and rr>=2 and risk is not None
                and (2<=risk<=12 if variant=="FIRST" else 1<=risk<=12)
                and gap is not None and gap<=(1 if variant=="FIRST" else 2)
                and not exclusions)
            plans.append(dict(asof=str(asof),ticker=ticker,name=r.get("name",""),
                method=r["method"],variant=variant,
                signal_condition=r.get("signal_condition",""),
                signal_close_reference=signal_close,
                research_entry_reference=entry,
                daily_structure_stop_reference=stop,
                nearest_target_repriced_reference=target,
                legacy_first_target_not_trusted=True,
                net_rr_repriced=round(rr,4) if rr is not None else None,
                geometry_gate_pass=good,
                stock_exclusion_reasons=exclusions,
                source_blockers=r.get("blocking_reasons","").split(";"),
                result_status="PENDING_FUTURE_SESSIONS",
                filled_at=None,exit_date=None,net_return_pct=None,
                net_r=None,trade_approved=False,orders_enabled=False))
    if len(plans)!=2*len(triggers):raise ValueError("PLAN_COUNT_INCOMPLETE")
    manifest=dict(schema=SCHEMA,version=VERSION,asof=str(asof),
        freeze_utc=ts.isoformat(),source_run_ids=source_ids,
        source_sha256=dict(v58_status=digest((v58/"entry_strategy_v58_status.json").read_bytes()),
            v58_rows=digest((v58/"entry_strategy_v58_all.csv").read_bytes()),
            recovery_status=digest((recovery/"status.json").read_bytes()),
            recovery_history=digest((recovery/"candidate_daily_history_v52.csv").read_bytes())),
        original_method_rows=len(cand),asof_signal_count=len(triggers),
        frozen_alternative_count=len(plans),
        frozen_payload_sha256=digest(canonical(plans)),
        freeze_status=PROVENANCE,
        research_source_regular_only_certified=False,
        account_position_and_capital_gate_verified=False,
        prospective_pre_first_followup_session_open_verified=False,
        future_session_calendar_completeness_verified=False,
        independently_verified_close_consensus=False,
        retrospective_selection_not_counted_as_forward_trades=True,
        orders_enabled=False,trade_approved=False,decision="CASH")
    return manifest,plans

def verify_snapshot(manifest,plans):
    if (manifest.get("schema")!=SCHEMA or manifest.get("version")!=VERSION or
        manifest.get("freeze_status")!=PROVENANCE or
        manifest.get("trade_approved") is not False or
        manifest.get("orders_enabled") is not False or
        manifest.get("frozen_alternative_count")!=len(plans) or
        len(plans)!=2*manifest.get("asof_signal_count",-1) or
        manifest.get("frozen_payload_sha256")!=digest(canonical(plans))):
        raise ValueError("IMMUTABLE_SNAPSHOT_HASH_OR_STATUS_INVALID")
    asof=parse_date(manifest["asof"])
    frozen_at=parse_utc(manifest["freeze_utc"])
    if frozen_at.date()<asof:raise ValueError("SOURCE_SNAPSHOT_TIME_INVALID")
    seen=set()
    for x in plans:
        key=(x["ticker"],x["method"],x["variant"])
        if (x.get("asof")!=str(asof) or x.get("trade_approved") is not False
            or x.get("orders_enabled") is not False or x["method"] not in METHODS
            or x["variant"] not in POLICIES or key in seen):
            raise ValueError("SNAPSHOT_UNSAFE_OR_DUPLICATE_PLAN")
        seen.add(key)
    return asof,frozen_at

def load_daily(root,asof,frozen_at):
    """Directory YYYY-MM-DD/{KOSPI.csv,KOSDAQ.csv,meta.json} in order.

    Every meta contains exact v18 run ID, asof, created_utc and per-file SHA256.
    No silently imputed holidays or missing dates. Still not an official KRX
    trading calendar, so completion remains PROVISIONAL_UNCERTIFIED.
    """
    grouped={}
    if not Path(root).exists():return grouped,[]
    for folder in sorted(Path(root).iterdir()):
        if not folder.is_dir():raise ValueError("UNEXPECTED_FORWARD_ROOT_FILE")
        trading=parse_date(folder.name)
        if trading<=asof:raise ValueError("SAME_OR_PAST_DAY_FORWARD_SOURCE_FORBIDDEN")
        meta_path=folder/"meta.json"
        if not meta_path.is_file():raise ValueError("MISSING_DAY_PROVENANCE")
        meta=read_json(meta_path)
        stamp=parse_utc(meta.get("source_completed_utc"))
        if (meta.get("asof")!=str(trading) or
            not str(meta.get("v18_run_id","")).isdigit() or
            stamp<=frozen_at or not meta.get("source_run_success") or
            meta.get("regular_only_verified") is not False):
            raise ValueError("DATE_MISMATCH_OR_SOURCE_NOT_FROZEN_FIRST")
        todays={}
        for market in ("KOSPI","KOSDAQ"):
            p=folder/(market+".csv")
            if (not p.is_file() or
                digest(p.read_bytes())!=meta.get("sha256",{}).get(market)):
                raise ValueError("DAILY_MARKET_FILE_SHA256_MISMATCH")
            rr=read_csv(p)
            if not rr:raise ValueError("DAILY_UNIVERSE_EMPTY")
            for r in rr:
                ticker=r.get("ticker")
                if (len(ticker or "")!=6 or not ticker.isdigit()
                    or r.get("Date")!=str(trading) or ticker in todays):
                    raise ValueError("DUPLICATE_STOCK_OR_DAILY_DATE_MISMATCH")
                fields={}
                for name in ("Open","High","Low","Close","Volume"):
                    v=number(r.get(name))
                    if v is None:fields=None;break
                    fields[name.lower()]=v
                # A suspended stock or a zero-volume day is missing price
                # evidence, not an automatic profitable exit.
                if fields is not None and (
                    not fields["low"]<=min(fields["open"],fields["close"])<=
                      max(fields["open"],fields["close"])<=fields["high"]
                    or fields["volume"]<=0):
                    fields=None
                todays[ticker]=(dict(date=trading,**fields) if fields else None)
        grouped[trading]=todays
    return grouped,sorted(grouped)

def evaluate(manifest,plans,future_root):
    asof,ts=verify_snapshot(manifest,plans)
    data,sessions=load_daily(future_root,asof,ts)
    observed=min(len(sessions),HORIZON)
    outcomes=[]
    for plan in plans:
        r=dict(plan)
        # A pending outcome is always an explicit NULL, even if an older
        # separately constructed snapshot left these optional fields absent.
        for key in ("filled_at","exit_date","net_return_pct","net_r"):
            r.setdefault(key,None)
        if plan.get("research_entry_reference") is None or (
            plan.get("daily_structure_stop_reference") is None or
            plan.get("nearest_target_repriced_reference") is None):
            r["result_status"]="REFERENCE_INVALID_NO_ORDER"
        elif observed<HORIZON:
            r["result_status"]="PENDING_COMPLETE_SEVEN_MARKET_SESSIONS"
        else:
            candles=[data[day].get(plan["ticker"]) for day in sessions[:HORIZON]]
            if any(v is None for v in candles):
                r["result_status"]="TICKER_MISSING_OR_SUSPENDED_NO_IMPUTATION"
            else:
                simplan=dict(ticker=plan["ticker"],method=plan["method"],
                    asof=str(asof),
                    stop_reference=plan["daily_structure_stop_reference"],
                    first_entry_reference=plan["research_entry_reference"],
                    nearest_resistance_reference=plan["nearest_target_repriced_reference"])
                sim=simulate(simplan,candles,"FIRST")
                r.update(result_status="PROVISIONAL_"+sim["outcome"],
                    filled_at=sim.get("entry_date"),exit_date=sim.get("exit_date"),
                    net_return_pct=sim.get("net_return_pct"),
                    net_r=sim.get("net_r"))
        r["trade_approved"]=False;r["orders_enabled"]=False
        outcomes.append(r)
    report=dict(schema=SCHEMA,asof=str(asof),freeze_utc=manifest["freeze_utc"],
        frozen_payload_sha256=manifest["frozen_payload_sha256"],
        observed_future_distinct_market_dates=[d.isoformat() for d in sessions],
        observed_full_market_snapshot_days=len(sessions),
        required_for_2day_entry_5day_hold=HORIZON,
        frozen_research_alternatives=len(outcomes),
        pending_count=sum(x["result_status"].startswith("PENDING") for x in outcomes),
        provisional_filled_scenarios=sum(x["result_status"].startswith(
            ("PROVISIONAL_NET_WIN","PROVISIONAL_NET_LOSS","PROVISIONAL_NET_FLAT"))
            for x in outcomes),
        officially_verified_forward_trade_count=0,
        forward_calendar_complete_officially_verified=False,
        all_prices_regular_only_verified=False,
        source_is_20261023_hindsight_selected_universe=True,
        account_verified=False,orders_enabled=False,trade_approved=False,
        decision="CASH",status=("WAITING_FOR_NEW_DAILY_SOURCES"
                  if observed<HORIZON else "PROVISIONAL_NONCERTIFIED_SEVEN_SESSIONS"))
    return report,outcomes

def save(output,manifest,plans=None,report=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if plans is not None:
        (output/"frozen_v63_manifest.json").write_bytes(
            json.dumps(manifest,ensure_ascii=False,indent=2).encode("utf-8"))
        (output/"frozen_v63_signals.json").write_bytes(
            json.dumps(plans,ensure_ascii=False,indent=2).encode("utf-8"))
        q=dict(asof=manifest["asof"],freeze_utc=manifest["freeze_utc"],
            signal_count=manifest["asof_signal_count"],
            first_and_alternative_second_count=manifest["frozen_alternative_count"],
            payload_sha256=manifest["frozen_payload_sha256"],decision="CASH")
        (output/"frozen_v63_mobile.md").write_text(
            "# v6.3 날짜별 신호 원본 고정\n\n"+
            json.dumps(q,ensure_ascii=False,indent=2)+
            "\n\n정규장 가격·종목분류·거래대금 검증되지 않은 연구가격입니다. "+
            "미래 5일 수익은 아직 관측하지 않았으며 실전 매수승인 0건.\n",
            encoding="utf-8")
    if report is not None:
        (output/"forward_v63_status.json").write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        with (output/"forward_v63_all.csv").open(
            "w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
            w.writeheader()
            for x in manifest:
                w.writerow({**x,
                    "stock_exclusion_reasons":";".join(x.get("stock_exclusion_reasons",[])),
                    "source_blockers":";".join(x.get("source_blockers",[]))})
        (output/"forward_v63_mobile.md").write_text(
            f"# v6.3 실제 날짜 신호의 전진 관찰\n\n기준일: {report['asof']}\n"
            f"원본 고정일: {report['freeze_utc']}\n"
            f"관측된 이후 거래일: {report['observed_full_market_snapshot_days']}/7\n"
            f"상태: **{report['status']}**\n"
            "검증된 실전 수익률/매수신호 없음. 결론 **CASH**.\n",
            encoding="utf-8")

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    f=sub.add_parser("freeze")
    for arg in ("--v58","--recovery","--outdir"):f.add_argument(arg,required=True)
    f.add_argument("--v58-run-id",required=True);f.add_argument("--recovery-run-id",required=True)
    f.add_argument("--frozen-at-utc",required=True)
    e=sub.add_parser("evaluate")
    for arg in ("--snapshot","--future","--outdir"):e.add_argument(arg,required=True)
    args=p.parse_args()
    if args.command=="freeze":
        manifest,plans=freeze(Path(args.v58),Path(args.recovery),
            {"v58_run_id":args.v58_run_id,"recovery_run_id":args.recovery_run_id},
            args.frozen_at_utc)
        save(args.outdir,manifest,plans)
        print(json.dumps(dict(asof=manifest["asof"],signals=len(plans)//2,
            alternatives=len(plans),sha256=manifest["frozen_payload_sha256"],
            decision="CASH"),ensure_ascii=False))
    else:
        root=Path(args.snapshot)
        manifest=read_json(root/"frozen_v63_manifest.json")
        plans=read_json(root/"frozen_v63_signals.json")
        report,results=evaluate(manifest,plans,args.future)
        save(args.outdir,results,report=report)
        print(json.dumps(dict(asof=report["asof"],
            observed_dates=report["observed_future_distinct_market_dates"],
            status=report["status"],decision="CASH"),ensure_ascii=False))
if __name__=="__main__":main()
