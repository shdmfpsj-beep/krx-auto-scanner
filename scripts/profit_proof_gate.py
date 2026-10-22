#!/usr/bin/env python3
"""C3 profit-proof checkpoint: verify completed *prospective* paper performance.

Not a guaranteed return or a live-trade signal. Validate journal identity,
account cash arithmetic and risk; test additional friction, chronology and
cluster-aware uncertainty. Zero backfilled trades and no chosen winner based
on past results. The result always leaves new trades as CASH until a separate
market/current-account approval gate exists.
"""
import argparse,json,math,random,statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from shadow_trade_audit import VERSION, ROUNDTRIP_COST_PCT

SCHEMA="c3_profit_evidence_gate_v1"
EXTRA_ROUNDTRIP_FRICTION_PCT=0.20
MIN_POSITIONS=30
MIN_DISTINCT_SIGNAL_DAYS=20
MIN_HOLDOUT=8
MIN_SPAN_DAYS=60
BOOTSTRAPS=1200

def numeric(x):
    if isinstance(x,bool):return None
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def day(x):
    try:return date.fromisoformat(str(x))
    except (ValueError,TypeError):return None

def identity(x):
    if not isinstance(x,dict):return None
    d=day(x.get("signal_date"));t=x.get("ticker")
    if (x.get("plan_version")!=VERSION or not d or not isinstance(t,str)
            or len(t)!=6 or not t.isdigit()):return None
    return (str(d),t,VERSION)

def lineage(signals,results):
    sources={}
    defects=[]
    for s in signals:
        k=identity(s)
        if not k:
            defects.append("INVALID_OR_BACKFILLED_SIGNAL_ID")
            continue
        if k in sources:
            defects.append("DUPLICATE_SIGNAL_ID")
            continue
        sources[k]=s
    observed=set()
    closed=[]
    pending=0
    skips=0
    for r in results:
        k=identity(r)
        if not k or k not in sources:
            defects.append("RESULT_NOT_IN_LOCKED_SIGNAL_LEDGER")
            continue
        if k in observed:
            defects.append("DUPLICATE_OUTCOME_ID")
            continue
        observed.add(k)
        s=sources[k]
        if any(str(r.get(field))!=str(s.get(field)) for field in
               ("signal_close","stop_reference","no_chase_reference","prior_high")):
            defects.append("RESULT_CHANGED_LOCKED_SIGNAL_PARAMETERS")
            continue
        status=r.get("status")
        if status=="CLOSED":
            ret=numeric(r.get("net_return_pct"))
            entry=numeric(r.get("next_open_entry"))
            exit_=numeric(r.get("exit_price"))
            hold=r.get("hold_sessions")
            if (ret is None or entry is None or exit_ is None or
                    entry<=0 or exit_<=0 or type(hold)!=int or
                    not 1<=hold<=5):
                defects.append("CLOSED_RESULT_MISSING_EXECUTION")
                continue
            expected=100*(exit_/entry-1)-ROUNDTRIP_COST_PCT
            if abs(expected-ret)>0.05:
                defects.append("CLOSED_RESULT_NET_ARITHMETIC_MISMATCH")
                continue
            closed.append(r)
        elif isinstance(status,str) and status.startswith("SKIP_"):
            skips+=1
        elif isinstance(status,str) and status.startswith(("OPEN_","PENDING_","MISSING_")):
            pending+=1
        else:
            defects.append("UNKNOWN_OUTCOME_STATUS")
    # An absent result can be pending, but cannot count as a profitable fill.
    pending+=len(set(sources)-observed)
    return closed,dict(locked_signals=len(sources),completed=len(closed),
        skips=skips,pending_or_missing=pending,
        integrity_defects=sorted(set(defects)),lineage_integrity=not defects)

