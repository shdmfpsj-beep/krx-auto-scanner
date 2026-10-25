#!/usr/bin/env python3
"""v6.12: 100 -> balanced Top20 discovery, no false BUY or fundamentals.

Strict as-of replay of v6.11 frozen observation universe and original v18
daily OHLCV + 5 completed investor-flow dates; 30-day prior OpenDART
filings are title-only, not audited operating-profit acceleration.

Portfolio cap and discovery index are UNVALIDATED research heuristics:
not a final 80-point investment grade, odds, future winner, or entry order.
No future candle, undated sector membership or same-day DART publication.
"""
from __future__ import annotations
import argparse,csv,json,math,re
from collections import Counter,defaultdict
from datetime import date,timedelta
from pathlib import Path
from forward_ledger_v63 import digest,read_json,read_csv
from broad_watch_v611 import SCHEMA as V611, WATCH_FIELDS, num, blocked_issuer
from official_issuer_entry_v610 import SCHEMA as V610,BASIC_SCHEMA,load_basic,is_common
from full_market_scanner_v68 import parse_days,valid_bar
from sector_flow_v69 import load_flows
from dart_dated_evidence_v610 import SOURCE_FIELDS,report_categories

SCHEMA="C3_K100_BALANCED_TOP20_FIVE_DAY_MONEY_QUALITY_V612"
TOP_FIELDS=("rank","asof","ticker","name","market","discovery_cohort",
    "sector_proxy_strong","last_close","last_turnover_krw",
    "foreign_5d_krw","institution_5d_krw","combined_fi_5d_krw",
    "both_fi_5d_positive","fi_positive_session_count",
    "fi_day_positive_foreign_count","fi_day_positive_institution_count",
    "fi_net_share_of_five_day_turnover_pct",
    "return_5d_pct","return_20d_pct","sma20","sma60",
    "sma20_slope_5d_pct","distance_from_sma20_pct",
    "drawdown_from_20d_high_pct","atr14_pct","relative_volume20",
    "trend_state","heat_risk","discovery_index_100",
    "money_score25","price_score25","persistence_score20",
    "liquidity_score15","risk_score15",
    "prior_30d_dart_receipts","prior_30d_earnings_titles",
    "prior_30d_contract_titles","same_day_dart_omitted",
    "positive_fundamental_numbers_verified",
    "prelim_only_not_final80","structure_entry_confirmed",
    "entry1_research","entry2_alternative_research","daily_stop_research",
    "regular_1530_verified","official_sector_PIT_verified",
    "buy_authorized","orders_enabled")
RAW_FIELDS=("ticker","asof","name","market","sector_proxy_strong",
    "discovery_cohort","discovery_index_100","trend_state","heat_risk",
    "both_fi_5d_positive","return_20d_pct","fi_positive_session_count",
    "last_turnover_krw","prior_30d_dart_receipts","trade_approved")
WEIGHTS=dict(money=25,price=25,persistence=20,liquidity=15,risk=15)
COHORT_TARGETS=(("HEALTHY_TREND",10),("DUAL_FI",5),
                ("STRONG_SECTOR",3),("RECOVERY",2))

def bounded(v,lo,hi):
    return max(lo,min(hi,v))

def normalnum(value):
    n=num(value)
    if n is None or not math.isfinite(n):
        raise ValueError("V612_NONFINITE_PRICE_FLOW_VALUE")
    return n

