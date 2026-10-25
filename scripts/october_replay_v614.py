#!/usr/bin/env python3
"""v6.14 honest October replay, v6.12 full daily shortlist + v6.13 risk entry.

This is a *retrospective* 2026-10-01..23 replay using a single Oct23
backfilled v18 archive. It is NOT strict independently vintage-confirmed PIT:
official issuer basic-info is dated Oct23, retrospective v18 ETF membership
and price histories might reflect later corrections; 15:30 regular-session-only
independent validation and original filing financial numbers unavailable.
Treat v6.14 research signals, next bar touch and 5-session paths as
HYPOTHETICAL, not broker executed fills. Full v6.13 BUY would be zero on
every day because compulsory final approval evidence remains false.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import Counter,defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from forward_ledger_v63 import read_csv,read_json,digest
from sector_flow_v69 import load_flows
from official_issuer_entry_v610 import is_common,load_basic,BASIC_SCHEMA
from broad_watch_v611 import blocked_issuer
from full_market_scanner_v68 import parse_days,valid_bar
from top20_quality_v612 import metrics,score,risk_priority_reason,COHORT_TARGETS
from entry_strategy_v58 import evaluate,METHODS
from entry_readiness_v613 import first_gate,second_gate

SCHEMA="C3_K100_OCTOBER_15DAY_REPLAY_V614"
DAILY_FIELDS=("asof","market_symbols","market_common_historic_issuer_PIT_unverified",
  "common_120bars_turnover50e8","flow_complete_and_net_buy_positive",
  "both_investor_net_buy_positive","strong_proxy_sector_count",
  "strong_sector_positive_buy_candidates","balanced_top20","risk_watch_top5",
  "research_confirmed_methods_all_flow_candidates","research_first_2R_all_flow_candidates",
  "research_confirmed_methods_balanced20","research_first_2R_balanced20",
  "research_first_2R_risk_top5","next_session","next_session_first_limit_touched_balanced20",
  "next_session_first_limit_touched_risk_top5",
  "broker_actual_execution_known","verified_real_buy_authorizations",
  "trade_approved","decision")
SIGNAL_FIELDS=("asof","ticker","name","market","research_group",
   "is_balanced_top20","is_risk_top5","method","signal_status",
   "stop_research","first_limit_research","second_optional_research",
   "first_net_R","nearest_ceiling_research",
   "first_2R_research","second_optional_2R_research",
   "next_session","next_session_limit_below_intraday_low_or_not",
   "next_session_limit_price_touched_hypothetical",
   "five_trading_session_window_complete",
   "future_5session_observed_min_low","future_5session_observed_max_high",
   "same_session_fill_stop_order_uncertain",
   "verified_1530_regular_only","historical_issuer_PIT_proof",
   "historical_financials_PIT_proof","final_80_point_buy_approval",
   "actual_broker_order_execution_known","trade_approved")
TOP_FIELDS=("asof","rank","ticker","name","research_group",
  "discovery_index_not_final80","risk_filter_pass","confirmed_method_count",
  "first_2R_method_count","next_session","trade_approved")

def verify(v18,issuer):
    st=read_json(v18/"diagnostics/collection_status.json")
    b=read_json(issuer/"basic/krx_basic_v610_status.json")
    if (st.get("asof")!="2026-10-23" or b.get("schema")!=BASIC_SCHEMA
        or b.get("asof")!="2026-10-23" or b.get("official_base_usable") is not True
        or st.get("orders_enabled") is not False
        or st.get("datasets",{}).get("prices",{}).get("status")!="OK"
        or st.get("datasets",{}).get("flows",{}).get("status")!="OK"
        or st.get("datasets",{}).get("holdings",{}).get("status")!="OK"):
        raise ValueError("V614_REPLAY_MARKET_ISSUER_ARCHIVE_ASOF_INCOMPATIBLE")
    if b["market_counts"].get("KOSPI",0)+b["market_counts"].get("KOSDAQ",0)<2000:
        raise ValueError("V614_ISSUER_MARKET_INCOMPLETE")
    basic=load_basic(issuer/"basic",b)
    rawdays={}
    for mk in ("KOSPI","KOSDAQ"):
        d=v18/"market/daily_prices"/mk
        for p in d.glob("2026-10-*.csv"):
            day=p.stem
            rawdays.setdefault(day,{})[mk]=p
    days=sorted(d for d in rawdays if len(rawdays[d])==2
        and "2026-10-01"<=d<="2026-10-23")
    if len(days)!=15 or days[0]!="2026-10-01" or days[-1]!="2026-10-23":
        raise ValueError("V614_OCTOBER_MARKET_DATES_15_INCOMPLETE")
    sectors=read_csv(v18/"research/sector_evidence_daily.csv")
    memberships=read_csv(v18/"market/sector_membership_dated.csv")
    sr=defaultdict(list)
    for r in sectors:
        if r["date"] in days:sr[r["date"]].append(r)
    if any(len(sr[d])!=17 for d in days):
        raise ValueError("V614_OCTOBER_17_SECTOR_DAY_MISSING")
    membership=defaultdict(set)
    for r in memberships:
        membership[(r["sector_id"],r["snapshot_date"])].add(r["ticker"])
    return basic,days,rawdays,sr,membership

def sector_proxy_of_day(day,sector_rows,members,flows,flowdays):
    strong=set();byticker=defaultdict(set)
    for r in sector_rows:
        sid=r["sector_id"];snap=r["snapshot_date"]
        src=members.get((sid,snap),set())
        if (date.fromisoformat(snap)>date.fromisoformat(day) or
            (date.fromisoformat(day)-date.fromisoformat(snap)).days>10):
            continue
        for t in src:byticker[t].add(sid)
        if sid=="HEALTH" or not src:continue
        if (r["price_flow_proxy_ready"]!="True" or
            r["membership_status"]!="PROVIDER_DATED_PROXY_NOT_STRICT_PIT" or
            r["live_selection_authorized"]!="False"):
            continue
        rs=float(r["rs_5d_pp"]) if r["rs_5d_pp"] else -math.inf
        breadth=float(r["breadth_up_5d_pct"]) if r["breadth_up_5d_pct"] else -math.inf
        if rs<=0 or breadth<20:continue
        if (not r["foreign_5d_coverage"] or
            not r["institution_5d_coverage"] or
            float(r["foreign_5d_coverage"])<.95 or
            float(r["institution_5d_coverage"])<.95 or
            r["turnover_coverage"]=="" or
            float(r["member_turnover_krw"])<=0):
            continue
        # All ETF constituents must be in every raw day: no missing == zero.
        foreign=0.;inst=0.;complete=True
        for t in src:
            for d in flowdays:
                f=flows[(d,"foreign")].get(t)
                i=flows[(d,"institution")].get(t)
                if f is None or i is None:
                    complete=False;break
                foreign+=f[1];inst+=i[1]
            if not complete:break
        if not complete or foreign+inst<=0:continue
        # Recompute daily sector reported sums from exact same five dated rows.
        fv=float(r["foreign_net_buy_5d_krw"]) if r["foreign_net_buy_5d_krw"] else None
        iv=float(r["institution_net_buy_5d_krw"]) if r["institution_net_buy_5d_krw"] else None
        if fv is None or iv is None or abs(fv-foreign)>1.1 or abs(iv-inst)>1.1:
            # Do not claim official strict sector without matching raw flow.
            continue
        strong.add(sid)
    return strong,byticker

def main_calc(v18,issuer):
    basic,days,daypaths,sectors,members=verify(v18,issuer)
    @lru_cache(maxsize=3500)
    def history(ticker):
        path=v18/"market/prices"/(ticker+".csv")
        return read_csv(path) if path.is_file() else []
    summary=[];signals=[];shortlists=[];coverage=Counter();prev_risk=[]
    for j,day in enumerate(days):
        flowdays,rawflows,_=load_flows(v18,day)
        strict,member_by_ticker=sector_proxy_of_day(day,sectors[day],members,rawflows,flowdays)
        market={}
        for mk in ("KOSPI","KOSDAQ"):
            for row in read_csv(daypaths[day][mk]):
                t=row["ticker"]
                if t in market:raise ValueError("V614_DUPLICATE_DATED_MARKET_TICKER")
                market[t]=(mk,row)
        watched=[];liquid=0;positive=0;both=0;strongbuy=0
        barsmap={}
        for t,(mk,daily) in sorted(market.items()):
            info=basic.get(t)
            if not is_common(info) or info["market"]!=mk:
                continue
            classified=member_by_ticker.get(t,set())
            if blocked_issuer(info["name"],"HEALTH" in classified):continue
            raw=history(t)
            if not raw:continue
            truncated=[r for r in raw if r["Date"]<=day]
            if len(truncated)<120:continue
            bars,err=parse_days(truncated,t,date.fromisoformat(day))
            if err or any(not valid_bar(x) for x in bars[-120:]):continue
            h=bars[-120:]
            turnover=h[-1]["turnover_krw"]
            if turnover is None or turnover<5e9:continue
            if abs(turnover-float(daily["TurnoverKRW"]))>1:
                raise ValueError("V614_RAW_DAILY_TURNOVER_DIVERGES")
            if h[-1]["close"]!=float(daily["Close"]):
                raise ValueError("V614_RAW_DAILY_CLOSE_DIVERGES")
            liquid+=1
            ff=[];ii=[];good=True
            for d in flowdays:
                a=rawflows[(d,"foreign")].get(t)
                b=rawflows[(d,"institution")].get(t)
                if a is None or b is None or a[0]!=mk or b[0]!=mk:
                    good=False;break
                ff.append(a[1]);ii.append(b[1])
            if not good:continue
            f5=sum(ff);i5=sum(ii)
            if f5+i5<=0:continue
            positive+=1
            if f5>0 and i5>0:both+=1
            if strict&classified:strongbuy+=1
            if [x["date"] for x in h[-5:]]!=flowdays:continue
            m=metrics(h,flowdays,list(zip(ff,ii)))
            qualities=score(m,f5,i5)
            cohort=("HEALTHY_TREND" if qualities["trend_state"]=="UPTREND_OBSERVE"
                 and not qualities["heat_risk"] and
                 m["relative_volume20"]>=.8 and 0<m["return_20d_pct"]<=20
                 else "STRONG_SECTOR" if strict&classified
                 else "DUAL_FI" if f5>0 and i5>0
                 else "RECOVERY" if qualities["trend_state"]=="REBOUND_CONFIRMATION_WAIT"
                 else "GENERAL_FLOW")
            watched.append(dict(ticker=t,name=info["name"],market=mk,
                cohort=cohort,sector_proxy_strong=bool(strict&classified),
                both_fi_5d_positive=f5>0 and i5>0,
                **m,**qualities))
            barsmap[t]=h
        ordering=lambda x:(-x["discovery_index_100"],
            -x["fi_positive_session_count"],-x["last_turnover_krw"],x["ticker"])
        watched.sort(key=ordering)
        pools={
            "HEALTHY_TREND":[x for x in watched if x["cohort"]=="HEALTHY_TREND"],
            "DUAL_FI":[x for x in watched if x["both_fi_5d_positive"]],
            "STRONG_SECTOR":[x for x in watched if x["sector_proxy_strong"]],
            "RECOVERY":[x for x in watched if x["trend_state"]=="REBOUND_CONFIRMATION_WAIT"]}
        top=[];seen=set();quota=Counter()
        def append(x,cohort):
            if x["ticker"] in seen:return
            top.append(x);seen.add(x["ticker"]);quota[cohort]+=1
        for cohort,maxn in COHORT_TARGETS:
            for x in sorted(pools[cohort],key=ordering):
                if quota[cohort]>=maxn:break
                append(x,cohort)
        for x in watched:
            if len(top)>=20:break
            append(x,"BACKFILL")
        risk=sorted([x for x in top if
            risk_priority_reason(x)=="RISK_PRECHECK_WATCH_NOT_ORDER"],
            key=ordering)[:5]
        riskcodes={x["ticker"] for x in risk}
        alltrigger=allfirst=toptrigger=topfirst=riskfirst=topnext=risknext=0
        nextday=days[j+1] if j+1<len(days) else ""
        for rank,x in enumerate(top,1):
            shortlists.append(dict(asof=day,rank=rank,ticker=x["ticker"],
                 name=x["name"],research_group=x["cohort"],
                 discovery_index_not_final80=x["discovery_index_100"],
                 risk_filter_pass=x["ticker"] in riskcodes,
                 confirmed_method_count=0,first_2R_method_count=0,
                 next_session=nextday,trade_approved=False))
        shortlist_idx={(x["asof"],x["ticker"]):x for x in shortlists if x["asof"]==day}
        # All 100+ flow-positive names are checked; keep technical cases
        # outside the balanced Top20 to diagnose premature exclusion.
        for x in watched:
            code=x["ticker"]
            in_top=code in seen
            in_risk=code in riskcodes
            h=barsmap[code]
            candidate=dict(ticker=code,name=x["name"],latest_date=day,
                close=h[-1]["close"],data_source="pykrx",
                instrument_type="COMMON",turnover_source="SOURCE_REPORTED")
            for method in METHODS:
                m=evaluate(candidate,h,day,method,
                    paired={"category":"OHLC_EXACT_MATCH_UNCERTIFIED",
                            "close_equal":True})
                trigger=m["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"
                first,why=first_gate(m)
                second=second_gate(m)
                if trigger:alltrigger+=1
                if first:allfirst+=1
                if in_top and trigger:toptrigger+=1
                if in_top and first:topfirst+=1
                if in_risk and first:riskfirst+=1
                if in_top and trigger:
                    shortlist_idx[(day,code)]["confirmed_method_count"]+=1
                if in_top and first:
                    shortlist_idx[(day,code)]["first_2R_method_count"]+=1
                if not trigger and not first:continue
                reference=m["first_entry_reference"]
                future=[nextday] if nextday else []
                next_candle=None
                if nextday and code in barsmap:
                    nxt=[q for q in history(code) if q["Date"]==nextday]
                    if len(nxt)==1:next_candle=nxt[0]
                touched=False
                if first and next_candle is not None and reference is not None:
                    nlow=float(next_candle["Low"])
                    touched=nlow<=float(reference)
                    if in_top and touched:topnext+=1
                    if in_risk and touched:risknext+=1
                # 5 completed future trading sessions only when j+5 < total.
                fut=days[j+1:j+6] if j+5<len(days) else []
                next5=[q for q in history(code) if q["Date"] in fut] if fut else []
                complete=len(next5)==5
                lows=[float(q["Low"]) for q in next5 if q["Low"]]
                highs=[float(q["High"]) for q in next5 if q["High"]]
                signals.append(dict(asof=day,ticker=code,name=x["name"],
                    market=x["market"],research_group=x["cohort"],
                    is_balanced_top20=in_top,is_risk_top5=in_risk,
                    method=method,signal_status=m["setup"],
                    stop_research=m["stop_reference"],
                    first_limit_research=reference,
                    second_optional_research=m["second_entry_reference"] if second else "",
                    first_net_R=m["first_net_rr"],
                    nearest_ceiling_research=m["nearest_resistance_reference"],
                    first_2R_research=first,second_optional_2R_research=second,
                    next_session=nextday,
                    next_session_limit_below_intraday_low_or_not=(
                        "" if next_candle is None or reference is None else
                        float(next_candle["Low"])>float(reference)),
                    next_session_limit_price_touched_hypothetical=touched,
                    five_trading_session_window_complete=complete,
                    future_5session_observed_min_low=min(lows) if complete else "",
                    future_5session_observed_max_high=max(highs) if complete else "",
                    same_session_fill_stop_order_uncertain=bool(touched),
                    verified_1530_regular_only=False,
                    historical_issuer_PIT_proof=False,
                    historical_financials_PIT_proof=False,
                    final_80_point_buy_approval=False,
                    actual_broker_order_execution_known=False,
                    trade_approved=False))
        summary.append(dict(asof=day,market_symbols=len(market),
          market_common_historic_issuer_PIT_unverified=True,
          common_120bars_turnover50e8=liquid,
          flow_complete_and_net_buy_positive=positive,
          both_investor_net_buy_positive=both,
          strong_proxy_sector_count=len(strict),
          strong_sector_positive_buy_candidates=strongbuy,
          balanced_top20=len(top),risk_watch_top5=len(risk),
          research_confirmed_methods_all_flow_candidates=alltrigger,
          research_first_2R_all_flow_candidates=allfirst,
          research_confirmed_methods_balanced20=toptrigger,
          research_first_2R_balanced20=topfirst,
          research_first_2R_risk_top5=riskfirst,
          next_session=nextday,
          next_session_first_limit_touched_balanced20=topnext,
          next_session_first_limit_touched_risk_top5=risknext,
          broker_actual_execution_known=False,
          verified_real_buy_authorizations=0,trade_approved=False,decision="CASH"))
        coverage.update(
            market_dates=1,valid_strict_broker_approvals=0,
            broad_candidates=positive,top20=len(top),risk_top5=len(risk),
            all_confirmed_method_count=alltrigger,
            all_first_2r_method_count=allfirst)
        print("V614_OCTOBER_DATED_REPLAY_PROGRESS",day,
            "flow",positive,"top20",len(top),"risk5",len(risk),
            "triggers_all",alltrigger,"first_2R_all",allfirst,
            "top20_2R",topfirst,"strict_BUY",0,flush=True)
    report=dict(schema=SCHEMA,source_market_asof="2026-10-23",
        evaluated_dates=days,evaluated_sessions=len(days),
        first_day=days[0],last_day=days[-1],
        issuer_labels_asof23_used_for_historical_replay=True,
        independently_validated_PIT_base_info_on_each_date=False,
        ETF_membership_independent_snapshot_vintage=False,
        restored_OHLCV_independent_1530_regular_only_source=False,
        originally_published_asof_financial_growth_verified=False,
        current_orderbook_lot_and_account_status_verified=False,
        broker_execution_log_available=False,
        user_actual_trades_verified=False,
        full_v613_buy_gate_authorizations=0,
        method_signal_count_all_positive_flow=sum(r["research_confirmed_methods_all_flow_candidates"] for r in summary),
        first_2R_method_count_all_positive_flow=sum(r["research_first_2R_all_flow_candidates"] for r in summary),
        first_2R_method_count_selected_top20=sum(r["research_first_2R_balanced20"] for r in summary),
        first_2R_method_count_risk_top5=sum(r["research_first_2R_risk_top5"] for r in summary),
        possible_next_session_limit_touches_top20=sum(r["next_session_first_limit_touched_balanced20"] for r in summary),
        possible_next_session_limit_touches_risk_top5=sum(r["next_session_first_limit_touched_risk_top5"] for r in summary),
        after_asof_Oct23_prices_not_available=True,
        outcome_known_limit="PRICE_AND_FLOW_OCT23_ONLY",
        no_live_execution_requested_or_authorized=True,
        fees_assumed_pct=0.5,
        future_5session_return_winrate_verified=False,
        trade_approved=False,orders_enabled=False,decision="CASH")
    return report,summary,signals,shortlists

def save(out,meta,daily,signals,shortlists):
    out.mkdir(parents=True,exist_ok=True)
    for file,fields,rows in (
        ("october_replay_v614_daily.csv",DAILY_FIELDS,daily),
        ("october_replay_v614_method_signals.csv",SIGNAL_FIELDS,signals),
        ("october_replay_v614_top20_by_date.csv",TOP_FIELDS,shortlists)):
        with (out/file).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader();w.writerows(rows)
    meta["artifact_sha256"]={fn:digest((out/fn).read_bytes()) for fn in (
        "october_replay_v614_daily.csv",
        "october_replay_v614_method_signals.csv",
        "october_replay_v614_top20_by_date.csv")}
    (out/"october_replay_v614_status.json").write_text(json.dumps(
        meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# 2026년 10월 v6.13 규칙을 과거에 적용했다면 매수했을까?","",
       f"**10월 1~23일 실제 완료 15거래일 조사 · 엄격한 매수승인 {meta['full_v613_buy_gate_authorizations']}건 (CASH)**",
       "실제 증권사 체결 기록을 확인한 것이 아니며 연구용 매매 신호와 다음날 가격 접촉은 별도 계산했습니다.",
       "기준일 2026-10-23에 수집한 종목기본정보/ETF 구성의 과거 독립 PIT 증명과 정규장 15:30 분리는 불완전하여 "+
       "추정 체결을 실제 주문으로 간주하지 않습니다.","",
       "| 날짜 | 5일수급+거래대금 감시 | 연구 Top20 | 위험 Top5 | 전체 감시 기술신호 | 전체 1차 2R | Top20 1차 2R | 최종 승인 |",
       "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in daily:
        lines.append(f"| {r['asof']} | {r['flow_complete_and_net_buy_positive']} | "+
          f"{r['balanced_top20']} | {r['risk_watch_top5']} | "+
          f"{r['research_confirmed_methods_all_flow_candidates']} | "+
          f"{r['research_first_2R_all_flow_candidates']} | "+
          f"{r['research_first_2R_balanced20']} | 0 |")
    lines+=["","## 후속 지정가 가정(실전 체결 아님)",
        f"- 일봉 1차 가격+피벗 손절+0.5% 비용반영 2R 연구 통과: 전체 수급 감시 "+
         f"{meta['first_2R_method_count_all_positive_flow']}건, Top20 "+
         f"{meta['first_2R_method_count_selected_top20']}건, Top5 "+
         f"{meta['first_2R_method_count_risk_top5']}건.",
        f"- 다음 1거래일 일봉 저가가 1차 가격에 도달했던 경우(체결 가능성의 상한 연구): "+
         f"Top20 {meta['possible_next_session_limit_touches_top20']}건, "+
         f"Top5 {meta['possible_next_session_limit_touches_risk_top5']}건.",
        "- 시가 갭, 한 일봉 안 고가·저가 순서, 미체결 지정가, 호가 잔량, 수수료·슬리피지, "+
        "실제 계좌 현금은 확인하지 못했으므로 실제 주문·수익률·승률로 표시하지 않았습니다.",
        "- 10월 23일 이후 10월 26~30일은 아직 오지 않았으므로 데이터도 성과도 계산하지 않았습니다.",
        "", "## Required Next Data",
        "거래일별 독립 정규장 15:30 가격과 시점별 공식 주식유형·산업분류, "+
        "당시 최초 공시된 실적 본문, 사용자의 실제 증권사 체결·주문가능잔고, "+
        "지정가 후 5거래일 가격순서 검증."]
    (out/"october_replay_v614_mobile.md").write_text(
        "\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    for arg in ("--v18","--issuer","--outdir"):
        p.add_argument(arg,type=Path,required=True)
    a=p.parse_args()
    meta,daily,signals,top=main_calc(a.v18,a.issuer)
    save(a.outdir,meta,daily,signals,top)
    print("V614_OCTOBER_15SESSION_SIMULATION",json.dumps({
        k:meta[k] for k in ("evaluated_sessions",
        "method_signal_count_all_positive_flow",
        "first_2R_method_count_all_positive_flow",
        "first_2R_method_count_selected_top20",
        "first_2R_method_count_risk_top5",
        "possible_next_session_limit_touches_top20",
        "full_v613_buy_gate_authorizations","decision")},ensure_ascii=False))
if __name__=="__main__":main()