def check_account(account,signals,closed=()):
    issues=[]
    if not isinstance(account,dict) or account.get("account_type")!=(
       "SYNTHETIC_PAPER_ACCOUNT_NOT_USER_BALANCE"):
        return ["ACCOUNT_SOURCE_MISSING_OR_WRONG"]
    if account.get("integrity")!="OK" or not account.get("research_valid"):
        issues.append("ACCOUNT_SESSION_OR_PRICE_INTEGRITY_UNVERIFIED")
    approved_ids={(s.get("signal_date"),s.get("ticker")) for s in signals
                  if identity(s)}
    cash=numeric(account.get("starting_capital_krw"))
    if cash is None or cash<=0:return ["ACCOUNT_START_CASH_INVALID"]
    verified_closed={(x["signal_date"],x["ticker"]):x for x in closed}
    completed=[]
    last_exit=None
    wins=0
    for t in account.get("trades",[]):
        if (t.get("signal_date"),t.get("ticker")) not in approved_ids:
            issues.append("ACCOUNT_TRADE_NOT_LOCKED_SIGNAL")
            continue
        entry=numeric(t.get("entry_krw"));sell=numeric(t.get("exit_krw"))
        pnl=numeric(t.get("realized_pnl_krw"))
        fee=numeric(t.get("simulated_cost_each_side_pct"))
        prior=numeric(t.get("entry_cash_before_krw"))
        n=t.get("shares")
        if (type(n)!=int or n<=0 or not entry or not sell or
            pnl is None or fee is None or prior is None or not
            day(t.get("entry_date")) or not day(t.get("exit_date")) or
            not day(t.get("signal_date"))):
            issues.append("ACCOUNT_TRADE_INCOMPLETE")
            continue
        if not(day(t["signal_date"])<day(t["entry_date"])<=day(t["exit_date"])):
            issues.append("ACCOUNT_NONCHRONOLOGICAL_EXECUTION")
        if last_exit and (day(t["signal_date"])<last_exit or
                          day(t["entry_date"])<=last_exit):
            issues.append("ACCOUNT_OVERLAPPING_POSITIONS")
        source=verified_closed.get((t.get("signal_date"),t.get("ticker")))
        if source is None:
            issues.append("ACCOUNT_TRADE_NO_COMPLETED_FORWARD_EVALUATION")
        elif (abs(entry-source["next_open_entry"])>.011 or
              abs(sell-source["exit_price"])>.011 or
              t.get("exit_reason")!=source.get("exit_reason")):
            issues.append("ACCOUNT_PRICES_OR_EXIT_NOT_FROM_LOCKED_OUTCOME")
        last_exit=day(t["exit_date"])
        if abs(prior-cash)>max(1.5,cash*.00001):
            issues.append("ACCOUNT_CASH_CHAIN_BROKEN")
        inferred=n*(sell*(1-fee/100)-entry*(1+fee/100))
        if abs(inferred-pnl)>max(3,n*.035):
            issues.append("ACCOUNT_REALISED_PNL_ARITHMETIC_MISMATCH")
        cost=n*entry*(1+fee/100)
        if cost>prior+.5:issues.append("ACCOUNT_CAPITAL_OVERSPEND")
        planned=numeric(t.get("planned_risk_krw"))
        budget=numeric(account.get("risk_budget_per_trade_pct"))
        if (planned is None or budget is None or budget<=0 or
                planned>prior*budget/100+max(1,prior*.00001)):
            issues.append("ACCOUNT_RISK_BUDGET_EXCEEDED")
        cash=prior+pnl
        wins+=pnl>0
        completed.append(t)
    total=numeric(account.get("ending_realised_equity_krw"))
    if total is None or abs(total-cash)>max(3,len(completed)*.2):
        issues.append("ACCOUNT_FINAL_EQUITY_ARITHMETIC_MISMATCH")
    if account.get("traded_positions")!=len(completed):
        issues.append("ACCOUNT_TRADE_COUNT_MISMATCH")
    if account.get("winning_positions")!=wins:
        issues.append("ACCOUNT_WIN_COUNT_MISMATCH")
    reported_return=numeric(account.get("realised_return_pct"))
    expected_return=100*(cash/float(account["starting_capital_krw"])-1)
    if reported_return is None or abs(reported_return-expected_return)>.015:
        issues.append("ACCOUNT_REALIZED_PERCENT_ARITHMETIC_MISMATCH")
    marks=account.get("equity_marks") or []
    if not marks:
        issues.append("ACCOUNT_MARK_TO_MARKET_PATH_UNVERIFIABLE")
    else:
        # An exit equity mark must match the cash ledger immediately after
        # that trade, not just reproduce a self-reported MDD percentage.
        for t in completed:
            matching=[m for m in marks if m.get("phase")=="EXIT" and
                       m.get("date")==t.get("exit_date") and
                       m.get("ticker")==t.get("ticker")]
            expected=t["entry_cash_before_krw"]+t["realized_pnl_krw"]
            if (len(matching)!=1 or
                    numeric(matching[0].get("equity_krw")) is None or
                    abs(numeric(matching[0]["equity_krw"])-expected)>2):
                issues.append("ACCOUNT_EXIT_EQUITY_MARK_NOT_IN_CASH_LEDGER")
        peak=float(account["starting_capital_krw"])
        mdd=0.
        previous_day=None
        for m in sorted(marks,key=lambda x:(str(x.get("date","")),str(x.get("phase","")))):
            d=day(m.get("date"))
            equity=numeric(m.get("equity_krw"))
            if not d or equity is None or equity<0 or (previous_day and d<previous_day):
                issues.append("ACCOUNT_INVALID_EQUITY_MARK")
                continue
            peak=max(peak,equity)
            mdd=max(mdd,100*(peak-equity)/peak)
            previous_day=d
        reported_mdd=numeric(account.get("mark_to_market_mdd_pct"))
        if reported_mdd is None or abs(reported_mdd-mdd)>.02:
            issues.append("ACCOUNT_MARK_TO_MARKET_MDD_MISMATCH")
    return sorted(set(issues))