def metrics(history, dates, daily_fi):
    if len(history)<120 or [r["date"] for r in history[-5:]]!=dates:
        raise ValueError("V612_PRICE_DATES_NOT_ALIGNED_WITH_FI")
    b=history
    closes=[normalnum(r["close"]) for r in b]
    highs=[normalnum(r["high"]) for r in b]
    lows=[normalnum(r["low"]) for r in b]
    vals=[normalnum(r["volume"]) for r in b]
    turnovers=[normalnum(r["turnover_krw"]) for r in b]
    def mean(a,n):return sum(a[-n:])/n
    sma20,sma60=mean(closes,20),mean(closes,60)
    sma20prior=sum(closes[-25:-5])/20
    trs=[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),
             abs(lows[i]-closes[i-1])) for i in range(len(b)-14,len(b))]
    atr=sum(trs)/14
    close=closes[-1]
    dayfi=[float(f+i) for f,i in daily_fi]
    if len(dayfi)!=5:raise ValueError("V612_DAILY_FI_NOT_FIVE_SESSIONS")
    return dict(sma20=sma20,sma60=sma60,
        sma20_slope_5d_pct=100*(sma20/sma20prior-1) if sma20prior else 0,
        distance_from_sma20_pct=100*(close/sma20-1) if sma20 else 0,
        return_5d_pct=100*(close/closes[-6]-1),
        return_20d_pct=100*(close/closes[-21]-1),
        drawdown_from_20d_high_pct=100*(1-close/max(highs[-20:])),
        atr14_pct=100*atr/close,
        relative_volume20=vals[-1]/(sum(vals[-21:-1])/20) if sum(vals[-21:-1]) else 0,
        fi_positive_session_count=sum(v>0 for v in dayfi),
        fi_day_positive_foreign_count=sum(f>0 for f,i in daily_fi),
        fi_day_positive_institution_count=sum(i>0 for f,i in daily_fi),
        fi_net_share_of_five_day_turnover_pct=100*sum(dayfi)/sum(turnovers[-5:])
            if sum(turnovers[-5:])>0 else None,
        last_turnover_krw=turnovers[-1],
        close=close)

def score(m, foreign5, inst5):
    """Deterministic component heuristics, not statistically fitted odds."""
    both=foreign5>0 and inst5>0
    fi_component= (15 if both else 8)
    net_share=m["fi_net_share_of_five_day_turnover_pct"]
    fi_component+=round(bounded(max(net_share or 0,0)*1.5,0,10),2)
    fi_component=bounded(fi_component,0,25)
    posret=m["return_20d_pct"]
    price_component= (12 if m["sma20"]>m["sma60"] else 3)
    price_component+= (6 if 0<=posret<=20 else 2 if posret<=35 else 0)
    price_component+= (7 if m["sma20_slope_5d_pct"]>0 else 0)
    persist=round(m["fi_positive_session_count"]*2.2+
        m["fi_day_positive_foreign_count"]*0.9+
        m["fi_day_positive_institution_count"]*0.9,2)
    liq= min(15,round(4+5*bounded(
        math.log10(max(m["last_turnover_krw"],1)/5e9),0,2)
        +2*bounded(m["relative_volume20"]-1,0,3),2))
    heat=(posret>30 or m["distance_from_sma20_pct"]>15 or m["atr14_pct"]>12)
    risk=15
    if heat:risk-=9
    if m["drawdown_from_20d_high_pct"]>12:risk-=5
    if m["atr14_pct"]>8:risk-=4
    if m["return_5d_pct"]<-8:risk-=4
    risk=max(0,risk)
    total=round(fi_component+price_component+persist+liq+risk,2)
    if not (0<=total<=100):raise ValueError("V612_SCORE_COMPONENT_BOUNDS_FAILED")
    if heat:state="HOT_CHASE_AVOID"
    elif m["sma20"]>m["sma60"] and m["return_20d_pct"]>0:
        state="UPTREND_OBSERVE"
    elif m["return_20d_pct"]<0 and m["return_5d_pct"]>0:
        state="REBOUND_CONFIRMATION_WAIT"
    elif m["return_20d_pct"]<0:state="DOWNTREND_WAIT"
    else:state="TRANSITION_WATCH"
    return dict(discovery_index_100=total,money_score25=round(fi_component,2),
        price_score25=round(price_component,2),persistence_score20=round(persist,2),
        liquidity_score15=round(liq,2),risk_score15=risk,
        trend_state=state,heat_risk=heat)

