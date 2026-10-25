#!/usr/bin/env python3
"""v6.20 honest loss attribution: signal selection vs achievable limit vs market.

FROZEN Oct 1-23 research (not PIT certified or regular-session confirmed).
Predeclared, NOT OPTIMIZED trend/momentum/market cohorts. Redo next-session
limit feasibility with high/open/low/gap checks, stop first, 0.65% total
assumed round trip; ETF 069500 same-day open-to-exit close market-relative
proxy (timing imperfect). NEVER authorize order or infer predictive accuracy.
"""
from __future__ import annotations
import argparse,csv,json,math,random,statistics
from collections import defaultdict,Counter
from functools import lru_cache
from pathlib import Path
from forward_ledger_v63 import read_csv,digest
from practical_entry_quotes_v619 import next_session_touch,krx_round

SCHEMA="C3_V620_PROFITABILITY_ATTRIBUTION_NO_BUY"
V616="C3_V616_PREDECLARED_ENTRY_TOURNAMENT_READ_ONLY"
V617="C3_V617_MARKET_CRASH_GATE_AUDIT_READ_ONLY"
SIGNAL="C3_CONDITIONAL_OPPORTUNITY_FRONTIER_V615"
COST_PCT=0.65
COHORTS=("ALL",
         "GREEN_ONLY",
         "AMBER_GREEN_ONLY",
         "FIRST_MA20_RESUME",
         "FRESH_20D_BREAKOUT",
         "EARLY_MA20_RECLAIM",
         "STRUCTURE_RISK_LE6",
         "REL_VOLUME_GE1P2",
         "OVERHEAD_NET_R_GE2",
         "GREEN_AND_MA20_RESUME",
         "GREEN_AND_RISK_LE6")
MODES=("ORIGINAL_LIMIT","BREAKOUT_RETEST_LIMIT","MA20_SUPPORT_LIMIT",
       "NEAR_CLOSE_LIMIT","NEXT_OPEN_GAP_CONDITION")
CASE_FIELDS=("asof","ticker","name","pattern","mode","risk_mode",
  "discovery_index_only","relative_volume20","entry_reference",
  "stop_reference","structure_risk_pct","overhead_net_R",
  "next_bar_date","next_open","next_high","next_low",
  "parent_touch_only","strict_contact_status","strict_price_contact_only",
  "five_future_sessions_complete","observed_parent_shadow_net_pct",
  "strict_shadow_net_pct_0p65_cost",
  "domestic_069500_market_open_to_exit_pct",
  "market_relative_proxy_net_pp","outcome","exit_date",
  "verified_broker_fill","final80_verified","regular1530_verified",
  "live_buy_approved","orders_enabled")
SUMMARY_FIELDS=("cohort","entry_mode","plans_total",
  "five_days_complete","old_touch_upper_bound",
  "strict_price_contact_not_broker_fill","strict_conservative_pnl_n",
  "distinct_signal_days","distinct_tickers",
  "pnl_positive_proxy_pct","pnl_mean_net_pct","pnl_median_net_pct",
  "pnl_worst_pct","pnl_day_cluster_CI_low","pnl_day_cluster_CI_high",
  "net_market_relative_mean_pp","strict_2R_overhead_price_count",
  "live_approved_buys")

def num(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):
        return None

