#!/usr/bin/env python3
"""Conservative v6.15 five-session outcome audit for observed A/B *research* signals.

Daily OHLC limit touching is not a confirmed execution. Every case is a
hypothetical mutually independent signal, never an actual broker trade,
portfolio return, final buy approval, or probability estimate. Stop-first
on same-bar ambiguity. No horizon claim until five market sessions exist.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
from functools import lru_cache
from collections import Counter
from forward_ledger_v63 import read_csv,digest
from entry_opportunities_v615 import SCHEMA as PARENT

SCHEMA="C3_V615_FIVE_SESSION_SHADOW_AUDIT"
FIELDS=("asof","ticker","name","method","classification",
 "reference_first_limit","reference_structure_stop","reference_ceiling_or_hypothetical_2R",
 "next_day_limit_touched_not_a_fill","future5_sessions_complete","shadow_outcome",
 "shadow_exit_date","shadow_exit_reference","shadow_net_pct_0p5_cost",
 "same_day_path_uncertain","broker_fill_proven","profitability_proven",
 "trade_approved","orders_enabled")

def scenario(e,future):
    first=float(e["first_limit_study"])
    stop=float(e["structure_stop_study"])
    target=float(e["nearby_confirmed_overhead"] or e["scenario_target_2R_not_verified"])
    if not (0<stop<first<target):raise ValueError("V615_INVALID_ASOF_STRUCTURE")
    out=dict(asof=e["asof"],ticker=e["ticker"],name=e["name"],
      method=e["method"],classification=e["classification"],
      reference_first_limit=first,reference_structure_stop=stop,
      reference_ceiling_or_hypothetical_2R=target,
      next_day_limit_touched_not_a_fill=False,future5_sessions_complete=False,
      shadow_outcome="FIVE_SESSIONS_NOT_OBSERVED",
      shadow_exit_date="",shadow_exit_reference="",shadow_net_pct_0p5_cost="",
      same_day_path_uncertain=False,broker_fill_proven=False,
      profitability_proven=False,trade_approved=False,orders_enabled=False)
    if len(future)<5:return out
    out["future5_sessions_complete"]=True
    bars=future[:5]
    if bars[0]["Date"]<=e["asof"] or any(a["Date"]>=b["Date"] for a,b in zip(bars,bars[1:])):
        raise ValueError("V615_FORWARD_DATES_NOT_STRICT")
    if float(bars[0]["Low"])>first:
        out["shadow_outcome"]="NO_FIRST_SESSION_LIMIT_TOUCH"
        return out
    out["next_day_limit_touched_not_a_fill"]=True
    out["same_day_path_uncertain"]=True
    if float(bars[0]["Open"])<=stop:
        out["shadow_outcome"]="GAP_BELOW_STOP_TOUCH_NO_EXECUTION_PROOF"
        return out
    outcome="HELD_FIVE_DAY_MARK_TO_MARKET"
    exitbar=bars[-1]
    exitref=float(exitbar["Close"])
    for n,bar in enumerate(bars):
        lo=float(bar["Low"]);hi=float(bar["High"]);op=float(bar["Open"])
        if lo<=stop:
            outcome="STOP_FIRST_CONSERVATIVE_OHLC"
            exitbar=bar;exitref=min(op,stop) if n>0 else stop
            break
        if n==0:
            # A target touch on day one might have preceded the limit fill.
            continue
        if hi>=target:
            outcome="TARGET_AFTER_FIRST_DAY_PROXY"
            exitbar=bar;exitref=target
            break
    out.update(shadow_outcome=outcome,shadow_exit_date=exitbar["Date"],
       shadow_exit_reference=round(exitref,2),
       shadow_net_pct_0p5_cost=round(100*(exitref/first-1)-.5,3))
    return out

def calculate(v18,status,signal):
    meta=json.loads(status.read_text(encoding="utf-8"))
    if (meta.get("schema")!=PARENT or
        meta.get("trade_approved") is not False or
        meta.get("orders_enabled") is not False or
        meta.get("source_asof")!="2026-10-23" or
        meta.get("sha256",{}).get("v615_all_setups.csv")!=digest(signal.read_bytes())):
        raise ValueError("V615_FROZEN_RESEARCH_SIGNAL_SHA_OR_ASOF_INVALID")
    rows=read_csv(signal)
    if len(rows)!=meta.get("unique_event_count"):
        raise ValueError("V615_ALL_SIGNALS_COUNT_MISMATCH")
    @lru_cache(maxsize=3500)
    def history(ticker):
        p=v18/"market/prices"/(ticker+".csv")
        return read_csv(p) if p.is_file() else []
    output=[]
    for e in rows:
        if (e["trade_approved"]!="False" or e["orders_enabled"]!="False"
            or e["asof"]>meta["source_asof"] or
            e["regular_1530_price_verified"]!="False"):
            raise ValueError("V615_UNTRUSTWORTHY_INPUT_OR_BUY_FLAG")
        if not e["classification"].startswith(("A_","B_")):continue
        h=history(e["ticker"])
        if not h:raise ValueError("V615_MISSING_FORWARD_HISTORY")
        future=[r for r in h if e["asof"]<r["Date"]<=meta["source_asof"]][:5]
        output.append(scenario(e,future))
    stats=Counter(x["shadow_outcome"] for x in output)
    bcomplete=[x for x in output if x["classification"].startswith("B_")
               and x["shadow_net_pct_0p5_cost"]!=""]
    # These overlapping signal observations are not independent portfolio trades.
    avg=(round(sum(x["shadow_net_pct_0p5_cost"] for x in bcomplete)/len(bcomplete),3)
         if bcomplete else None)
    report=dict(schema=SCHEMA,parent_sha256=digest(status.read_bytes()),
      source_asof=meta["source_asof"],observations=len(output),
      A_count=sum(x["classification"].startswith("A_") for x in output),
      B_count=sum(x["classification"].startswith("B_") for x in output),
      complete_five_session_count=sum(x["future5_sessions_complete"] for x in output),
      first_day_price_touch_upper_bound=sum(x["next_day_limit_touched_not_a_fill"] for x in output),
      B_complete_5session_proxy_count=len(bcomplete),
      B_average_5session_net_pct_proxy_not_portfolio_return=avg,
      observation_counts=dict(stats),order_execution_verified=False,
      exclusive_portfolio_positions_evaluated=False,
      profit_expectancy_proven=False,trade_approved=False,orders_enabled=False,
      decision="CASH_PENDING_FORWARD_INDEPENDENT_DATA")
    return report,output

def save(out,report,rows):
    out.mkdir(parents=True,exist_ok=True)
    name="v615_shadow_five_session_cases.csv"
    with (out/name).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="raise")
        w.writeheader();w.writerows(rows)
    report["csv_sha256"]=digest((out/name).read_bytes())
    (out/"v615_shadow_five_session_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# v6.15 추가 검증 — 5거래일 진입/매도 가상 경로",
      "**실제 주문은 0건입니다.** 원본은 10/23까지 소급 수집된 일봉이고, 호가·분봉·PIT 검증은 아직 없습니다.",
      "한 종목이 중복 출현할 수 있어 아래 관찰은 독립 거래나 포트폴리오 수익률이 아닙니다.",
      "첫날 저가 도달은 체결 확인이 아닙니다. 당일 고저 순서는 불명확하며 손절을 먼저 처리합니다.",
      "B 돌파 유형은 목표가격 자체가 검증되지 않은 2R 가설입니다.", "",
      "| 일자 | 종목 | 종류 | 5일결과 분류 | 비용후 가상 순수익률 |",
      "|---|---|---|---|---:|"]
    for x in rows:
        v=(str(x["shadow_net_pct_0p5_cost"])+"%" if x["shadow_net_pct_0p5_cost"]!="" else "산정 불가")
        lines.append("| {} | {} | {} | {} | {} |".format(
            x["asof"],x["name"],x["classification"][0],
            x["shadow_outcome"],v))
    lines+=["","**검증 기준:** 1차는 다음 시장일 지정가만 가정하고, 가격 미도달은 미체결. 같은 일봉에서 손절과 목표를 동시에 볼 때 손절 우선. 5시장일 미확보는 손익산정 금지.",
       "**결론:** 위 수치로 매수승인을 활성화하거나 1.5R 실전 규칙을 확정하지 않습니다."]
    (out/"v615_shadow_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--v18",type=Path,required=True)
    a.add_argument("--status",type=Path,required=True)
    a.add_argument("--signals",type=Path,required=True)
    a.add_argument("--outdir",type=Path,required=True)
    q=a.parse_args()
    report,rows=calculate(q.v18,q.status,q.signals)
    save(q.outdir,report,rows)
    print("V615_FIVE_SESSION_OUTCOMES",json.dumps(report,ensure_ascii=False))

if __name__=="__main__":main()
