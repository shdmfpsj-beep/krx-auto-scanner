#!/usr/bin/env python3
"""C3 one-position simulated equity, driven ONLY by prospectively locked signals.

Key differences from per-signal results:
- At most one selected stock can be held at a time.
- On each signal date, choose the highest *previously recorded* research rank
  before seeing the next session. Do not substitute the next-ranked stock when
  that chosen stock gaps up or fails the capital gate.
- Enter on the following completed exchange session OPEN and exit by the
  existing stop-first 5-session paper evaluator. No account credentials.
- Determine integer shares using BOTH affordable cash and a *portfolio risk*
  budget, NOT an arbitrary 1% stock-price stop.
- Gross cash accounting applies 0.2% modeled entry + 0.2% modeled exit costs.
- Portfolio mark-to-market includes pre-exit daily closes while held. Not
  transaction-level actual returns, and not an executable trading engine.
"""
import argparse,json,math
from collections import defaultdict
from datetime import date
from pathlib import Path
from shadow_trade_audit import (
    VERSION,HORIZON,ROUNDTRIP_COST_PCT,datestr,finite,evaluate,
    price_history,market_session_calendar)

SCHEMA="c3_one_position_paper_v1"
DEFAULT_CAPITAL=1000000
RISK_BUDGET_PCT=2.0
COST_EACH_SIDE_PCT=ROUNDTRIP_COST_PCT/2

def score(signal):
    try:
        v=float(signal.get("research_proxy_index"))
        return v if math.isfinite(v) else -1
    except (TypeError,ValueError):
        return -1

def is_signal(s):
    return (isinstance(s,dict) and s.get("plan_version")==VERSION and
            datestr(s.get("signal_date")) is not None and
            isinstance(s.get("ticker"),str) and
            len(s["ticker"])==6 and s["ticker"].isdigit())

def choose_one_per_day(signals):
    """Lock selection by signal-day research rank, never future fill outcome."""
    groups=defaultdict(list)
    for s in signals:
        if is_signal(s):
            groups[s["signal_date"]].append(s)
    return [(d,sorted(choices,key=lambda x:(-score(x),x["ticker"]))[0],
              len(choices)) for d,choices in sorted(groups.items())]