def load_verified(v616status,v616cases,v615status,v615signals,v617status,v617days,v18):
    s=json.loads(v616status.read_text(encoding="utf-8"))
    t=json.loads(v615status.read_text(encoding="utf-8"))
    r=json.loads(v617status.read_text(encoding="utf-8"))
    if (s.get("schema")!=V616 or t.get("schema")!=SIGNAL or
        r.get("schema")!=V617 or
        s.get("study_candidates")!=315 or
        s.get("parent_signal_sha256")!=digest(v615signals.read_bytes()) or
        s.get("artifacts_sha256",{}).get("v616_all_entry_modes.csv")!=
          digest(v616cases.read_bytes()) or
        t.get("sha256",{}).get("v615_all_setups.csv")!=digest(v615signals.read_bytes()) or
        r.get("file_sha256",{}).get("v617_risk_days.csv")!=digest(v617days.read_bytes()) or
        s.get("trade_approved") is not False or s.get("orders_enabled") is not False or
        r.get("trade_approved") is not False or r.get("orders_enabled") is not False or
        s.get("source_asof")!="2026-10-23" or r.get("source_asof")!="2026-10-23"):
        raise ValueError("V620_FROZEN_SOURCE_SCHEMA_CHECKSUM_OR_SAFETY_INVALID")
    study=read_csv(v616cases)
    raw=read_csv(v615signals)
    dayrows=read_csv(v617days)
    if len(study)!=315 or len(dayrows)!=15:
        raise ValueError("V620_ARCHIVE_EXHAUSTIVENESS_MISMATCH")
    if (not v18.joinpath("market/prices").is_dir() or
        not v18.joinpath("market/etf_prices/069500.csv").is_file()):
        raise ValueError("V620_KRX_V18_ARCHIVE_NOT_READY")
    # Every study must have its asof signal-day source, never future ranks.
    bykey={(e["asof"],e["ticker"],e["method"]):e for e in raw}
    if len(bykey)!=len(raw):raise ValueError("V620_DUPLICATE_SIGNAL_PATTERN")
    for a in study:
        if ((a["asof"],a["ticker"],a["pattern"]) not in bykey
            or a["mode"] not in MODES
            or a["live_trade_approved"]!="False"
            or a["orders_enabled"]!="False"):
            raise ValueError("V620_UNMATCHED_STUDY_OR_FAKE_BUY")
    risk_by_date={r["asof"]:r["risk_mode"] for r in dayrows}
    if len(risk_by_date)!=15:raise ValueError("V620_INCOMPLETE_DOMESTIC_RISK")
    return study,bykey,risk_by_date

def strict_reference(c,stock,etf_by_date):
    """Re-evaluate old touch as a standing next-session order with no chase.

    v6.16 single-bar stop-first outcome preserved *only* when strict contact.
    LIMIT open below resting limit is excluded; never interpreted as fill.
    """
    a=c["asof"];future=[x for x in stock if x["Date"]>a][:5]
    out=dict(next_bar_date="",next_open="",next_high="",next_low="",
       strict_contact_status="INSUFFICIENT_FORWARD_FIVE",
       strict_price_contact_only=False,
       five_future_sessions_complete=False,
       strict_shadow_net_pct_0p65_cost="",observed_parent_shadow_net_pct="",
       domestic_069500_market_open_to_exit_pct="",market_relative_proxy_net_pp="")
    if len(future)<5:return out
    for i in range(4):
        if future[i]["Date"]>=future[i+1]["Date"]:
            raise ValueError("V620_FUTURE_DATE_BAD_ORDER")
    out["five_future_sessions_complete"]=True
    nextday=future[0]
    out.update(next_bar_date=nextday["Date"],next_open=nextday["Open"],
               next_high=nextday["High"],next_low=nextday["Low"])
    entry=num(c["entry_limit_reference"])
    stop=num(c["stop_reference"])
    close=num(c["asof_close"])
    if None in (entry,stop,close) or not 0<stop<entry:
        out["strict_contact_status"]="INVALID_PARENT_GEOMETRY";return out
    # Match predeclared history v6.16; read-only, never price tick-fill claim.
    if c["mode"]=="NEXT_OPEN_GAP_CONDITION":
        op=float(nextday["Open"])
        ceiling=num(c["condition_ceiling_reference"])
        label=("STUDY_PRICE_CONTACT_NOT_BROKER_FILL"
               if ceiling is not None and entry<=op<=ceiling and op>stop else
               "PENDING_LIMIT_NOT_TOUCHED")
    else:
        plan={"proposed_limit_krw":entry,"day_structure_stop_krw":stop}
        # Keep original study-limit float precision to compare exact parent
        # assumptions. v6.19 tick rounding must happen before any real order.
        label=next_session_touch(plan,close,
            max(num(c["distance_below_close_atr"]) or 0, .01) and
            _infer_atr(c,close,entry),
            float(nextday["Open"]),float(nextday["High"]),float(nextday["Low"]))
    out["strict_contact_status"]=label
    if label not in ("STUDY_PRICE_CONTACT_NOT_BROKER_FILL",
                   "STUDY_TOUCH_WITH_AMBIGUOUS_SAME_DAY_STOP_FIRST"):
        return out
    # Contradictory parent-touch status must not create fictitious returns.
    if c["next_day_limit_touch_not_broker_fill"]!="True":
        out["strict_contact_status"]="PARENT_STUDY_TOUCH_CONFLICT";return out
    out["strict_price_contact_only"]=True
    pnl=num(c["shadow_net_pct"])
    if pnl is None:
        out["strict_contact_status"]="CONTACT_NO_VALID_PARENT_PNL"
        return out
    out["observed_parent_shadow_net_pct"]=pnl
    out["strict_shadow_net_pct_0p65_cost"]=round(pnl-(COST_PCT-.5),3)
    exitday=c["shadow_exit_date"]
    if exitday:
        etfentry=etf_by_date.get(nextday["Date"])
        etfexit=etf_by_date.get(exitday)
        if etfentry and etfexit:
            eb=num(etfentry["Open"]);ex=num(etfexit["Close"])
            if eb and ex and eb>0:
                market=round(100*(ex/eb-1),3)
                out["domestic_069500_market_open_to_exit_pct"]=market
                out["market_relative_proxy_net_pp"]=round(
                   float(out["strict_shadow_net_pct_0p65_cost"])-market,3)
    return out

