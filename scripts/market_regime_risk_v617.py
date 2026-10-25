#!/usr/bin/env python3
"""v6.17 retrospective market risk overlay: never force BUY from watch candidates.

Predeclared KOSPI200 ETF 069500 completed daily prices are a BROAD MARKET
PROXY, not a verified KOSPI/KOSDAQ index and not enough for KOSDAQ authorization.
Same-day asof-only momentum/MA checks, fixed thresholds, 5-session shadow
outcomes inherited unchanged from the v6.16 frozen artifact.
No live broker, regular-session-only, PIT fundamentals, or account access.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics
from pathlib import Path
from collections import Counter,defaultdict
from forward_ledger_v63 import read_csv,digest

SCHEMA="C3_V617_MARKET_CRASH_GATE_AUDIT_READ_ONLY"
V616="C3_V616_PREDECLARED_ENTRY_TOURNAMENT_READ_ONLY"
FIELDS=("asof","etf_069500_close","etf_069500_sma20","etf_069500_ret1_pct",
        "etf_069500_ret3_pct","etf_069500_ret5_pct","risk_mode",
        "reason","approved_live_buy","orders_enabled")
SUMMARY=("mode","baseline_5d_matured_price_touch_events",
 "baseline_5d_proxy_pnl_count","baseline_proxy_mean_net_pct",
 "green_signal_count","green_5d_complete_price_touch_events",
 "green_5d_proxy_pnl_count","green_5d_proxy_avg_net_pct",
 "red_signal_count","amber_signal_count","approved_live_buys")

def finite(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def classify(close,ma20,ret1,ret3,ret5):
    """Fixed, as-of-only risk policy. No profitability or 80-point score."""
    vs=(close,ma20,ret1,ret3,ret5)
    if any(v is None or not math.isfinite(v) for v in vs) or close<=0 or ma20<=0:
        return "RED_UNVERIFIED_DATA","MISSING_ASOF_MARKET_EVIDENCE"
    if close<ma20 or ret3<=-3.0 or ret1<=-3.0:
        return "RED_MARKET_RISK_OFF","BELOW_20MA_OR_SHARP_RECENT_DECLINE"
    if ret1<0 or ret3<0 or ret5< -1.5:
        return "AMBER_CONFIRMATION_WAIT","SHORT_TERM_MOMENTUM_NOT_CONFIRMED"
    return "GREEN_RESEARCH_ONLY","ABOVE_20MA_WITH_NO_NEGATIVE_RECENT_MOMENTUM"

def market_asof(v18,expected):
    path=v18/"market/etf_prices/069500.csv"
    if not path.is_file():raise ValueError("V617_KOSPI200_PROXY_ARCHIVE_UNAVAILABLE")
    bars=read_csv(path)
    if len(bars)<120 or bars[-1]["Date"]!=expected:
        raise ValueError("V617_PROXY_ARCHIVE_STALE_NOT_ASOF_OCT23")
    if any(a["Date"]>=b["Date"] for a,b in zip(bars,bars[1:])):
        raise ValueError("V617_NONCHRONOLOGICAL_ETF_PRICES")
    out={}
    for j in range(20,len(bars)):
        b=bars[j];c=finite(b["Close"])
        prev=finite(bars[j-1]["Close"])
        c3=finite(bars[j-3]["Close"])
        c5=finite(bars[j-5]["Close"])
        ma20=sum(finite(x["Close"]) for x in bars[j-19:j+1])/20
        if any(x is None or x<=0 for x in (c,prev,c3,c5,ma20)):
            raise ValueError("V617_INVALID_DAILY_MARKET_INPUT")
        d=b["Date"]
        ret1=100*(c/prev-1);ret3=100*(c/c3-1);ret5=100*(c/c5-1)
        gate,reason=classify(c,ma20,ret1,ret3,ret5)
        out[d]=dict(asof=d,etf_069500_close=round(c,2),
          etf_069500_sma20=round(ma20,2),
          etf_069500_ret1_pct=round(ret1,3),
          etf_069500_ret3_pct=round(ret3,3),
          etf_069500_ret5_pct=round(ret5,3),
          risk_mode=gate,reason=reason,
          approved_live_buy=False,orders_enabled=False)
    return out,digest(path.read_bytes())

def evaluate(v18,statusfile,casesfile):
    status=json.loads(statusfile.read_text(encoding="utf-8"))
    if (status.get("schema")!=V616 or
        status.get("daily_price_source_last_day")!="2026-10-23"
        or status.get("parent_signal_sha256")=="" or
        status.get("trade_approved") is not False or
        status.get("orders_enabled") is not False or
        status.get("artifacts_sha256",{}).get("v616_all_entry_modes.csv")!=
           digest(casesfile.read_bytes())):
        raise ValueError("V617_V616_ASOF_SHA_OR_NO_BUY_POLICY_INVALID")
    cases=read_csv(casesfile)
    if len(cases)!=status.get("study_candidates"):
        raise ValueError("V617_MODE_CASES_INCOMPLETE")
    if any(q["live_trade_approved"]!="False" or q["orders_enabled"]!="False"
           or q["asof"]>"2026-10-23" for q in cases):
        raise ValueError("V617_UNEXPECTED_REAL_BUY_OR_FUTURE_STOCK_DATA")
    proxy,marketsha=market_asof(v18,"2026-10-23")
    dates=sorted({r["asof"] for r in cases})
    if not dates or dates[0]<"2026-10-01" or dates[-1]!="2026-10-23":
        raise ValueError("V617_STUDY_DATE_RANGE_INVALID")
    risk=[]
    for d in dates:
        q=proxy.get(d)
        if q is None:raise ValueError("V617_MISSING_MARKET_ASOF_DAY")
        risk.append(q)
    grouped=defaultdict(list)
    for r in cases:grouped[r["mode"]].append(r)
    comparison=[]
    for mode,rs in sorted(grouped.items()):
        baseline=[x for x in rs if x["shadow_net_pct"]!=""]
        green=[x for x in rs if proxy[x["asof"]]["risk_mode"]=="GREEN_RESEARCH_ONLY"]
        maturetouch=[x for x in green if x["future5_complete"]=="True"
                     and x["next_day_limit_touch_not_broker_fill"]=="True"]
        greenp=[x for x in maturetouch if x["shadow_net_pct"]!=""]
        vals=[float(x["shadow_net_pct"]) for x in baseline]
        gv=[float(x["shadow_net_pct"]) for x in greenp]
        comparison.append(dict(mode=mode,
            baseline_5d_matured_price_touch_events=sum(
                x["future5_complete"]=="True" and
                x["next_day_limit_touch_not_broker_fill"]=="True" for x in rs),
            baseline_5d_proxy_pnl_count=len(vals),
            baseline_proxy_mean_net_pct=round(statistics.mean(vals),3) if vals else "",
            green_signal_count=len(green),
            green_5d_complete_price_touch_events=len(maturetouch),
            green_5d_proxy_pnl_count=len(gv),
            green_5d_proxy_avg_net_pct=round(statistics.mean(gv),3) if gv else "",
            red_signal_count=sum(proxy[x["asof"]]["risk_mode"].startswith("RED") for x in rs),
            amber_signal_count=sum(proxy[x["asof"]]["risk_mode"].startswith("AMBER") for x in rs),
            approved_live_buys=0))
    meta=dict(schema=SCHEMA,source_asof="2026-10-23",
      frozen_v616_sha256=digest(statusfile.read_bytes()),
      frozen_v616_case_sha256=digest(casesfile.read_bytes()),
      market_proxy="KOSPI200_TRACKER_069500_NOT_WHOLE_KOSPI_KOSDAQ",
      benchmark_asof_history_SHA256=marketsha,
      session_dates=len(risk),
      risk_day_distribution=dict(Counter(q["risk_mode"] for q in risk)),
      last_observed_market_risk=risk[-1]["risk_mode"],
      KOSDAQ_independent_index_not_certified=True,
      market_proxy_not_a_sole_buy_authority=True,
      research_trade_outcomes_overlapping_not_independent=True,
      costed_trade_execution_not_verified=True,
      20261026_and_after_not_observed=True,
      no_change_to_live_2R_or_80_point_gates=True,
      final_buy_authorization_count=0,
      orders_enabled=False,trade_approved=False,
      recommendation="CASH_WITH_RESEARCH_WATCHLIST")
    return meta,risk,comparison

def save(out,meta,risk,comparison):
    out.mkdir(parents=True,exist_ok=True)
    for name,fields,rows in (
        ("v617_risk_days.csv",FIELDS,risk),
        ("v617_entry_mode_risk_comparison.csv",SUMMARY,comparison)):
        with (out/name).open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="raise")
            w.writeheader();w.writerows(rows)
    meta["file_sha256"]={p:digest((out/p).read_bytes()) for p in (
       "v617_risk_days.csv","v617_entry_mode_risk_comparison.csv")}
    (out/"v617_status.json").write_text(json.dumps(
         meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# C3 v6.17 — 시장 급락 위험 분리, 후보는 남기고 BUY는 강제로 만들지 않음","",
       "2026-10-23까지 완료된 날짜만 분석. KOSPI200 추종 ETF 069500은 **시장 위험 프록시**이며 전체 KOSPI·KOSDAQ 정밀 인증은 아니다.",
       "RED: 지수대용 ETF 20일선 하회 또는 단기 급락 → 현금 우선.",
       "AMBER: 20일선 위라도 단기 하락 모멘텀 → 신규주문 유보.",
       "GREEN: 20일선 위·최근 단기 하락 아님 → 연구후보만 평가. 실제 매수 승인 아님.","",
       "| 완료 거래일 | KOSPI200 ETF 종가 | 5일 등락 | 상태 |",
       "|---|---:|---:|---|"]
    for z in risk:
        lines.append("| {} | {} | {}% | {} |".format(
            z["asof"],z["etf_069500_close"],z["etf_069500_ret5_pct"],z["risk_mode"]))
    lines+=["","## 일봉 후행 5거래일 연구 성과 — 필터 전 vs 그린 연구조건","",
      "| 진입 방식 | 전체 수익 계산된 모의건 | 평균 순수익률 | GREEN 모의건 | GREEN 평균 순수익률 |",
      "|---|---:|---:|---:|---:|"]
    for x in comparison:
        lines.append("| {} | {} | {}% | {} | {}% |".format(x["mode"],
            x["baseline_5d_proxy_pnl_count"],x["baseline_proxy_mean_net_pct"],
            x["green_5d_proxy_pnl_count"],x["green_5d_proxy_avg_net_pct"]))
    lines+=["","**위험분류는 사전 선언한 임계치에 대한 과거 적용 결과일 뿐 최적화·미래 승률 검증이 아니다.**",
      "단기 ETF 시장 대용지표만으로 개별 종목을 실매수하지 않으며, RED에서도 연구 Top5는 유지하되 반드시 별도 'CASH' 결정을 표시한다.",
      "**Required Next Data:** 10/26 이후 완료 종가, 실제 정규장별 공식 시장 지표, 과거 PIT 공시·주권 종류, 키움 주문가능 잔고/체결, 시장 상승구간 독립 표본."]
    (out/"v617_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--v18",required=True,type=Path)
    p.add_argument("--v616-status",required=True,type=Path)
    p.add_argument("--v616-cases",required=True,type=Path)
    p.add_argument("--outdir",required=True,type=Path)
    a=p.parse_args()
    meta,risk,comp=evaluate(a.v18,a.v616_status,a.v616_cases)
    save(a.outdir,meta,risk,comp)
    print("V617_RISK_STATUS",json.dumps(meta,ensure_ascii=False),flush=True)
    for x in comp:print("V617_RISK_MODE",json.dumps(x,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