def bootstrap_lower_by_date(closed):
    """Bootstrap blocks = signal day, not independent simultaneous tickers."""
    groups=defaultdict(list)
    for t in closed:
        groups[t["signal_date"]].append(
            numeric(t["net_return_pct"])-EXTRA_ROUNDTRIP_FRICTION_PCT)
    dates=sorted(groups)
    if len(dates)<2:return None
    rng=random.Random(20261022)
    samples=[]
    for _ in range(BOOTSTRAPS):
        observed=[]
        for _ in dates:
            observed.extend(groups[dates[rng.randrange(len(dates))]])
        samples.append(statistics.mean(observed))
    samples.sort()
    return round(samples[int(.05*(len(samples)-1))],3)

def audit(signals,results,account,ab=None):
    closed,journal=lineage(signals,results)
    issues=list(journal["integrity_defects"])+check_account(account,signals,closed)
    samples=sorted(closed,key=lambda x:(x["signal_date"],x["ticker"]))
    n=len(samples)
    span=(day(samples[-1]["signal_date"])-day(samples[0]["signal_date"])).days if n>=2 else 0
    distinct=len({x["signal_date"] for x in samples})
    holdout_n=max(MIN_HOLDOUT,math.ceil(n*.25))
    early=samples[:-holdout_n] if n>holdout_n else []
    late=samples[-holdout_n:] if n>=holdout_n else []
    def average(xs,extra=0):
        return round(sum(numeric(x["net_return_pct"])-extra for x in xs)/len(xs),3) if xs else None
    avg=average(samples)
    stressed=average(samples,EXTRA_ROUNDTRIP_FRICTION_PCT)
    holdout=average(late,EXTRA_ROUNDTRIP_FRICTION_PCT)
    lower=bootstrap_lower_by_date(samples) if distinct>=MIN_DISTINCT_SIGNAL_DAYS else None
    mdd=numeric(account.get("mark_to_market_mdd_pct")) if isinstance(account,dict) else None
    no_issues=not issues
    sample_ok=(n>=MIN_POSITIONS and distinct>=MIN_DISTINCT_SIGNAL_DAYS
               and span>=MIN_SPAN_DAYS and len(late)>=MIN_HOLDOUT)
    stress_ok=(stressed is not None and stressed>0 and
               holdout is not None and holdout>0 and
               lower is not None and lower>0)
    account_ok=(mdd is not None and 0<=mdd<=15 and
               isinstance(account,dict) and account.get("traded_positions",0)>=MIN_POSITIONS)
    # Historical rule discovery/tuning invalidates independent statistical
    # certification even if this retrospective diagnostic looks good.
    reasons=sorted(set(issues+
      ([] if sample_ok else ["MIN_SAMPLE_OR_SPAN_NOT_MET"])+
      ([] if stress_ok else ["STRESS_OR_HOLDOUT_EXPECTANCY_NOT_POSITIVE_OR_UNTESTED"])+
      ([] if account_ok else ["ACCOUNT_DRAWDOWN_OR_POSITION_SAMPLE_NOT_VALIDATED"])))
    status=("AUDIT_INTEGRITY_FAILURE" if not no_issues
        else "INSUFFICIENT_PROSPECTIVE_EVIDENCE" if not sample_ok
        else "PAPER_EDGE_NOT_ROBUST" if not(stress_ok and account_ok)
        else "PROVISIONAL_PAPER_EDGE_NOT_LIVE_OR_OOS_PROVEN")
    return dict(schema=SCHEMA,signal_lineage=journal,
      completed_shadow_trades=n,distinct_signal_dates=distinct,span_calendar_days=span,
      paper_mean_net_return_pct=avg,
      paper_mean_after_additional_20bps_cost_pct=stressed,
      last_quarter_chronological_trade_mean_stressed_pct=holdout,
      date_cluster_bootstrap_5pct_lower_mean_stressed_pct=lower,
      paper_one_slot_mdd_pct=mdd,
      sample_sufficiency_met=sample_ok,
      integrity_pass=no_issues,
      profit_proof_status=status,
      blockers=reasons,
      cost_sensitivity_not_a_broker_quote=True,
      bootstrap_not_independent_oos_or_live_validation=True,
      win_rate_is_not_profit_guarantee=True,
      statistical_profit_guarantee=False,
      real_account_profit_verified=False,
      final_80_trade_score_verified=False,final_80_trade_score_verified=False,final_85_trade_score_verified=False,
      orders_enabled=False,trade_approved=False,decision="CASH")