def _infer_atr(c,close,entry):
    # v6.16 only stored distance in ATR, rounded to .001;
    # reconstructing from rounded distance would magnify 0-distance errors.
    # Caller is required to use v6.15 original ATR source instead.
    raise ValueError("V620_REQUIRE_ORIGINAL_ATR_NOT_RECONSTRUCTION")

def strict_with_original_atr(c,signal,stock,etf):
    out=strict_reference.__wrapped__(c,stock,etf) if hasattr(strict_reference,"__wrapped__") else None
    raise NotImplementedError("OVERRIDE")

def qualifies(c,cohort):
    if cohort=="ALL":return True
    risk=c["risk_mode"]
    pattern=c["pattern"]
    if cohort=="GREEN_ONLY":return risk=="GREEN_RESEARCH_ONLY"
    if cohort=="AMBER_GREEN_ONLY":return risk in ("GREEN_RESEARCH_ONLY","AMBER_CONFIRMATION_WAIT")
    if cohort=="FIRST_MA20_RESUME":return pattern=="FIRST_MA20_RESUME"
    if cohort=="FRESH_20D_BREAKOUT":return pattern=="FRESH_20D_BREAKOUT"
    if cohort=="EARLY_MA20_RECLAIM":return pattern=="EARLY_MA20_RECLAIM"
    if cohort=="STRUCTURE_RISK_LE6":
        return (num(c["structure_risk_pct"]) or 100)<=6
    if cohort=="REL_VOLUME_GE1P2":
        return (num(c["relative_volume20"]) or 0)>=1.2
    if cohort=="OVERHEAD_NET_R_GE2":
        return (num(c["overhead_net_R"]) or -100)>=2
    if cohort=="GREEN_AND_MA20_RESUME":
        return risk=="GREEN_RESEARCH_ONLY" and pattern=="FIRST_MA20_RESUME"
    if cohort=="GREEN_AND_RISK_LE6":
        return risk=="GREEN_RESEARCH_ONLY" and (num(c["structure_risk_pct"]) or 100)<=6
    raise ValueError("V620_UNKNOWN_PREDECLARED_COHORT")

def day_cluster_ci(rows,field="strict_shadow_net_pct_0p65_cost"):
    """Deterministic percentile bootstrap by SIGNAL DATE, not independent trades."""
    good=[r for r in rows if num(r[field]) is not None]
    byday=defaultdict(list)
    for r in good:byday[r["asof"]].append(float(r[field]))
    days=sorted(byday)
    if len(days)<6 or len(good)<12:return None,None
    rng=random.Random(620)
    vals=[]
    for k in range(600):
        chosen=[days[rng.randrange(len(days))] for _ in days]
        flat=[x for d in chosen for x in byday[d]]
        vals.append(statistics.mean(flat))
    vals.sort()
    return round(vals[15],3),round(vals[-16],3)