def dart_prior(v18,tickers,asof):
    meta=read_json(v18/"diagnostics/collection_status.json")
    status=meta.get("datasets",{}).get("dart",{})
    if (meta.get("asof")!=asof or
        status.get("status")!="DATE_ONLY_COMPLETE" or
        status.get("exact_publication_time")!="UNAVAILABLE"):
        raise ValueError("V612_DART_DATE_PRECISION_SOURCE_NOT_VERIFIED")
    path=v18/"catalysts/disclosures.csv"
    raw=read_csv(path)
    if (not raw or len(raw)!=status.get("rows")
        or tuple(raw[0].keys())!=SOURCE_FIELDS):
        raise ValueError("V612_DART_SOURCE_COVERAGE_BAD")
    ids=set();strict=defaultdict(list);same=Counter()
    start=date.fromisoformat(asof)-timedelta(days=30)
    for r in raw:
        receipt=r["receipt_no"]
        if receipt in ids or not re.fullmatch(r"[0-9]{14}",receipt):
            raise ValueError("V612_DART_RECEIPT_DUPLICATE")
        ids.add(receipt)
        day=date.fromisoformat(r["receipt_date"])
        if (day>date.fromisoformat(asof) or
            r["published_precision"]!="DAY_ONLY_no_intraday_time"
            or r["source"]!="OPENDART_list"):
            raise ValueError("V612_DART_FUTURE_OR_UNVERIFIED_INTRADAY")
        ticker=r["ticker"]
        if ticker not in tickers:continue
        if day.isoformat()==asof:same[ticker]+=1
        elif start<=day<date.fromisoformat(asof):strict[ticker].append(r)
    return strict,same,digest(path.read_bytes()),len(raw)

def validate_source(v18,watch,issuer):
    w=read_json(watch/"broad_watch_v611_status.json")
    u=read_json(issuer/"issuer_entry_v610_status.json")
    b=read_json(issuer/"basic/krx_basic_v610_status.json")
    if (w.get("schema")!=V611 or u.get("schema")!=V610 or
        w.get("asof")!=u.get("asof") or b.get("asof")!=w.get("asof")
        or w.get("trade_approved") is not False or
        w.get("orders_enabled") is not False or
        u.get("trade_approved") is not False or
        u.get("orders_enabled") is not False or
        w.get("regular_1530_session_certified") is not False or
        u.get("exact_regular_1530_prices_verified") is not False or
        w.get("final_80_score_verified") is not False or
        b.get("official_base_usable") is not True or
        not w.get("broad_radar_universe_untouched_by_old_52_candidate_filter")):
        raise ValueError("V612_FROZEN_PREDECESSOR_ASOF_OR_BUY_POLICY_INVALID")
    info=load_basic(issuer/"basic",b)
    allrows=read_csv(watch/"broad_watch_v611_all.csv")
    if len(allrows)!=w["official_common_120day_liquid_5d_positive_FI"]:
        raise ValueError("V612_WATCH_UNIVERSE_COUNT_MISMATCH")
    ids={r["ticker"] for r in allrows}
    if len(ids)!=len(allrows) or len(ids)<1:
        raise ValueError("V612_DUPLICATE_OR_EMPTY_WATCH")
    if len(set(w["observed_watches"]["broad_flow_watch"]))!=w["group_counts"]["broad_flow_watch"]:
        raise ValueError("V612_BROAD_WATCH_DISPLAY_SET_MISMATCH")
    audit=read_csv(watch/"broad_watch_v611_full_audit.csv")
    if len(audit)!=w["full_market_universe"] or len(set(r["ticker"] for r in audit))!=len(audit):
        raise ValueError("V612_FULL_MARKET_AUDIT_NOT_2764_UNIQUE")
    selected={r["ticker"] for r in audit if r["phase"]=="RESEARCH_WATCH"}
    if selected!=ids:
        raise ValueError("V612_AUDIT_AND_UNIVERSE_DIFFER")
    for r in allrows:
        ticker=r["ticker"]
        if (r["asof"]!=w["asof"] or r["orders_enabled"]!="False"
            or r["trade_approved"]!="False"
            or r["industry_PIT_verified"]!="False"
            or r["regular_1530_certified"]!="False"
            or not is_common(info.get(ticker))
            or r["market"]!=info[ticker]["market"]
            or blocked_issuer(info[ticker]["name"],"HEALTH" in r["sector_proxy_observation"].split(";"))):
            raise ValueError("V612_COMMON_DATE_HEALTH_OR_BUY_INVALID")
    return w,u,allrows,audit