def markdown(r):
    fmt=lambda x: "—" if x is None else str(x)
    return "\n".join(["# C3 전향적 수익성 실증 게이트","",
       "**신규매수 CASH — 1~5거래일 수익 보장은 불가능합니다.**","",
       "| 검증 지표 | 결과 |","|---|---:|",
       "| 사전 기록 평가완료 건수 | "+str(r["completed_shadow_trades"])+" |",
       "| 서로 다른 신호 날짜 | "+str(r["distinct_signal_dates"])+" |",
       "| 거래당 모의 평균 순수익률 | "+fmt(r["paper_mean_net_return_pct"])+"% |",
       "| 왕복 비용 0.20%p 추가 후 평균 | "+fmt(r["paper_mean_after_additional_20bps_cost_pct"])+"% |",
       "| 최근 25% 신호의 추가비용 적용 평균 | "+fmt(r["last_quarter_chronological_trade_mean_stressed_pct"])+"% |",
       "| 신호 날짜 묶음 재표본 추정 하위 5% 평균 | "+fmt(r["date_cluster_bootstrap_5pct_lower_mean_stressed_pct"])+"% |",
       "| C3 한 종목 가상계좌 MDD | "+fmt(r["paper_one_slot_mdd_pct"])+"% |",
       "| 연구 판정 | "+r["profit_proof_status"]+" |","",
       "누락·오염: "+(", ".join(r["blockers"]) if r["blockers"] else "산술·연속성 내부 점검 통과"),"",
       "동일 날짜 섹터 종목의 상관관계를 일부 고려하도록 날짜별 묶음 표본추출을 사용합니다.",
       "최근 25% 구간 검사는 시간순 진단이며, 전략 선택과 독립된 외부 검증이 아닙니다.",
       "완료된 모의매매만 집계하고 미체결·스킵·미완료를 수익으로 계산하지 않습니다.",
       "가상계좌 수익·MDD는 실제 키움 계좌의 체결·성과와 무관합니다.",
       "어떤 연구 판정도 실제 BUY 권한이나 수익 보장을 생성하지 않습니다.",""])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    def read(name,default):
        f=a.root/name
        try:return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else default
        except (ValueError,OSError):return default
    signals=read("shadow_signals.json",[])
    results=read("shadow_results.json",[])
    account=read("c3_one_slot_equity.json",{})
    if not isinstance(signals,list):signals=[]
    if not isinstance(results,list):results=[]
    if not isinstance(account,dict):account={}
    res=audit(signals,results,account)
    a.root.mkdir(parents=True,exist_ok=True)
    (a.root/"profit_proof_gate.json").write_text(
       json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.root/"profit_proof_mobile.md").write_text(markdown(res),encoding="utf-8")
    compact=a.root/"sector_first_compact_mobile.md"
    if compact.is_file():
        marker="## ⑦ C3 실증 수익성 게이트"
        old=compact.read_text(encoding="utf-8").split("\n"+marker)[0].rstrip()
        compact.write_text(old+"\n\n"+marker+"\n"+
              "- 완료: "+str(res["completed_shadow_trades"])+
              "건 / 추가 왕복비용 반영 평균: "+
              str(res["paper_mean_after_additional_20bps_cost_pct"])+
              "%\n- 실증 상태: "+res["profit_proof_status"]+
              "\n- 수익보장 없음. 신규매수: CASH.\n",encoding="utf-8")
    print(json.dumps(dict(status=res["profit_proof_status"],
           closed=res["completed_shadow_trades"],
           integrity=res["integrity_pass"],decision="CASH"),ensure_ascii=False))
if __name__=="__main__":main()