def summarize(rows):
    result=[]
    for cohort in COHORTS:
        for mode in MODES:
            group=[r for r in rows if r["mode"]==mode and qualifies(r,cohort)]
            mature=[r for r in group if r["five_future_sessions_complete"]]
            positive=[r for r in mature if r["strict_price_contact_only"]]
            pnls=[float(r["strict_shadow_net_pct_0p65_cost"]) for r in positive
                  if num(r["strict_shadow_net_pct_0p65_cost"]) is not None]
            alphas=[float(r["market_relative_proxy_net_pp"]) for r in positive
                    if num(r["market_relative_proxy_net_pp"]) is not None]
            lo,hi=day_cluster_ci(positive)
            result.append(dict(cohort=cohort,entry_mode=mode,
              plans_total=len(group),five_days_complete=len(mature),
              old_touch_upper_bound=sum(r["parent_touch_only"] for r in mature),
              strict_price_contact_not_broker_fill=len(positive),
              strict_conservative_pnl_n=len(pnls),
              distinct_signal_days=len(set(r["asof"] for r in positive)),
              distinct_tickers=len(set(r["ticker"] for r in positive)),
              pnl_positive_proxy_pct=round(100*sum(v>0 for v in pnls)/len(pnls),2) if pnls else "",
              pnl_mean_net_pct=round(statistics.mean(pnls),3) if pnls else "",
              pnl_median_net_pct=round(statistics.median(pnls),3) if pnls else "",
              pnl_worst_pct=round(min(pnls),3) if pnls else "",
              pnl_day_cluster_CI_low=lo if lo is not None else "",
              pnl_day_cluster_CI_high=hi if hi is not None else "",
              net_market_relative_mean_pp=round(statistics.mean(alphas),3) if alphas else "",
              strict_2R_overhead_price_count=sum((num(r["overhead_net_R"]) or -10)>=2 for r in positive),
              live_approved_buys=0))
    return result