def simulate(signals, prices, sessions, initial_cash=DEFAULT_CAPITAL,
             risk_budget_pct=RISK_BUDGET_PCT, fee_side_pct=COST_EACH_SIDE_PCT):
    if not isinstance(initial_cash,(float,int)) or initial_cash<=0:
        raise ValueError("INITIAL_CASH_MUST_BE_POSITIVE")
    if not (0<risk_budget_pct<=5 and 0<=fee_side_pct<=1):
        raise ValueError("INVALID_RISK_OR_COST_ASSUMPTIONS")
    if not sessions or sorted(set(sessions))!=list(sessions):
        return dict(schema=SCHEMA,decision="CASH",research_valid=False,
            integrity="NO_VALID_COMPLETE_KRX_SESSION_CALENDAR",
            starting_capital_krw=initial_cash,ending_realised_equity_krw=None,
            realised_pnl_krw=None,realised_return_pct=None,
            mark_to_market_mdd_pct=None,traded_positions=0,
            winning_positions=0,blocked_simultaneous_candidates=0,
            risk_budget_per_trade_pct=risk_budget_pct,
            cost_each_side_pct=fee_side_pct,
            trades=[],skips=[],equity_marks=[],blocked_signals=0)
    cash=float(initial_cash)
    cash_at_last_exit=float(initial_cash)
    ledger=[]
    skips=[]
    equity=[dict(date=sessions[0],equity_krw=round(cash,2),
                 phase="INITIAL_CASH")]
    blocked=0
    exit_session=None
    unresolved=None
    selected=choose_one_per_day(signals)
    for signal_day,signal,simultaneous in selected:
        if signal_day not in sessions:
            unresolved="SIGNAL_DATE_NOT_IN_VALIDATED_CALENDAR"
            skips.append(dict(signal_date=signal_day,ticker=signal["ticker"],
                reason=unresolved))
            break
        if exit_session is not None and signal_day<exit_session:
            blocked+=simultaneous
            skips.append(dict(signal_date=signal_day,ticker=signal["ticker"],
              reason="C3_ALREADY_HOLDING_ONE_STOCK",
              candidate_count_ignored=simultaneous))
            continue
        ticker=signal["ticker"]
        bars=prices.get(ticker,[])
        result=evaluate(signal,bars,market_sessions=sessions,
                        cost_pct=fee_side_pct*2)
        if result["status"]!="CLOSED":
            skips.append(dict(signal_date=signal_day,ticker=ticker,
                              reason=result["status"],
                              rejected_alternative_signals=simultaneous-1))
            if result["status"].startswith(("PENDING_","OPEN_","MISSING_")):
                unresolved=result["status"]
                # Unknown open/exits: MUST NOT simulate later trades as if free.
                break
            continue
        later=[day for day in sessions if day>signal_day]
        held=result.get("hold_sessions")
        if not isinstance(held,int) or held<1 or held>HORIZON or len(later)<held:
            unresolved="INCONSISTENT_EXIT_SESSION"
            break
        opened=later[0]
        closed=later[held-1]
        entry=finite(result.get("next_open_entry"))
        sold=finite(result.get("exit_price"))
        stop=finite(signal.get("stop_reference"))
        if not(entry and sold and stop and entry>stop):
            unresolved="INCONSISTENT_EXECUTION_PRICE"
            break
        fee=fee_side_pct/100
        risk_per_share=entry-stop+fee*(entry+stop)
        risk_money=cash*risk_budget_pct/100
        affordable=math.floor(cash/(entry*(1+fee)))
        risk_cap=math.floor(risk_money/risk_per_share)
        shares=max(0,min(affordable,risk_cap))
        if shares<1:
            skips.append(dict(signal_date=signal_day,ticker=ticker,
              reason="CAPITAL_GATE_LESS_THAN_ONE_SHARE",
              entry_reference=round(entry,2),cash_before_krw=round(cash,2),
              affordable_shares=affordable,risk_capped_shares=risk_cap))
            continue
        initial=cash
        cost=shares*entry*(1+fee)
        cash-=cost
        # Daily mark-to-market conservatively includes hypothetical sell fee.
        dated={b["date"]:b for b in bars}
        for day in later[:held-1]:
            bar=dated.get(day)
            if not bar:
                unresolved="MISSING_MARK_TO_MARKET_SESSION"
                break
            estimate=cash+shares*bar["close"]*(1-fee)
            equity.append(dict(date=day,equity_krw=round(estimate,2),
                               phase="HOLDING_MARK_TO_MARKET",ticker=ticker))
        if unresolved:
            break
        cash+=shares*sold*(1-fee)
        equity.append(dict(date=closed,equity_krw=round(cash,2),
                           phase="EXIT",ticker=ticker))
        ledger.append(dict(signal_date=signal_day,ticker=ticker,
              research_rank=score(signal),simultaneous_candidates=simultaneous,
              entry_date=opened,exit_date=closed,
              shares=shares,entry_krw=round(entry,2),
              exit_krw=round(sold,2),structure_stop_krw=round(stop,2),
              entry_cash_before_krw=round(initial,2),
              planned_risk_krw=round(shares*risk_per_share,2),
              realized_pnl_krw=round(cash-initial,2),
              realized_net_pct_on_initial_cash=round(100*(cash/initial-1),3),
              simulated_cost_each_side_pct=fee_side_pct,
              exit_reason=result.get("exit_reason")))
        exit_session=closed
        cash_at_last_exit=cash
    # Only completed-account results can be reported as realised.
    peak=float(initial_cash)
    mdd=0.0
    for e in sorted(equity,key=lambda x:(x["date"],x["phase"])):
        mark=e["equity_krw"]
        peak=max(peak,mark)
        mdd=max(mdd,100*(peak-mark)/peak)
    realised=[trade["realized_pnl_krw"] for trade in ledger]
    filled=len(ledger)
    return dict(schema=SCHEMA,decision="CASH",
      research_valid=(unresolved is None),integrity=unresolved or "OK",
      account_type="SYNTHETIC_PAPER_ACCOUNT_NOT_USER_BALANCE",
      starting_capital_krw=round(initial_cash,2),
      ending_realised_equity_krw=round(cash_at_last_exit,2),
      realised_pnl_krw=round(cash_at_last_exit-initial_cash,2),
      realised_return_pct=round(100*(cash_at_last_exit/initial_cash-1),3),
      mark_to_market_mdd_pct=round(mdd,3),
      risk_budget_per_trade_pct=risk_budget_pct,
      cost_each_side_pct=fee_side_pct,
      traded_positions=filled,
      winning_positions=sum(p>0 for p in realised),
      blocked_simultaneous_candidates=blocked,
      evaluated_signal_days=len(selected),
      research_sample_sufficient=filled>=30 and unresolved is None,
      statistically_verified_profit=False,
      trades=ledger,skips=skips,equity_marks=equity)

