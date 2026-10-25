#!/usr/bin/env python3
"""v6.11 widen WATCH coverage BEFORE setup/sector veto. No orders, no BUY.

Based on the unchanged 2764-code v18 as-of market plus KRX official base
share-kind records, frozen v6.8 EOD SHA and v6.9 five-day FI input.
Watch tiers:
  (1) strong ETF-sector proxy + liquidity + positive net foreign+institution,
  (2) across ALL ordinary/common KRX market names with liquid money buying,
  (3) both separate foreign and institution five-session net buy positive.
Never promote third weak sector, unverified biotech, lookahead, or candidates
as finalized trade recommendations. 1st/2nd alternative and structural stop
are research-only and NEVER average down the same filled position.
"""
from __future__ import annotations
import argparse,csv,json,math,re
from collections import Counter,defaultdict
from pathlib import Path
from datetime import date
from forward_ledger_v63 import read_json,read_csv,digest
from full_market_scanner_v68 import SCHEMA as V68,parse_days,valid_bar
from entry_strategy_v58 import evaluate as entry_eval,METHODS
from official_issuer_entry_v610 import SCHEMA as V610,BASIC_SCHEMA,is_common,load_basic,risk_valid
from sector_flow_v69 import SCHEMA as V69,load_flows,read_sector_evidence,read_memberships

SCHEMA="C3_K100_BROAD_COVERAGE_RISK_FIRST_WATCH_V611"
MIN_TURNOVER_C3=5_000_000_000
MIN_HISTORY=120
PHARMA_TITLE=("바이오","제약","신약","의약","메디","진단","헬스","셀트리온",
    "알테오젠","에이비엘","약품","녹십자","종근당","의료","보령")
OTHER_SPECIAL=("스팩","SPAC","ETF","ETN","리츠","REIT","인버스","레버리지")
WATCH_FIELDS=("asof","ticker","name","market","sector_proxy_strong",
    "sector_proxy_observation","last_close","actual_turnover_krw",
    "return20_pct","rvol20","foreign_net5_krw","institution_net5_krw",
    "combined_net5_krw","two_sided_fi_positive","in_strong_sector_proxy",
    "money_flow_rank_index","confirmed_setups","risk_2r_structures",
    "watch_tier","nearest_structure_stop_research",
    "first_alternative_research","second_alternative_research",
    "nearest_resistance_research","best_cost_adjusted_rr_research",
    "industry_PIT_verified","regular_1530_certified",
    "financial_growth_verified","final_80_score_verified",
    "trade_approved","orders_enabled")
AUDIT_FIELDS=("asof","ticker","name","market","phase",
    "reason","official_common_group","history_valid_120",
    "turnover_krw","flow_complete_5days","foreign_plus_institution_net5",
    "strong_sector_proxy","trade_approved","orders_enabled")

def num(s):
    try:
        if isinstance(s,bool) or s in ("",None):return None
        n=float(s)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None

def blocked_issuer(name,health):
    s=str(name or "").upper()
    return bool(health or any(word.upper() in s for word in PHARMA_TITLE+OTHER_SPECIAL))

def gate_archives(v18,scan,flows,issuer):
    p=read_json(scan/"full_market_v68_status.json")
    f=read_json(flows/"sector_money_v69_status.json")
    b=read_json(issuer/"issuer_entry_v610_status.json")
    bm=read_json(issuer/"basic/krx_basic_v610_status.json")
    status=read_json(v18/"diagnostics/collection_status.json")
    if (p.get("schema")!=V68 or f.get("schema")!=V69
        or b.get("schema")!=V610 or bm.get("schema")!=BASIC_SCHEMA
        or p["asof"]!=f["asof"] or f["asof"]!=b["asof"]
        or b["asof"]!=bm["asof"] or bm["asof"]!=status["asof"]
        or not p["official_krx_and_v18_latest_all_fields_match"]
        or p.get("trade_approved") is not False
        or f.get("trade_approved") is not False
        or b.get("trade_approved") is not False
        or status.get("orders_enabled") is not False
        or b.get("exact_regular_1530_prices_verified") is not False
        or bm.get("official_base_usable") is not True
        or f.get("ETF_membership_not_independent_PIT") is not True
        or b.get("full_market_initial_codes")!=p.get("asof_universe_count")
        or f.get("v68_market_sha256")!=p.get("market_v18_daily_source_sha256")
        or b.get("v68_market_sha256")!=p.get("market_v18_daily_source_sha256")
        or b.get("v69_flow_sha256")!=f.get("flow_source_sha256")):
        raise ValueError("V611_ASOF_PROVENANCE_SECTOR_OR_PRICE_POLICY_FAILED")
    for mk,sha in p["market_v18_daily_source_sha256"].items():
        file=v18/"market/daily_prices"/mk/(p["asof"]+".csv")
        if not file.exists() or digest(file.read_bytes())!=sha:
            raise ValueError("V611_FULL_KRX_DAILY_SOURCE_SHA_CHANGED")
    for rel,sha in f["flow_source_sha256"].items():
        file=v18/rel
        if not file.is_file() or digest(file.read_bytes())!=sha:
            raise ValueError("V611_FIVE_DAYS_INVESTOR_RAW_SHA_CHANGED")
    if p.get("asof_universe_count")!=bm["market_counts"]["KOSPI"]+bm["market_counts"]["KOSDAQ"]:
        raise ValueError("V611_BASIC_MARKET_UNIVERSE_COUNT_DRIFT")
    return p,f,b,bm