def build(v18,watch,issuer):
    w,u,rows,audit=validate_source(v18,watch,issuer)
    day=w["asof"]
    vstatus=read_json(v18/"diagnostics/collection_status.json")
    if vstatus.get("asof")!=day or vstatus.get("orders_enabled") is not False:
        raise ValueError("V612_MARKET_ASOF_WRONG")
    for market,sha in u["v68_market_sha256"].items():
        path=v18/"market/daily_prices"/market/(day+".csv")
        if not path.is_file() or digest(path.read_bytes())!=sha:
            raise ValueError("V612_KRX_EOD_DATED_MARKET_SHA_MISMATCH")
    for relative,sha in u["v69_flow_sha256"].items():
        path=v18/relative
        if not path.is_file() or digest(path.read_bytes())!=sha:
            raise ValueError("V612_FIVE_DAY_FI_FLOW_SHA_MISMATCH")
    dates, flows, hashes=load_flows(v18,day)
    if hashes!=u["v69_flow_sha256"] or len(dates)!=5 or dates[-1]!=day:
        raise ValueError("V612_COMPLETE_5_SESSION_FLOW_MISSING")
    darts,same,disclosure_sha,disclosure_count=dart_prior(v18,{x["ticker"] for x in rows},day)
    scored=[]
    for row in rows:
        ticker=row["ticker"]
        path=v18/"market/prices"/(ticker+".csv")
        if not path.is_file():raise ValueError("V612_MARKET_WIDE_STOCK_HISTORY_MISSING")
        candles,problem=parse_days(read_csv(path),ticker,date.fromisoformat(day))
        if (problem or len(candles)<120 or
            any(not valid_bar(x) for x in candles[-120:])):
            raise ValueError("V612_120_COMPLETED_PRICE_HISTORY_CHANGED")
        c=candles[-120:]
        if (row["last_close"]!=str(c[-1]["close"]) and
            float(row["last_close"])!=c[-1]["close"]):
            raise ValueError("V612_LAST_CLOSE_NOT_FROZEN")
        lastturn=normalnum(row["actual_turnover_krw"])
        if lastturn!=c[-1]["turnover_krw"]:
            raise ValueError("V612_SOURCE_REPORTED_KRW_TURNOVER_CHANGED")
        fs=[];ins=[]
        for datekey in dates:
            a=flows[(datekey,"foreign")].get(ticker)
            b=flows[(datekey,"institution")].get(ticker)
            if a is None or b is None or a[0]!=row["market"] or b[0]!=row["market"]:
                raise ValueError("V612_HISTORIC_MISSING_FI_NOT_ZERO")
            fs.append(a[1]);ins.append(b[1])
        foreign,inst=sum(fs),sum(ins)
        if (abs(foreign-normalnum(row["foreign_net5_krw"]))>1
            or abs(inst-normalnum(row["institution_net5_krw"]))>1
            or abs(foreign+inst-normalnum(row["combined_net5_krw"]))>1
            or (foreign>0 and inst>0)!=(row["two_sided_fi_positive"]=="True")):
            raise ValueError("V612_FI_NET_BUY_RAW_REPLAY_MISMATCH")
        m=metrics(c,dates,list(zip(fs,ins)))
        if abs(m["return_20d_pct"]-normalnum(row["return20_pct"]))>0.002:
            raise ValueError("V612_FROZEN_20D_RETURN_MISMATCH")
        if abs(m["relative_volume20"]-normalnum(row["rvol20"]))>0.002:
            raise ValueError("V612_FROZEN_RVOL20_MISMATCH")
        scoredata=score(m,foreign,inst)
        types=[r for r in darts[ticker]]
        categories=[z for r in types for z in report_categories(r["report_name"])]
        cohort=("HEALTHY_TREND" if scoredata["trend_state"]=="UPTREND_OBSERVE"
            and not scoredata["heat_risk"] and
            m["relative_volume20"]>=0.8 and
            0<m["return_20d_pct"]<=20
            else "STRONG_SECTOR" if row["in_strong_sector_proxy"]=="True"
            else "DUAL_FI" if foreign>0 and inst>0
            else "RECOVERY" if scoredata["trend_state"]=="REBOUND_CONFIRMATION_WAIT"
            else "GENERAL_FLOW")
        record=dict(asof=day,ticker=ticker,name=row["name"],
            market=row["market"],discovery_cohort=cohort,
            sector_proxy_strong=row["sector_proxy_strong"],
            last_close=m["close"],last_turnover_krw=m["last_turnover_krw"],
            foreign_5d_krw=foreign,institution_5d_krw=inst,
            combined_fi_5d_krw=foreign+inst,
            both_fi_5d_positive=foreign>0 and inst>0,
            fi_positive_session_count=m["fi_positive_session_count"],
            fi_day_positive_foreign_count=m["fi_day_positive_foreign_count"],
            fi_day_positive_institution_count=m["fi_day_positive_institution_count"],
            fi_net_share_of_five_day_turnover_pct=round(
                m["fi_net_share_of_five_day_turnover_pct"],3),
            return_5d_pct=round(m["return_5d_pct"],3),
            return_20d_pct=round(m["return_20d_pct"],3),
            sma20=round(m["sma20"],3),sma60=round(m["sma60"],3),
            sma20_slope_5d_pct=round(m["sma20_slope_5d_pct"],3),
            distance_from_sma20_pct=round(m["distance_from_sma20_pct"],3),
            drawdown_from_20d_high_pct=round(m["drawdown_from_20d_high_pct"],3),
            atr14_pct=round(m["atr14_pct"],3),
            relative_volume20=round(m["relative_volume20"],3),
            **scoredata,
            prior_30d_dart_receipts=len(types),
            prior_30d_earnings_titles=categories.count("EARNINGS_OR_FINANCIAL_TITLE"),
            prior_30d_contract_titles=categories.count("CONTRACT_OR_ORDER_TITLE"),
            same_day_dart_omitted=same[ticker],
            positive_fundamental_numbers_verified=False,
            prelim_only_not_final80=True,structure_entry_confirmed=False,
            entry1_research=None,entry2_alternative_research=None,
            daily_stop_research=None,regular_1530_verified=False,
            official_sector_PIT_verified=False,buy_authorized=False,
            orders_enabled=False)
        scored.append(record)
    if len(scored)!=len(rows):raise ValueError("V612_MARKET_LIST_NOT_SCORED")
    key=lambda r:(-r["discovery_index_100"],-r["fi_positive_session_count"],
                  -r["last_turnover_krw"],r["ticker"])
    scored.sort(key=key)
    chosen=[];selected=set();cohort_counts=Counter()
    def add(item,slot):
        if item["ticker"] in selected:return False
        chosen.append(dict(item));selected.add(item["ticker"])
        cohort_counts[slot]+=1
        return True
    # Four queues: strong sector is allowed to be in a healthy uptrend too.
    # Every queue has a hard slot quota, so no single hot trading theme can
    # replace the entire Top20 as in v6.11. Missing queues do not invent stocks.
    pools={
        "HEALTHY_TREND":[x for x in scored if x["discovery_cohort"]=="HEALTHY_TREND"],
        "DUAL_FI":[x for x in scored if x["both_fi_5d_positive"]],
        "STRONG_SECTOR":[x for x in scored if x["sector_proxy_strong"]],
        "RECOVERY":[x for x in scored if x["trend_state"]=="REBOUND_CONFIRMATION_WAIT"]}
    for group,limit in COHORT_TARGETS:
        for candidate in pools[group]:
            if cohort_counts[group]>=limit:break
            add(candidate,group)
    for candidate in scored:
        if len(chosen)>=20:break
        add(candidate,"BACKFILL")
    for i,row in enumerate(chosen,1):row["rank"]=i
    outcome=dict(schema=SCHEMA,asof=day,
        v611_market_watched=len(rows),
        v611_total_market=w["full_market_universe"],
        source_v18_run_id=u.get("v68_source_run_id") or "",
        source_original_market_SHA256=u["v68_market_sha256"],
        source_original_fi_flow_SHA256=u["v69_flow_sha256"],
        source_dart_date_only_SHA256=disclosure_sha,
        completed_fi_dates=dates,
        original_date_only_dart_receipts=disclosure_count,
        prior_date_catalyst_titles_not_verified_growth=True,
        all_candidates_recalculated_from_120_frozen_bars=True,
        five_day_investor_reconciliation_complete=True,
        missing_fundamentals_are_neither_zero_nor_positive=True,
        top20_count=len(chosen),queue_quota_targets=dict(COHORT_TARGETS),
        queue_actual=dict(cohort_counts),different_market_symbols=len({r["ticker"] for r in chosen}),
        top20_tickers=[r["ticker"] for r in chosen],
        top5_watch_only=[r["ticker"] for r in chosen[:5]],
        healthy_trend_total=len(pools["HEALTHY_TREND"]),
        both_investor_total=len(pools["DUAL_FI"]),
        strong_proxy_total=len(pools["STRONG_SECTOR"]),
        rebound_watch_total=len(pools["RECOVERY"]),
        overheat_flags_in_top20=sum(r["heat_risk"] for r in chosen),
        strict_setup_and_cost_adjusted_2r_approvals=0,
        final_80_score_verified=False,financial_growth_verified=False,
        regular_1530_verified=False,industry_PIT_verified=False,
        backtest_5day_forward_evaluated=False,
        trade_approved=False,orders_enabled=False,decision="CASH")
    return outcome,scored,chosen