def render(report):
    lines=["# C3 1종목 집중형 모의 계좌 성과","",
      "**연구용 가상 계좌이며 실제 C3 잔고·매매 수익이 아닙니다.**",
      "**현재 신규매수 승인: CASH**","",
      "| 항목 | 결과 |","|---|---:|",
      f"| 시작 가상자금 | {report.get('starting_capital_krw','—'):,}원 |",
      f"| 완료된 거래 | {report.get('traded_positions',0)}건 |"]
    for label,key,suffix in [
        ("실현 모의 순수익","realised_pnl_krw","원"),
        ("실현 모의 수익률","realised_return_pct","%"),
        ("보유 중 평가액 반영 최대낙폭","mark_to_market_mdd_pct","%"),
        ("기존 포지션 때문에 건너뛴 후보","blocked_simultaneous_candidates","건")]:
        value=report.get(key)
        lines.append(f"| {label} | {value if value is not None else '—'}{suffix if value is not None else ''} |")
    lines.extend(["","자료 상태: "+str(report.get("integrity","UNKNOWN")),
      f"가정: 가상 초기자금 {report.get('starting_capital_krw','—')}원, "
      f"거래당 계좌 계획위험 {report.get('risk_budget_per_trade_pct','—')}%, "
      f"편도 비용 {report.get('cost_each_side_pct','—')}%.",
      "계획 위험은 **주가 손절폭이 아닙니다.** 수량 제한에 쓰이는 계좌 손실 예산입니다.",
      "다른 종목 보유 시 중복 진입하지 않고, 한 주도 매수할 수 없으면 현금 유지.",
      "종가 평가 기준 최대낙폭은 일중 최저 평가액 및 급락 갭의 실시간 손실을 완전히 반영하지 못합니다.",
      "데이터가 끊기면 이후 거래 성과를 함부로 계산하지 않습니다.",
      "현재 C3 실보유 상태 및 실제 주문가능금액은 별도 확인이 필요합니다.",
      "모의 신호가 30건 미만이거나 시장 국면 검증 전이면 투자 우위를 입증한 것이 아닙니다.",""])
    return "\n".join(lines)

def run_cli():
    parser=argparse.ArgumentParser()
    parser.add_argument("--signals",type=Path,default=Path("output/shadow_signals.json"))
    parser.add_argument("--history",type=Path,default=Path("inputs/evidence"))
    parser.add_argument("--out",type=Path,default=Path("output"))
    parser.add_argument("--initial-cash",type=float,default=DEFAULT_CAPITAL)
    parser.add_argument("--risk-budget-pct",type=float,default=RISK_BUDGET_PCT)
    a=parser.parse_args()
    try:
        data=json.loads(a.signals.read_text(encoding="utf-8")) if a.signals.is_file() else []
    except (ValueError,OSError):
        data=[]
    signals=data if isinstance(data,list) else []
    tickers={s.get("ticker") for s in signals if is_signal(s)}
    prices=price_history(a.history,tickers)
    calendar=market_session_calendar(a.history)
    result=simulate(signals,prices,calendar,a.initial_cash,a.risk_budget_pct)
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"c3_one_slot_equity.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.out/"c3_one_slot_mobile.md").write_text(render(result),encoding="utf-8")
    # Make the daily report useful on an Android screen: keep the research
    # account paragraph below its sector TOP3 / TOP5 setup and A/B comparison.
    compact=a.out/"sector_first_compact_mobile.md"
    if compact.is_file():
        marker="## ⑥ C3 1종목 집중 가상 계좌"
        previous=compact.read_text(encoding="utf-8").split("\n"+marker)[0].rstrip()
        stats=[
            "",marker,"",
            "- 가상 초기자금 1,000,000원 (실제 C3 잔고와 무관)",
            "- 완료 거래 "+str(result.get("traded_positions",0))+"건 / 보유로 배제한 후보 "+
              str(result.get("blocked_simultaneous_candidates",0))+"건",
            "- 가상 실현 순수익 "+(
                str(result["realised_pnl_krw"])+"원" if result.get("research_valid")
                and result.get("traded_positions") else "미집계"),
            "- 계좌 평가 최대낙폭(MDD) "+(
                str(result["mark_to_market_mdd_pct"])+"%" if result.get("research_valid")
                and result.get("traded_positions") else "미집계"),
            "- 자료 검증: "+str(result.get("integrity","UNKNOWN")),
            "- 실제 계좌 운용 성과 또는 신규매수 신호 아님 (CASH)",""]
        compact.write_text(previous+"\n"+"\n".join(stats),encoding="utf-8")
    print(json.dumps({k:result.get(k) for k in ("integrity","traded_positions",
        "realised_pnl_krw","realised_return_pct","mark_to_market_mdd_pct")},ensure_ascii=False))

if __name__=="__main__":
    run_cli()