def build(v18,scan,flows,issuer):
    p,f,b,bm=gate_archives(v18,scan,flows,issuer)
    asof=p["asof"]
    infos=load_basic(issuer/"basic",bm)
    sectors=read_csv(flows/"sector_money_v69_all.csv")
    if len(sectors)!=f["total_proxy_sectors"]:
        raise ValueError("V611_SECTOR_RESEARCH_COUNT_MISMATCH")
    strict={r["sector_id"] for r in sectors if r["strength_status"]=="PROXY_STRONG_RESEARCH"}
    if strict!=set(f["strict_strong_sectors"]):
        raise ValueError("V611_STRONG_SECTOR_APPROVAL_OR_REFERENCE_DRIFT")
    sr,_=read_sector_evidence(v18,asof)
    members,usable,memsha=read_memberships(v18,asof,sr)
    if memsha!=f["membership_source_sha256"]:
        raise ValueError("V611_MEMBER_RAW_SHA_CHANGED")
    member_by_ticker=defaultdict(set)
    for row in sr:
        if usable.get(row["sector_id"]):
            for ticker in members[(row["sector_id"],row["snapshot_date"])]:
                member_by_ticker[ticker].add(row["sector_id"])
    daylist,ledger,hashes=load_flows(v18,asof)
    if hashes!=f["flow_source_sha256"] or daylist!=f["validated_flow_dates"]:
        raise ValueError("V611_FIVE_DAY_EXACT_DATETIME_OR_FLOW_HASH_DRIFT")
    diary={};counts=Counter()
    for mk in ("KOSPI","KOSDAQ"):
        r=read_csv(v18/"market/daily_prices"/mk/(asof+".csv"))
        for x in r:
            ticker=x["ticker"]
            if ticker in diary or x["Date"]!=asof or len(ticker)!=6:
                raise ValueError("V611_DUPLICATE_OR_BAD_DATED_SECURITY")
            diary[ticker]=(mk,x)
    if len(diary)!=p["asof_universe_count"]:
        raise ValueError("V611_FULL_MARKET_UNIVERSE_COVERAGE_MISSING")
    audits=[];radar=[];method_total=0;method_confirm=0;good_rr=0
    for ticker,(mk,dayrow) in sorted(diary.items()):
        name=infos.get(ticker,{}).get("name","")
        typ=is_common(infos.get(ticker))
        member=member_by_ticker.get(ticker,set())
        def write_audit(phase,reason,history_ok=False,turnover=None,
                        flow_complete=False,total=None):
            counts[reason]+=1
            audits.append(dict(asof=asof,ticker=ticker,name=name,market=mk,
                phase=phase,reason=reason,official_common_group=typ,
                history_valid_120=history_ok,
                turnover_krw=turnover,flow_complete_5days=flow_complete,
                foreign_plus_institution_net5=total,
                strong_sector_proxy=";".join(sorted(member&strict)),
                trade_approved=False,orders_enabled=False))
        if not typ or infos[ticker]["market"]!=mk:
            write_audit("EXCLUDED","NOT_OFFICIAL_COMMON_SHARE")
            continue
        if blocked_issuer(name,"HEALTH" in member):
            write_audit("EXCLUDED","NAME_OR_HEALTHCARE_SPECIAL_STOCK_EXCLUDED")
            continue
        hfile=v18/"market/prices"/(ticker+".csv")
        if not hfile.is_file():
            write_audit("EXCLUDED","HISTORICAL_MARKET_FILE_NOT_FOUND")
            continue
        bars,err=parse_days(read_csv(hfile),ticker,date.fromisoformat(asof))
        if err or len(bars)<MIN_HISTORY:
            write_audit("EXCLUDED","HISTORY_TOO_SHORT_OR_MISSING_FINAL_DAY")
            continue
        last=bars[-MIN_HISTORY:]
        if not all(valid_bar(x) for x in last):
            write_audit("EXCLUDED","INVALID_120_DAY_OHLCV_UNREPAIRED")
            continue
        if any(num(last[-1][k])!=num(dayrow[k.capitalize()])
               for k in ("open","high","low","close","volume")):
            raise ValueError("V611_LAST_BAR_DAILY_SOURCE_MISMATCH")
        turnover=num(dayrow.get("TurnoverKRW"))
        if turnover is None or turnover<=0 or num(last[-1]["turnover_krw"])!=turnover:
            raise ValueError("V611_DAY_TURNOVER_OR_HISTORY_SOURCE_MISMATCH")
        if turnover<MIN_TURNOVER_C3:
            write_audit("WATCH_BELOW_GATE","BELOW_C3_50E8_TURNOVER",True,turnover)
            continue
        counts["TURNOVER_50E8_VERIFIED"]+=1
        source5={}
        full=True
        for invest in ("foreign","institution"):
            points=[ledger[(d,invest)].get(ticker) for d in daylist]
            if any(x is None or x[0]!=mk for x in points):
                full=False
            else:source5[invest]=sum(x[1] for x in points)
        if not full:
            write_audit("FLOW_UNKNOWN","FIVE_DAY_INVESTOR_ROWS_INCOMPLETE",True,turnover)
            continue
        total=sum(source5.values())
        if total<=0:
            write_audit("FLOW_NEGATIVE","NONPOSITIVE_COMBINED_FIVE_DAY_BUY",True,turnover,True,total)
            continue
        counts["FLOW_POSITIVE_ALL_MARKET"]+=1
        both=all(source5[k]>0 for k in source5)
        if both:counts["BOTH_FI_POSITIVE"]+=1
        isstrong=bool(member&strict)
        if isstrong:counts["STRONG_SECTOR_FLOW_POSITIVE_LIQUID"]+=1
        close=last[-1]["close"]
        close20=last[-21]["close"]
        meanvol=sum(x["volume"] for x in last[-21:-1])/20
        rvol=last[-1]["volume"]/meanvol if meanvol>0 else 0
        ret20=(close/close20-1)*100
        candidate=dict(ticker=ticker,name=name,latest_date=asof,
            close=close,data_source="pykrx",instrument_type="COMMON",
            turnover_source="SOURCE_REPORTED")
        methods=[entry_eval(candidate,last,asof,m,
            paired=dict(category="OHLC_EXACT_MATCH_UNCERTIFIED",close_equal=True))
            for m in METHODS]
        method_total+=len(methods)
        confirmed=[m for m in methods if m["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"]
        good=[m for m in methods if risk_valid({
            "setup":m["setup"],"first_entry_reference":m["first_entry_reference"],
            "second_entry_reference":m["second_entry_reference"],
            "stop_reference":m["stop_reference"],
            "nearest_resistance_reference":m["nearest_resistance_reference"],
            "first_net_rr":m["first_net_rr"],"second_net_rr":m["second_net_rr"],
            "structure_reference_valid":m["technical_research_ready"]})[0]]
        method_confirm+=len(confirmed);good_rr+=len(good)
        chosen=next(iter(sorted(good,key=lambda x:-float(x["first_net_rr"]))),None)
        if chosen is None:chosen=confirmed[0] if confirmed else None
        # descriptive screen priority, NOT claimed success likelihood or 80-gate.
        pri=round(max(-20,min(20,ret20))/2
            +min(15,rvol*3)
            +min(15,math.log10(max(total,1))*1.2)
            +(10 if both else 0)
            +(12 if isstrong else 0),2)
        radar.append(dict(asof=asof,ticker=ticker,name=name,market=mk,
            sector_proxy_strong=";".join(sorted(member&strict)),
            sector_proxy_observation=";".join(sorted(member)),
            last_close=close,actual_turnover_krw=turnover,
            return20_pct=round(ret20,3),rvol20=round(rvol,3),
            foreign_net5_krw=round(source5["foreign"],2),
            institution_net5_krw=round(source5["institution"],2),
            combined_net5_krw=round(total,2),
            two_sided_fi_positive=both,in_strong_sector_proxy=isstrong,
            money_flow_rank_index=pri,
            confirmed_setups=len(confirmed),risk_2r_structures=len(good),
            watch_tier="STRONG_SECTOR_RESEARCH" if isstrong else
              ("BOTH_INVESTORS_POSITIVE" if both else "GENERAL_MONEY_FLOW"),
            nearest_structure_stop_research=chosen["stop_reference"] if chosen else None,
            first_alternative_research=chosen["first_entry_reference"] if chosen else None,
            second_alternative_research=chosen["second_entry_reference"] if chosen else None,
            nearest_resistance_research=chosen["nearest_resistance_reference"] if chosen else None,
            best_cost_adjusted_rr_research=chosen["first_net_rr"] if chosen else None,
            industry_PIT_verified=False,regular_1530_certified=False,
            financial_growth_verified=False,final_80_score_verified=False,
            trade_approved=False,orders_enabled=False))
        write_audit("RESEARCH_WATCH","FLOW_AND_C3_LIQUID_120DAY_VALID",True,turnover,True,total)
    if len(audits)!=len(diary):
        raise ValueError("V611_ALL_MARKET_STOCKS_NOT_ACCOUNTED_FOR")
    def ranked(items):
        return sorted(items,key=lambda x:(
            -x["money_flow_rank_index"],-x["actual_turnover_krw"],x["ticker"]))
    strong=ranked([x for x in radar if x["in_strong_sector_proxy"]])
    broad=ranked(radar)
    both=ranked([x for x in radar if x["two_sided_fi_positive"]])
    moderate=ranked([x for x in radar if
        0<x["return20_pct"]<=20 and x["rvol20"]>=1])
    samples={"strong_sector_watch":strong[:20],
        "broad_flow_watch":broad[:20],
        "two_sided_investors_watch":both[:20],
        "moderate_trend_watch":moderate[:20]}
    outcome=dict(schema=SCHEMA,asof=asof,
        full_market_universe=len(diary),
        official_common_120day_50e8_liquid=counts["TURNOVER_50E8_VERIFIED"],
        official_common_120day_liquid_5d_positive_FI=len(radar),
        both_investors_5d_net_buy_positive=counts["BOTH_FI_POSITIVE"],
        strong_proxy_sector_5d_positive_liquid=len(strong),
        strong_proxy_sector_last20day_declining_count=sum(x["return20_pct"]<0 for x in strong),
        positive20day_money_flow_count=sum(x["return20_pct"]>0 for x in radar),
        moderate_trend_no_chase_research_count=len(moderate),
        twentieth_day_return_above_20pct_count=sum(x["return20_pct"]>20 for x in radar),
        strong_sector_ids=sorted(strict),
        broad_radar_universe_untouched_by_old_52_candidate_filter=True,
        raw_full_market_and_liquidity_coverage_by_exclusion_reason=dict(counts),
        analyzed_pattern_method_rows=method_total,
        confirmed_research_trigger_rows=method_confirm,
        both_limit_alternatives_2R_research_rows=good_rr,
        watched_ordinary_share_PIT_historic_unverified=True,
        ETF_membership_authoritative_industry=False,
        financial_and_catalyst_verified=False,
        regular_1530_session_certified=False,
        backtested_5_session_expected_winrate=False,
        final_80_score_verified=False,
        orders_enabled=False,trade_approved=False,decision="CASH",
        group_counts={key:len(value) for key,value in samples.items()},
        observed_watches={key:[s["ticker"] for s in value] for key,value in samples.items()})
    return outcome,radar,audits,samples

def save(outdir,report,watch,audit,groups):
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"broad_watch_v611_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for fname,rows,cols in (
      ("broad_watch_v611_all.csv",watch,WATCH_FIELDS),
      ("broad_watch_v611_full_audit.csv",audit,AUDIT_FIELDS)):
        with (outdir/fname).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore")
            w.writeheader();w.writerows(rows)
    lines=["# v6.11 KRX 넓은 발굴 · 엄격한 매수 승인 분리","",
       f"**{report['asof']} 데이터 기준 · CASH / 승인된 매수 0**",
       f"전체 {report['full_market_universe']}개 중 보통주·120일 이력·50억원 유동성 "+
       f"{report['official_common_120day_50e8_liquid']}개, "+
       f"5일 외국인+기관 합산 순매수 양수 "+
       f"{report['official_common_120day_liquid_5d_positive_FI']}개, "+
       f"둘 다 순매수 {report['both_investors_5d_net_buy_positive']}개.",
       f"기존 52개 조기 기술패턴 필터를 통과하지 않아도 강한 섹터 연구 "+
       f"{report['strong_proxy_sector_5d_positive_liquid']}종목 추적. 그중 "+
       f"{report['strong_proxy_sector_last20day_declining_count']}종목은 최근 20일 하락으로 매수에는 주의.",
       f"돈 유입 관찰군 중 20일 완만한 상승(0~20%) 및 거래량 전20일 평균 이상 "+
       f"{report['moderate_trend_no_chase_research_count']}종목(미검증 연구기준).",
       "이 수치에는 이름과 ETF 헬스케어 구성으로 의심되는 제약·바이오가 연구 제외되었습니다.",
       "", "## 그룹별 넓은 상위 관찰 대상 (실제 매수가 아님)"]
    for label,key in (
      ("강한 ETF 섹터·실측 순매수·유동성","strong_sector_watch"),
      ("전체시장 5일 순매수·유동성","broad_flow_watch"),
      ("외국인·기관 각각 5일 순매수","two_sided_investors_watch"),
      ("완만한 상승 0~20%·거래량 전20일 평균 이상","moderate_trend_watch")):
        lines+=["","### "+label, "",
          "| 종목 | 분야 ETF 대용 | 외국인(억) | 기관(억) | 거래대금(억) | 20일 등락률 | 기술자리 |",
          "|---|---|---:|---:|---:|---:|---:|"]
        for c in groups[key]:
            lines.append(f"| {c['name']} ({c['ticker']}) | "+
              f"{c['sector_proxy_strong'] or '분야 미확정'} | "+
              f"{c['foreign_net5_krw']/1e8:+.1f} | "+
              f"{c['institution_net5_krw']/1e8:+.1f} | "+
              f"{c['actual_turnover_krw']/1e8:,.1f} | "+
              f"{c['return20_pct']:+.1f}% | {c['confirmed_setups']} |")
        if not groups[key]:
            lines.append("| 없음 | — | — | — | — | — | — |")
    lines+=["","**매수는 여전히 0건입니다.** 위 전체시장 금융수급은 Open API와 교차 인증된 정규장 15:30 수급/가격으로 확정되지 않았으며 ETF 종목분류가 공식 업종은 아닙니다.",
        "예비 우선순위는 실측 순매수·거래대금·20일 흐름·동반매수 여부의 정렬지수이며 상승확률이나 최종 80점 점수가 아닙니다.",
        "1차/2차 진입은 같은 포지션에 추가 매수하는 방식이 아니며, 두 가격 모두 구조손절과 최소 2R·실제 계좌·정규장 증빙 없이는 주문가로 사용할 수 없습니다.",
        "", "## Required Next Data",
        "KRX 공식 산업 PIT·제약바이오 예외 종목분류, 독립 15:30 정규장 가격, 단일출처 120일 역사검증, 기업재무/공시, 5거래일 전진 검증 및 계좌 현금."]
    (outdir/"broad_watch_v611_mobile.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    for arg in ("--v18","--scan","--flow","--issuer","--outdir"):
        p.add_argument(arg,type=Path,required=True)
    a=p.parse_args()
    r,watch,audit,groups=build(a.v18,a.scan,a.flow,a.issuer)
    save(a.outdir,r,watch,audit,groups)
    print("V611_WIDEN_KRX_WATCH_NOT_BUY",json.dumps({key:r[key] for key in (
       "full_market_universe","official_common_120day_50e8_liquid",
       "official_common_120day_liquid_5d_positive_FI",
       "both_investors_5d_net_buy_positive",
       "strong_proxy_sector_5d_positive_liquid",
       "confirmed_research_trigger_rows","decision")},ensure_ascii=False))
if __name__=="__main__":main()