def main():
    parser=argparse.ArgumentParser()
    for key in ("v18","v616-status","v616-cases","v615-status","v615-signals",
       "v617-status","v617-risk","outdir"):
        parser.add_argument("--"+key,required=True,type=Path)
    q=parser.parse_args()
    study,signals,risks=load_verified(q.v616_status,q.v616_cases,q.v615_status,
       q.v615_signals,q.v617_status,q.v617_risk,q.v18)
    stockprices=q.v18/"market/prices"
    etf={r["Date"]:r for r in read_csv(q.v18/"market/etf_prices/069500.csv")}
    @lru_cache(maxsize=360)
    def history(ticker):
        p=stockprices/(ticker+".csv")
        if not p.is_file():raise ValueError("V620_MISSING_TICKER_ARCHIVE")
        x=read_csv(p)
        if len(x)<120 or x[-1]["Date"]!="2026-10-23":
            raise ValueError("V620_INCOMPLETE_HISTORY")
        return x
    rows=[]
    for c in study:
        sig=signals[(c["asof"],c["ticker"],c["pattern"])]
        # All fields date-stamped original signal, not future fields.
        daily=history(c["ticker"])
        orig_asof=[x for x in daily if x["Date"]==c["asof"]]
        if len(orig_asof)!=1 or float(orig_asof[0]["Close"])!=float(c["asof_close"]):
            raise ValueError("V620_ASOF_DATA_CONFLICT")
        outcome=strict_reference(c,daily,etf,signal_atr=num(sig["atr14"]))
        rows.append(dict(asof=c["asof"],ticker=c["ticker"],name=c["name"],
          pattern=c["pattern"],mode=c["mode"],risk_mode=risks[c["asof"]],
          discovery_index_only=c["score_rank_only"],
          relative_volume20=sig["relative_volume20"],
          entry_reference=c["entry_limit_reference"],
          stop_reference=c["stop_reference"],
          structure_risk_pct=c["structural_risk_pct"],
          overhead_net_R=c["net_r_to_overhead"],
          parent_touch_only=c["next_day_limit_touch_not_broker_fill"]=="True",
          outcome=c["shadow_outcome"],exit_date=c["shadow_exit_date"],
          verified_broker_fill=False,final80_verified=False,
          regular1530_verified=False,live_buy_approved=False,orders_enabled=False,
          **outcome))
    results=summarize(rows)
    out=q.outdir;out.mkdir(parents=True,exist_ok=True)
    def write_csv(name,fields,rs):
        with (out/name).open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="raise")
            w.writeheader();w.writerows(rs)
    write_csv("v620_trade_attribution.csv",CASE_FIELDS,rows)
    write_csv("v620_predeclared_cohorts.csv",SUMMARY_FIELDS,results)
    status=dict(schema=SCHEMA,asof="2026-10-23",
       source_v616_sha256=digest(q.v616_cases.read_bytes()),
       source_v615_sha256=digest(q.v615_signals.read_bytes()),
       source_v617_risk_sha256=digest(q.v617_risk.read_bytes()),
       case_count=len(rows),all_conditions_predeclared=True,
       sample_has_bear_regime_concentration=True,
       independent_unseen_period_validation=False,
       regular_session_price_certified=False,
       historic_fundamentals_PIT_certified=False,
       slippage_and_cost_assumption_pct=COST_PCT,
       first_day_price_contact_not_execution=True,
       ETF_market_open_to_exit_comparison_not_exact_trade_match=True,
       profit_proven=False,trade_approved=False,orders_enabled=False,
       cohort_count=len(COHORTS),comparison_count=len(results))
    status["sha256"]={name:digest((out/name).read_bytes())
      for name in ("v620_trade_attribution.csv","v620_predeclared_cohorts.csv")}
    (out/"v620_status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# C3 v6.20 수익성 병목 분해 — 기존 15거래일 자료",
      "**10/1~10/23 소급 데이터이며 신규 실전 승인 0건**",
      "신호 자체 선택 / 다음날 가격 접촉(갭·추격금지) / 실질 구조 손익비 / KOSPI200 ETF 위험장이라는 네 가지 효과를 분리합니다.",
      "일봉 저가가 지정가와 맞닿아도 실제 체결은 인증되지 않으며 0.65% 비용은 가정값입니다.",
      "6일 미만 독립 신호 날짜 또는 12건 미만 가격접촉은 신뢰구간 산출하지 않습니다.",
      "**특정 부분집합이 우연히 이익을 보여도 이 15일 자료로 매수전략 채택 금지.**", "",
      "| 사전 조건 | 진입 방식 | 5일 관찰완료 | 엄격 가격접촉 | 순수익 계산 | 평균 순수익 | 시장 상대 |",
      "|---|---|---:|---:|---:|---:|---:|"]
    for x in results:
        if x["cohort"] in ("ALL","GREEN_ONLY","STRUCTURE_RISK_LE6",
                           "OVERHEAD_NET_R_GE2","GREEN_AND_MA20_RESUME"):
            lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
                x["cohort"],x["entry_mode"],x["five_days_complete"],
                x["strict_price_contact_not_broker_fill"],
                x["strict_conservative_pnl_n"],
                x["pnl_mean_net_pct"],x["net_market_relative_mean_pp"]))
    lines+=["","**최우선 후속검증:** 외국인/기관 순매수를 필수로 하지 않는 KRX 전시장 정규장 데이터 스캔, 연속 상승·추세위치 및 산업주도주 강도, 최소 60~120개 과거 거래일과 독립 이후 5거래일, 실제 주문잔고/슬리피지 검증.",
      "실전 매수 승인 점수 >=80, 구조손절 먼저, 검증된 저항 비용후 >=2R, C3 1종목 원칙 유지."]
    (out/"v620_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("V620_SOURCE_VALIDATED",json.dumps(status,ensure_ascii=False),flush=True)
    for x in results:
        if x["cohort"] in ("ALL","GREEN_ONLY","STRUCTURE_RISK_LE6","OVERHEAD_NET_R_GE2","GREEN_AND_MA20_RESUME"):
            print("V620_PROFIT",json.dumps(x,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
