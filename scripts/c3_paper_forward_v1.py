#!/usr/bin/env python3
"""C3 TOP2 prospective PAPER-FILL tracker with no brokerage trading.

A signal is registered after close and only subsequent independently observed
sessions may create hypothetical fills. Entry touch is an OHLC *assumption*,
not proof that a real limit order could have filled. No same-bar take-profit.
Close-below-structure-stop is acted on only at the NEXT observed session OPEN;
missing next-open is never replaced with a convenient later price.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from datetime import date
from pathlib import Path
from collections import Counter

VERSION="C3_TOP2_IMMUTABLE_PAPER_FORWARD_V1"
BUY_COST=0.0015
SELL_COST=0.005
PLANS_REQUIRED=("plan_id","ticker","name","selection_date","registered_day",
 "source_run_id","source_close","watch_low","watch_high","structure_stop",
 "target1","target2","expires_after_sessions","source_scope","stop_rule")
OHLC_REQUIRED=("ticker","date","open","high","low","close","volume")
NEXT_STOP_RULE="NEXT_OPEN_AFTER_CLOSE_BELOW_STOP"
PRICE_SCOPE="PYKRX_ADJUSTED_UNVERIFIED_REGULAR_SCOPE"

def load_csv(path,required):
    with Path(path).open(encoding="utf-8-sig",newline="") as file:
        r=csv.DictReader(file)
        if not set(required)<=set(r.fieldnames or []):
            raise ValueError("MISSING_COLUMNS:"+str(set(required)-set(r.fieldnames or [])))
        return list(r)

def numeric(s,field):
    try:v=float(s)
    except (ValueError,TypeError):raise ValueError("INVALID_"+field)
    if not math.isfinite(v) or v<=0:raise ValueError("INVALID_"+field)
    return v

def canonical_plan(row):
    p={k:str(row[k]).strip() for k in PLANS_REQUIRED}
    if not p["ticker"].isdigit() or len(p["ticker"])!=6 or not p["plan_id"]:
        raise ValueError("INVALID_TICKER_OR_ID")
    if p["stop_rule"]!=NEXT_STOP_RULE:raise ValueError("STOP_POLICY_UNSUPPORTED")
    if p["source_scope"]!="PYKRX_RESEARCH_REGULAR_ONLY_UNCERTIFIED":
        raise ValueError("UNVERIFIED_SCOPE_MUST_BE_DECLARED")
    if not date.fromisoformat(p["selection_date"])<=date.fromisoformat(p["registered_day"]):
        raise ValueError("PLAN_REGISTERED_BEFORE_SELECTION")
    if not (0<numeric(p["structure_stop"],"STOP")<
      numeric(p["watch_low"],"ENTRY_LOW")<=numeric(p["watch_high"],"ENTRY_HIGH")<
      numeric(p["source_close"],"SOURCE_CLOSE")<
      numeric(p["target1"],"T1")<numeric(p["target2"],"T2")):
        raise ValueError("PLAN_PRICE_SEQUENCE_INVALID")
    x=int(p["expires_after_sessions"])
    if not 1<=x<=20:raise ValueError("INVALID_EXPIRY_SESSIONS")
    return p

def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def init_state(plan):
    return dict(plan=plan,plan_sha256=plan_hash(plan),
      status="WAITING",sessions_observed=0,last_observed_date=None,
      entry_date=None,entry_price=None,assumed_fill_method=None,
      remaining_fraction=0,realized_net_krw_per_unit=0,
      target1_date=None,target2_date=None,exit_date=None,exit_price=None,
      last_close=None,last_mark_date=None,missed_after_entry=False,
      registered_without_retroactive_fill=True,
      source_regular_only_certified=False,trade_approved=False,orders_enabled=False)

def bar_valid(row):
    ticker=str(row["ticker"]).strip()
    day=date.fromisoformat(row["date"]).isoformat()
    o,h,l,c,v=[numeric(row[k],k.upper()) for k in ("open","high","low","close","volume")]
    if not l<=min(o,c)<=max(o,c)<=h:
        raise ValueError("INVALID_OHLC_BAR")
    return dict(ticker=ticker,date=day,open=o,high=h,low=l,close=c,volume=v)

def event(log,p,day,kind,price=None,detail=None):
    e=dict(event_key=f"{p['plan']['plan_id']}:{day}:{kind}",
       plan_id=p["plan"]["plan_id"],ticker=p["plan"]["ticker"],
       source_session=day,event=kind,mode="HYPOTHETICAL_OHLC_PAPER_ONLY",
       model_price_krw=price,details=detail or "",
       actual_broker_fill=False,regular_only_verified=False)
    if e["event_key"] not in {x["event_key"] for x in log}:log.append(e)

def sell(p,log,day,price,portion,kind):
    if portion<=0 or portion>p["remaining_fraction"]+.00001:
        raise ValueError("PAPER_EXIT_SHARE_INVALID")
    p["remaining_fraction"]=round(p["remaining_fraction"]-portion,8)
    gain=(price*(1-SELL_COST)-p["entry_price"]*(1+BUY_COST))*portion
    p["realized_net_krw_per_unit"]+=gain
    event(log,p,day,kind,price,f"fraction_of_initial_unit={portion:.2f};model_net_unit_krw={gain:.2f}")
    if p["remaining_fraction"]<1e-7:
        p["remaining_fraction"]=0
        p["exit_date"]=day;p["exit_price"]=price

def next_observed_session(prev,current,history_days):
    candidates=sorted(d for d in history_days if prev<d<=current)
    if not candidates or candidates[0]!=current:
        return False
    return True

def update_one(p,log,history,today,market_scan_asof):
    plan=p["plan"];ticker=plan["ticker"]
    registration=plan["registered_day"]
    dates=sorted(history)
    if not dates:return "NO_SOURCE_OHLCV"
    day=dates[-1]
    if day!=today:
        return "NO_NEW_TRADING_SESSION_TODAY"
    if day<=registration or day<=plan["selection_date"]:
        return "NOT_ELIGIBLE_UNTIL_SESSION_AFTER_REGISTRATION"
    if market_scan_asof!=day:
        return "FULL_MARKET_SCAN_DATE_NOT_MATCHED_NO_PAPER_FILLS"
    if p["status"] in ("CLOSED_T2","CLOSED_STOP","EXPIRED",
                       "CANCELLED_STOP_BEFORE_ENTRY",
                       "CANCELLED_TARGET_BEFORE_ENTRY",
                       "STOP_OPEN_MISSED_UNVERIFIABLE"):
        return "TERMINAL_POSITION_UNCHANGED"
    if p["last_observed_date"]==day:return "ALREADY_PROCESSED_IDEMPOTENT"
    previous=p["last_observed_date"] or plan["selection_date"]
    if not next_observed_session(previous,day,dates):
        # No favorable retroactive open/fill after a missing daily run.
        p["missed_after_entry"]=p["entry_date"] is not None
        p["status"]=("STOP_OPEN_MISSED_UNVERIFIABLE" if
             p["status"]=="STOP_PENDING" else "DATA_GAP_HOLD")
        event(log,p,day,"MISSING_PRIOR_SESSION_GAP_NO_BACKFILL",None,
              "No new fills/exits until a separately documented reconciliation")
        p["last_observed_date"]=day
        return "GAP_NO_BACKFILL"
    if p["status"]=="DATA_GAP_HOLD":
        return "DATA_GAP_HOLD_NO_AUTOMATIC_RECOVERY"
    row=history[day]
    p["last_observed_date"]=day;p["last_close"]=row["close"];p["last_mark_date"]=day
    stop=numeric(plan["structure_stop"],"STOP")
    low=numeric(plan["watch_low"],"LOW");high=numeric(plan["watch_high"],"HIGH")
    t1=numeric(plan["target1"],"T1");t2=numeric(plan["target2"],"T2")
    if p["status"]=="STOP_PENDING":
        sell(p,log,day,row["open"],p["remaining_fraction"],"NEXT_OPEN_STOP_EXIT_ASSUMED")
        p["status"]="CLOSED_STOP"
        return "CLOSED_AT_NEXT_SESSION_OPEN_AFTER_PRIOR_CLOSE_STOP"
    if p["status"]=="WAITING":
        p["sessions_observed"]+=1
        touch=row["low"]<=high and row["high"]>=low
        if touch and row["open"]<low:
            event(log,p,day,"GAP_OPEN_BELOW_BAND_SKIPPED",row["open"],
                  "No favorable intraday fill inferred after gap under planned band")
        elif touch:
            entry=row["open"] if row["open"]<=high else high
            if not low<=entry<=high:
                raise ValueError("SIMULATED_ENTRY_OUTSIDE_PRE_REGISTERED_BAND")
            p["entry_price"]=entry;p["entry_date"]=day;p["remaining_fraction"]=1.0
            p["assumed_fill_method"]="AT_OPEN_IN_BAND" if row["open"]<=high else "LIMIT_UPPER_BAND_TOUCHED"
            p["status"]="OPEN"
            event(log,p,day,"PAPER_ENTRY_ASSUMED_ON_DAILY_OHLC",entry,
                  "Entry order assumed placed before session; actual intraday fill/order queue UNVERIFIED")
            # The same day's earlier high may have happened before entry:
            # NEVER claim T1/T2 profit from the entry candle.
            if row["high"]>=t1:
                event(log,p,day,"ENTRY_BAR_TARGET_ORDER_UNKNOWN",None,
                  "Same-bar high is not counted as post-entry profit")
            if row["close"]<stop:
                p["status"]="STOP_PENDING"
                event(log,p,day,"CLOSE_BELOW_STOP_EXIT_NEXT_OPEN_PENDING",row["close"])
        if p["status"]=="WAITING" and row["close"]<stop:
            p["status"]="CANCELLED_STOP_BEFORE_ENTRY"
            event(log,p,day,"NO_FILL_CANCELLED_STRUCTURE_BROKEN",row["close"],
                  "Never buy an expired thesis after daily close below the pre-registered structure stop")
        if p["status"]=="WAITING" and row["high"]>=t1:
            p["status"]="CANCELLED_TARGET_BEFORE_ENTRY"
            event(log,p,day,"MISSED_NO_FILL_FIRST_RESISTANCE_VISITED",t1,
                  "Price reached original first resistance before entering registered watch band; no retroactive fill")
        if p["status"]=="WAITING" and p["sessions_observed"]>=int(plan["expires_after_sessions"]):
            p["status"]="EXPIRED"
            event(log,p,day,"PAPER_PLAN_EXPIRED_NO_FILL",None,"No entry within allowed observed sessions")
        return "FILL_ASSUMED" if p["entry_date"]==day else p["status"]
    if p["status"]!="OPEN":return p["status"]
    # Targets are historical price levels, resting sell limits assumed active
    # on sessions strictly FOLLOWING the hypothetical entry session.
    if day>p["entry_date"]:
        if p["target1_date"] is None and row["high"]>=t1:
            sell(p,log,day,t1,.5,"FIRST_TARGET_HALF_UNIT_ASSUMED")
            p["target1_date"]=day
        if p["remaining_fraction"]>.01 and row["high"]>=t2:
            sell(p,log,day,t2,p["remaining_fraction"],"SECOND_TARGET_REST_UNIT_ASSUMED")
            p["target2_date"]=day
            p["status"]="CLOSED_T2"
            return "BOTH_TARGETS_RECORDED"
    if row["close"]<stop and p["remaining_fraction"]>0:
        p["status"]="STOP_PENDING"
        event(log,p,day,"CLOSE_BELOW_STOP_EXIT_NEXT_OPEN_PENDING",row["close"])
    return p["status"]

def run(plans_csv,prices_csv,ledger_json,outdir,report_day,market_scan_asof):
    date.fromisoformat(report_day)
    if market_scan_asof:date.fromisoformat(market_scan_asof)
    plans=[canonical_plan(x) for x in load_csv(plans_csv,PLANS_REQUIRED)]
    if len({x["plan_id"] for x in plans})!=len(plans):raise ValueError("DUPLICATE_REGISTERED_PLAN_ID")
    if Path(ledger_json).exists():
        ledger=json.loads(Path(ledger_json).read_text(encoding="utf-8"))
        if ledger.get("schema")!=VERSION:raise ValueError("LEDGER_SCHEMA_CHANGED")
    else:
        ledger=dict(schema=VERSION,positions={},events=[],price_scope=PRICE_SCOPE,
            real_broker_orders=False,authoritative_regular_scope=False)
    positions=ledger["positions"];events=ledger["events"]
    registered_ids={p["plan_id"] for p in plans}
    for plan in plans:
        pid=plan["plan_id"]
        if pid in positions:
            if positions[pid]["plan_sha256"]!=plan_hash(plan):
                raise ValueError("IMMUTABLE_REGISTERED_PLAN_MODIFIED:"+pid)
        else:
            positions[pid]=init_state(plan)
    # No plan deletion. Stable ledger survives future TOP2 replacement.
    if set(positions)!=registered_ids:
        raise ValueError("REGISTERED_PLAN_REMOVED_FROM_SOURCE")
    source=load_csv(prices_csv,OHLC_REQUIRED)
    per_ticker={}
    for raw in source:
        b=bar_valid(raw);symbol=b["ticker"]
        d=per_ticker.setdefault(symbol,{})
        if b["date"] in d:raise ValueError("DUPLICATE_BAR_TICKER_DATE")
        if b["date"]>report_day:raise ValueError("FUTURE_BAR_IN_CURRENT_SOURCE")
        d[b["date"]]=b
    outcomes={}
    for pid,p in positions.items():
        outcomes[pid]=update_one(p,events,per_ticker.get(p["plan"]["ticker"],{}),
                          report_day,market_scan_asof)
    # Fairly report only position marks; no capital allocation and no aggregate
    # model CAGR/win probability from two deliberately selected research names.
    summary=[]
    for pid,p in positions.items():
        entry=p["entry_price"];remaining=p["remaining_fraction"]
        close=p["last_close"]
        marked=(p["realized_net_krw_per_unit"]+
            (close*(1-SELL_COST)-entry*(1+BUY_COST))*remaining if entry and close else None)
        cost=entry*(1+BUY_COST) if entry else None
        pct=round(100*marked/cost,2) if marked is not None else None
        summary.append(dict(plan_id=pid,ticker=p["plan"]["ticker"],name=p["plan"]["name"],
          source_selection_date=p["plan"]["selection_date"],
          registered_day=p["plan"]["registered_day"],status=p["status"],
          sim_entry_date=p["entry_date"],sim_entry_price=p["entry_price"],
          last_observed_session=p["last_observed_date"],last_source_close=close,
          target1_date=p["target1_date"],target2_date=p["target2_date"],
          stop_exit_date=p["exit_date"] if p["status"]=="CLOSED_STOP" else None,
          observed_sessions_waited=p["sessions_observed"],
          remaining_fraction=remaining,sim_net_mark_to_market_pct=pct,
          next_open_exit_pending=p["status"]=="STOP_PENDING",
          fill_is_hypothetical_from_ohlc=True,
          official_regular_close_verified=False,real_trade_executed=False,
          update_status=outcomes[pid]))
    folder=Path(outdir);folder.mkdir(parents=True,exist_ok=True)
    # Durable ledger path persists across days via GitHub commit; status is
    # artifact-only and may be generated even on weekends, without mutating
    # events or fabricating a new price observation.
    dest=Path(ledger_json);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(ledger,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    with (folder/"c3_paper_events.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=[
           "event_key","plan_id","ticker","source_session","event","mode",
           "model_price_krw","details","actual_broker_fill","regular_only_verified"])
        w.writeheader();w.writerows(events)
    with (folder/"c3_paper_positions.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]))
        w.writeheader();w.writerows(summary)
    statuses=dict(Counter(p["status"] for p in positions.values()))
    event_counts=dict(Counter(e["event"] for e in events))
    factual_counts=dict(
       plan_registrations=len(positions),
       observed_entry_assumptions=sum(p["entry_date"] is not None for p in positions.values()),
       first_target_assumptions=sum(p["target1_date"] is not None for p in positions.values()),
       second_target_assumptions=sum(p["target2_date"] is not None for p in positions.values()),
       fully_closed_paper_exits=sum(p["status"] in ("CLOSED_T2","CLOSED_STOP") for p in positions.values()),
       missed_without_entry=sum(p["status"]=="CANCELLED_TARGET_BEFORE_ENTRY" for p in positions.values()),
       invalidated_before_entry=sum(p["status"]=="CANCELLED_STOP_BEFORE_ENTRY" for p in positions.values()),
       expired_without_entry=sum(p["status"]=="EXPIRED" for p in positions.values()),
       next_session_open_missing=sum(p["status"]=="STOP_OPEN_MISSED_UNVERIFIABLE" for p in positions.values()))
    status=dict(schema=VERSION,report_day_kst=report_day,
      full_market_price_asof=market_scan_asof,price_source_scope=PRICE_SCOPE,
      registered_plans=len(plans),events_total=len(events),
      status_counts=statuses,event_type_counts=event_counts,
      prospective_outcome_counts=factual_counts,
      empirical_win_probability_not_claimed=True,positions=summary,
      no_backfills_or_same_signal_day_fills=True,
      buy_cost_bps=15,sell_cost_bps=50,
      first_target_fraction=0.5,second_target_fraction=0.5,
      stop_trigger="DAILY_CLOSE_BELOW_STOP",stop_assumed_exit="NEXT_OBSERVED_TRADING_SESSION_OPEN",
      same_day_entry_target_never_counted=True,
      adjusted_pykrx_not_official_regular_certification=True,
      simulation_only_no_actual_limit_order_execution=True,
      automatic_brokerage_orders=False,buy_approved=False,orders_enabled=False)
    (folder/"c3_paper_daily_status.json").write_text(
        json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    lines=["# C3 전 종목 TOP2 가상매매 추적",f"- 보고일: {report_day} / 매칭 원본 거래일: {market_scan_asof or '미확인'}",
      f"- 등록된 가상전략: {len(plans)}개 / 누적 사건: {len(events)}개",
      "- **가상매수는 사전 등록 뒤 실제 다음 완료 일봉의 일중 가격 범위와 비교한 가정입니다. 실제 체결이 아닙니다.**",
      "- 가상 비용: 매수 0.15%, 매도 0.50%; 1차 절반·2차 잔여분; 종가 구조손절 후 다음 개장 시초가 청산 가정",
      "- 정규장 09:00~15:30 단독 데이터 검증 미완료 · 자동주문 없음",
      "","| 종목 | 상태 | 가상진입일/가격 | 최근 관측 종가 | 가상 평가손익률 |",
      "|---|---|---|---|---|"]
    for x in summary:
        lines.append(f"| {x['name']} | {x['status']} | {x['sim_entry_date'] or '-'} / {x['sim_entry_price'] or '-'} | {x['last_source_close'] or '-'} | {str(x['sim_net_mark_to_market_pct'])+'%' if x['sim_net_mark_to_market_pct'] is not None else '-'} |")
    (folder/"c3_paper_daily_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return status

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--bars",required=True)
    p.add_argument("--ledger",required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--today",required=True)
    p.add_argument("--full-market-asof",default="")
    args=p.parse_args()
    st=run(args.plans,args.bars,args.ledger,args.outdir,args.today,args.full_market_asof)
    print(json.dumps(dict(day=st["report_day_kst"],positions=st["registered_plans"],
        statuses=st["status_counts"],events=st["events_total"]),ensure_ascii=False))

if __name__=="__main__":main()
