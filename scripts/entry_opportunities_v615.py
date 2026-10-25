#!/usr/bin/env python3
"""v6.15 C3 opportunity frontier: do not confuse a watchable setup with BUY.

Read-only historical research from the unchanged v6.14 Oct23 archive.
No K100 new purchases, no trade orders. Initial 2R/live-score/regular-only/PIT
safety approval is NEVER bypassed. This studies why "0 buys" was observed and
provides a wider, falsifiable *next-day conditional* shortlist.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path
from october_replay_v614 import verify
from forward_ledger_v63 import read_csv,digest
from sector_flow_v69 import load_flows
from official_issuer_entry_v610 import is_common
from broad_watch_v611 import blocked_issuer
from full_market_scanner_v68 import parse_days,valid_bar
from top20_quality_v612 import metrics,score
from free_structural_v52 import last_confirmed_pivot

SCHEMA="C3_CONDITIONAL_OPPORTUNITY_FRONTIER_V615"
FIELDS=("asof","ticker","name","market","method","rank_date","discovery_index_only",
 "fi_5d_net_krw","fi_positive_sessions","asof_close","prior20_high",
 "relative_volume20","atr14","sma20","sma60","pivot_date","pivot_low",
 "first_limit_study","structure_stop_study","structural_risk_pct",
 "entry_distance_atr","nearby_confirmed_overhead","net_R_to_ceiling",
 "scenario_target_2R_not_verified","classification","next_session",
 "next_session_limit_touch_only","regular_1530_price_verified",
 "issuer_history_PIT_verified","final80_trade_score_verified",
 "broker_order_confirmed","trade_approved","orders_enabled")
DAY_FIELDS=("asof","market_liquid_valid_flow_positive","setup_stocks",
 "geometry_1p5R_candidates","open_air_breakout_watches",
 "insufficient_headroom_or_structure","top5_research_candidates",
 "next_session","next_session_study_limit_touches",
 "verified_trade_buys","decision")

def atr14(b):
    if len(b)<16:return None
    tr=[]
    for i in range(len(b)-14,len(b)):
        p=b[i-1]["close"];z=b[i]
        tr.append(max(z["high"]-z["low"],abs(z["high"]-p),abs(z["low"]-p)))
    return sum(tr)/14

def method_candidates(b,atr,rv):
    """Candidate generation based ONLY on completed candles at index -1."""
    c=b[-1]["close"]; y=b[-2]
    ma20=sum(z["close"] for z in b[-20:])/20
    ma60=sum(z["close"] for z in b[-60:])/60
    old20=sum(z["close"] for z in b[-25:-5])/20
    prior20=max(z["high"] for z in b[-21:-1])
    prev20=sum(z["close"] for z in b[-21:-1])/20
    signals=[]
    if (c>prior20 and y["close"]<=prior20 and c<=prior20+1.3*atr
        and ma20>=ma60 and ma20>old20 and rv>=0.9):
        signals.append(("FRESH_20D_BREAKOUT",min(c,prior20+.30*atr)))
    if (ma20>ma60 and ma20>old20 and c>y["high"]
        and c<=ma20+2.5*atr and c>ma20 and
        min(z["low"] for z in b[-7:-1])<=ma20+.8*atr and rv>=.65):
        signals.append(("FIRST_MA20_RESUME",min(c,ma20+.65*atr)))
    if (y["close"]<=prev20 and c>ma20 and c>y["high"]
        and ma20>=.97*ma60 and rv>=.8):
        signals.append(("EARLY_MA20_RECLAIM",min(c,ma20+.3*atr)))
    return signals,ma20,ma60,prior20

def confirmed_overhead(b,entry,close):
    """Only fully confirmed swing highs ABOVE today's close are overhead.

    Prior highs already overtaken by the as-of close are not wrongly treated
    as ceiling. Missing overhead is NOT proof of achievable 2R.
    """
    levels=[]
    for i in range(max(2,len(b)-80),len(b)-3):
        h=b[i]["high"]
        if (h>max(close,entry) and h>b[i-1]["high"]
            and h>b[i-2]["high"] and h>=b[i+1]["high"]
            and h>=b[i+2]["high"]):
            levels.append(h)
    return min(levels) if levels else None

def inspect(b,m,asof,code,name,market,fi5,rank=0):
    if (len(b)<120 or b[-1]["date"]!=asof or
        any(not valid_bar(z) for z in b[-120:]) or fi5<=0):
        return []
    atr=atr14(b)
    if atr is None or atr<=0:return []
    c=b[-1]["close"]; rv=m["relative_volume20"]
    signals,ma20,ma60,p20=method_candidates(b,atr,rv)
    if not signals:return []
    pd,plow=last_confirmed_pivot(b)
    out=[]
    for method,first in signals:
        stop=plow-max(.25*atr,.003*c) if plow is not None else None
        risk=100*(first-stop)/first if stop is not None and 0<stop<first else None
        distance=(c-first)/atr
        ceiling=confirmed_overhead(b,first,c)
        rr=((ceiling-first-.005*first)/(first-stop+.005*first)
            if risk is not None and ceiling is not None else None)
        clean_breakout=(method=="FRESH_20D_BREAKOUT" and
             c>max(z["high"] for z in b[-61:-1]))
        plausible=(risk is not None and 1.5<=risk<=10
                   and distance<=1.25 and
                   m["return_20d_pct"]<=30 and
                   m["distance_from_sma20_pct"]<=15 and
                   m["atr14_pct"]<=10)
        if plausible and rr is not None and rr>=1.5:
            stage="A_CONDITIONAL_GEOMETRY_1P5R_RESEARCH"
        elif (risk is not None and 1.5<=risk<=12 and distance<=1.0
              and m["return_20d_pct"]<=30 and m["atr14_pct"]<=12
              and clean_breakout and ceiling is None):
            stage="B_PRICE_DISCOVERY_NO_PROVEN_TARGET_WATCH"
        else:
            stage="C_SIGNAL_NOT_READY_RISK_OR_HEADROOM"
        target=first+2*(first-stop+.005*first)+.005*first if risk is not None else None
        out.append(dict(asof=asof,ticker=code,name=name,market=market,
            method=method,rank_date=rank,discovery_index_only=m.get("discovery_index_100"),
            fi_5d_net_krw=fi5,fi_positive_sessions=m["fi_positive_session_count"],
            asof_close=round(c,2),prior20_high=round(p20,2),
            relative_volume20=round(rv,3),atr14=round(atr,2),
            sma20=round(ma20,2),sma60=round(ma60,2),
            pivot_date=pd or "",pivot_low=round(plow,2) if plow else "",
            first_limit_study=round(first,2),structure_stop_study=round(stop,2) if stop else "",
            structural_risk_pct=round(risk,3) if risk is not None else "",
            entry_distance_atr=round(distance,3),
            nearby_confirmed_overhead=round(ceiling,2) if ceiling else "",
            net_R_to_ceiling=round(rr,3) if rr is not None else "",
            scenario_target_2R_not_verified=round(target,2) if target else "",
            classification=stage,next_session="",
            next_session_limit_touch_only="",
            regular_1530_price_verified=False,issuer_history_PIT_verified=False,
            final80_trade_score_verified=False,broker_order_confirmed=False,
            trade_approved=False,orders_enabled=False))
    return out

def calculate(v18,issuer):
    basic,days,daypaths,sectors,members=verify(v18,issuer)
    @lru_cache(maxsize=3500)
    def history(t):
        p=v18/"market/prices"/(t+".csv")
        return read_csv(p) if p.is_file() else []
    daily=[];events=[];top5=[];lastdate=days[-1]
    for ix,day in enumerate(days):
        flowdays,flows,_=load_flows(v18,day)
        market={}
        for mk in ("KOSPI","KOSDAQ"):
            for z in read_csv(daypaths[day][mk]):
                t=z["ticker"]
                if t in market:raise ValueError("V615_DUPLICATE_MARKET_TICKER")
                market[t]=(mk,z)
        # Exclude health/pharma by date-stamped ETF membership as well as names.
        # A retrospective ETF snapshot is an exclusion hint, never proof
        # of historical sector membership or future returns.
        health_codes=set()
        for sector_row in sectors[day]:
            if sector_row["sector_id"]!="HEALTH":continue
            snap=sector_row["snapshot_date"]
            if (snap<=day and
                (date.fromisoformat(day)-date.fromisoformat(snap)).days<=10):
                health_codes.update(members.get(("HEALTH",snap),set()))
        clean=[];watched=0
        for t,(mk,rawday) in sorted(market.items()):
            info=basic.get(t)
            if not is_common(info) or info["market"]!=mk:continue
            if blocked_issuer(info["name"],t in health_codes):continue
            hist=history(t)
            if len(hist)<120:continue
            truncated=[x for x in hist if x["Date"]<=day]
            if len(truncated)<120:continue
            b,err=parse_days(truncated,t,date.fromisoformat(day))
            if err or any(not valid_bar(x) for x in b[-120:]):continue
            b=b[-120:]
            if (b[-1]["turnover_krw"] is None or
                b[-1]["turnover_krw"]<5e9):continue
            if (b[-1]["close"]!=float(rawday["Close"]) or
                abs(b[-1]["turnover_krw"]-float(rawday["TurnoverKRW"]))>1):
                raise ValueError("V615_MARKET_ARCHIVED_RAW_CLOSE_TURNOVER_CONFLICT")
            pairs=[]
            for d in flowdays:
                f=flows[(d,"foreign")].get(t);inst=flows[(d,"institution")].get(t)
                if f is None or inst is None or f[0]!=mk or inst[0]!=mk:
                    pairs=[];break
                pairs.append((f[1],inst[1]))
            if len(pairs)!=5:continue
            f5=sum(f for f,i in pairs);i5=sum(i for f,i in pairs)
            if f5+i5<=0:continue
            if [x["date"] for x in b[-5:]]!=flowdays:continue
            watched+=1
            m=metrics(b,flowdays,pairs);m.update(score(m,f5,i5))
            ev=inspect(b,m,day,t,info["name"],mk,f5+i5)
            clean.extend(ev)
        order={"A_CONDITIONAL_GEOMETRY_1P5R_RESEARCH":0,
               "B_PRICE_DISCOVERY_NO_PROVEN_TARGET_WATCH":1,
               "C_SIGNAL_NOT_READY_RISK_OR_HEADROOM":2}
        clean.sort(key=lambda r:(order[r["classification"]],
                -r["discovery_index_only"],-r["fi_positive_sessions"],
                r["ticker"],r["method"]))
        nextday=days[ix+1] if ix+1<len(days) else ""
        with_next=[]
        for e in clean:
            e["next_session"]=nextday
            if nextday:
                future=[z for z in history(e["ticker"]) if z["Date"]==nextday]
                if len(future)==1:
                    z=future[0]
                    # A low touch is just a price contact, NOT a proven fill.
                    e["next_session_limit_touch_only"]=(float(z["Low"])<=e["first_limit_study"])
            with_next.append(e)
        shortlisted=[];seen=set()
        for e in with_next:
            if e["ticker"] in seen:continue
            if len(shortlisted)==5:break
            shortlisted.append(e);seen.add(e["ticker"])
        top5.extend(shortlisted);events.extend(with_next)
        cnt=Counter(e["classification"] for e in with_next)
        daily.append(dict(asof=day,market_liquid_valid_flow_positive=watched,
          setup_stocks=len({x["ticker"] for x in with_next}),
          geometry_1p5R_candidates=len({x["ticker"] for x in with_next if x["classification"].startswith("A_")}),
          open_air_breakout_watches=len({x["ticker"] for x in with_next if x["classification"].startswith("B_")}),
          insufficient_headroom_or_structure=len({x["ticker"] for x in with_next if x["classification"].startswith("C_")}),
          top5_research_candidates=len(shortlisted),next_session=nextday,
          next_session_study_limit_touches=sum(e["next_session_limit_touch_only"] is True for e in shortlisted),
          verified_trade_buys=0,decision="RESEARCH_SHORTLIST_NOT_BUY"))
        print("V615",day,"flow",watched,"setups",len(with_next),
              "A",cnt["A_CONDITIONAL_GEOMETRY_1P5R_RESEARCH"],
              "B",cnt["B_PRICE_DISCOVERY_NO_PROVEN_TARGET_WATCH"],flush=True)
    report=dict(schema=SCHEMA,source_asof=lastdate,sessions=len(days),
       source_base_issuer_labels_point_in_time_proven=False,
       regular_session_only_1530_verified=False,
       original_historical_financial_growth_verified=False,
       strategy_net_profitability_proven=False,
       research_1p5R_is_NOT_live_2R_buy_rule=True,
       no_future_rows_in_signal_construction=True,
       orders_enabled=False,trade_approved=False,
       hypothetical_next_bar_touch_not_execution=True,
       C3_new_candidates_only=True,K100_new_candidates_allowed=False,
       reviewed_flow_positive_stocks=sum(d["market_liquid_valid_flow_positive"] for d in daily),
       dates_with_A=sum(d["geometry_1p5R_candidates"]>0 for d in daily),
       dates_with_A_or_B=sum((d["geometry_1p5R_candidates"]+d["open_air_breakout_watches"])>0 for d in daily),
       total_A_signals=sum(d["geometry_1p5R_candidates"] for d in daily),
       total_B_signals=sum(d["open_air_breakout_watches"] for d in daily),
       unique_event_count=len(events),top5_event_count=len(top5),
       buy_authorizations=0,decision="CASH_UNTIL_ALL_FINAL_GATES")
    return report,daily,events,top5

def save(out,meta,daily,events,top5):
    out.mkdir(parents=True,exist_ok=True)
    for fn,fields,rows in (
        ("v615_daily.csv",DAY_FIELDS,daily),
        ("v615_all_setups.csv",FIELDS,events),
        ("v615_top5_per_day.csv",FIELDS,top5)):
        with (out/fn).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="raise")
            w.writeheader();w.writerows(rows)
    meta["sha256"]={p:digest((out/p).read_bytes()) for p in (
        "v615_daily.csv","v615_all_setups.csv","v615_top5_per_day.csv")}
    (out/"v615_status.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# C3 v6.15 — 실전 매수보다 한 단계 앞선 조건부 연구후보","",
       "2026-10-01~23 완료 15거래일. 10/23 기준 수집 자료를 과거에 적용한 연구로 독립 PIT/정규장 종가 재검증이 없습니다.",
       "**A: 피벗 구조손절+비용 후 1.5R 이상이며 종가 대비 최대 1.25 ATR 이내의 대기 지정가 연구. 2R 실전승인 아님.**",
       "**B: 피벗 구조손절 최대 12% 및 윗저항 미검증 돌파 관찰. 2R 기대수익 검증 안 됨.**",
       "**C: 신호만 관찰. 조건부 대기조차 불가; 매수 승인 아님.**",
       "**실제 매수승인 0건, 주문 0건.**", "",
       "| 일자 | 수급통과 | 패턴 종목 | A연구 | B관찰 | 연구 Top5 | 다음날 가격접촉(체결아님) |",
       "|---|---:|---:|---:|---:|---:|---:|"]
    for d in daily:
        lines.append("| {asof} | {market_liquid_valid_flow_positive} | {setup_stocks} | {geometry_1p5R_candidates} | {open_air_breakout_watches} | {top5_research_candidates} | {next_session_study_limit_touches} |".format(**d))
    lines.extend(["","## 10/23 시점 기술 감시 Top5 (A/B 없으면 C도 표기; 10/26 매수 지시가 아님)","",
       "| 종목 | 패턴 | 단계 | 1차 참고가 | 일봉 구조손절 | 1.5R 저항 검증 |",
       "|---|---|---|---:|---:|---|"])
    for e in [x for x in top5 if x["asof"]=="2026-10-23"]:
        lines.append("| {} {} | {} | {} | {} | {} | {} |".format(
            e["name"],e["ticker"],e["method"],e["classification"],
            e["first_limit_study"],e["structure_stop_study"],
            e["net_R_to_ceiling"] if e["net_R_to_ceiling"]!="" else "저항 미확인"))
    lines+=["","**다음 검증:** 각 신호 이후 5거래일의 미체결/갭/손절/목표 성과, 독립 정규장-only 가격, 과거 주식종류·공시 PIT, 별도 최종 80점, 실제 계좌. A/B/C는 모두 연구단계이며, 수익 검증이 없으므로 1.5R을 실제 매수 허용선으로 바꾸지 않음."]
    (out/"v615_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--v18",type=Path,required=True)
    p.add_argument("--issuer",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args()
    report,daily,events,top5=calculate(a.v18,a.issuer)
    save(a.outdir,report,daily,events,top5)
    print("V615_SUMMARY",json.dumps(report,ensure_ascii=False))

if __name__=="__main__":main()