def save(folder,manifest,allrows,top20):
    folder.mkdir(parents=True,exist_ok=True)
    def csvout(name,columns,rows):
        p=folder/name
        with p.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore")
            w.writeheader();w.writerows(rows)
        return digest(p.read_bytes())
    shas={}
    shas["top20_quality_v612_all.csv"]=csvout("top20_quality_v612_all.csv",
        ("ticker","asof","name","market","sector_proxy_strong","discovery_cohort",
         "discovery_index_100","trend_state","heat_risk","both_fi_5d_positive",
         "return_20d_pct","fi_positive_session_count","last_turnover_krw",
         "prior_30d_dart_receipts","buy_authorized"),allrows)
    shas["top20_quality_v612_selected.csv"]=csvout("top20_quality_v612_selected.csv",
        ("rank",)+TOP_FIELDS,top20)
    manifest["output_file_sha256"]=shas
    (folder/"top20_quality_v612_status.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# v6.12 100종목 → 균형 잡힌 Top20 연구 후보","",
        f"{manifest['asof']} 완료 시장일 · **CASH / 주문 0**",
        f"원본 후보 {manifest['v611_market_watched']}개 중 120일 가격·최근5일 기관/외국인 "+
         "수급을 다시 대조하고 진단적으로 20개 선정.",
        "연구지수(0~100)는 검증된 상승확률이나 최종 80점이 아니며, "+
          "누락된 재무 실적은 0 또는 우량으로 간주하지 않았습니다.",
        "업종 공식 PIT·정규장 15:30·재무 수치·2R 조건 미인증으로 매수 후보가 아닙니다.","",
        "## 20개 균형 연구 종목 (가격은 해당 날짜 참고만)","",
        "| 순번 | 종목 | 관찰그룹 | 연구지수 | 20일 주가변화 | 순매수 지속(5일) | 실측 거래대금(억원) |",
        "|---|---|---|---:|---:|---:|---:|"]
    for r in top20:
        lines.append(f"| {r['rank']} | {r['name']} ({r['ticker']}) | {r['discovery_cohort']} | "+
          f"{r['discovery_index_100']:.1f} | {r['return_20d_pct']:+.1f}% | "+
          f"{r['fi_positive_session_count']}/5 | {r['last_turnover_krw']/1e8:,.1f} |")
    lines+=["","### 매수 승인을 막는 검증항목",
       "- 정규장 전용 15:30 가격/호가 및 PIT 종목 산업분류, 실제 재무 실적/계약 공시본문",
       "- 구조저점 및 1차/2차 대체매수가의 수수료·슬리피지 후 2R, 계좌 체결가능 수량",
       "- 다음 5거래일 진짜 미래 관측치가 없는 2026-10-23 시점에서는 백테스트 승률 미공개",
       "", "## Required Next Data",
       "OpenDART 분기/연간 매출·영업이익 비교가능 기간·공시 최초 시각, "+
       "KRX 정규장 15:30 공식 분리 자료, 5일 전진검증, 계좌 보유주/주문가능현금."]
    (folder/"top20_quality_v612_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    for name in ("--v18","--watch","--issuer","--outdir"):
        p.add_argument(name,type=Path,required=True)
    a=p.parse_args()
    meta,allrows,top20=build(a.v18,a.watch,a.issuer)
    save(a.outdir,meta,allrows,top20)
    print("V612_FIVE_SESSION_TOP20_RESEARCH",json.dumps({
        k:meta[k] for k in ("asof","v611_market_watched","top20_count",
        "queue_actual","healthy_trend_total","overheat_flags_in_top20",
        "top5_watch_only","decision")},ensure_ascii=False))
if __name__=="__main__":main()
