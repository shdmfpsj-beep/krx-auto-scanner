#!/usr/bin/env python3
"""C3/K100 v6.8 all-KRX-market as-of screening, research only.

Universe is the full, date-frozen KOSPI+KOSDAQ daily snapshot (NOT the
old 82 cherry-picked recovery candidates). All historical 160+ candles
come from v18 market-WIDE per-stock archived files, with no per-ticker
adjusted=True calls. As-of final OHLCV and actual reported turnover are
compared with the authenticated KRX official EOD API by exact ticker/date.

NOT a 15:30-only source certification, independent historic 120-day KRX
verification, adjusted/unadjusted correction or a PIT common-share audit.
NEVER send orders or treat technical preliminary scores as final 80+.
"""
from __future__ import annotations
import argparse,csv,json,math,re
from collections import Counter
from datetime import date
from pathlib import Path

from entry_strategy_v58 import evaluate,METHODS
from forward_ledger_v63 import read_json,read_csv,digest
from free_structural_v52 import history_check
from krx_official_eod_v65 import official_rows,COLLECT_SCHEMA
from rank_candidates import score as preliminary_score

SCHEMA="C3_K100_FULL_MARKET_SAME_SOURCE_RESEARCH_V68"
DAY_FIELDS=("ticker","Date","Open","High","Low","Close","Volume","TurnoverKRW")
OHLC=("open","high","low","close","volume")
REQUIRED_WARMUP=160
HISTORICAL_BARS_TO_SAVE=120
EXCLUDED_NAME=("제약","바이오","PHARMA","BIOTECH","SPAC","스팩","ETF",
    "ETN","REIT","리츠","인버스","레버리지","우B","우C")
CAND_FIELDS=("ticker","name","market","asof","source_file_sha256",
    "source_latest_ohlcv_vs_krx_eod_verified","history_bars",
    "history_min_160_valid","history_last_120_sha256",
    "instrument_type","instrument_name_exclusion","turnover_source",
    "turnover_krw","close","ma20","ma60","ma120","rvol20",
    "weekly_filter","monthly_filter","breakout",
    "first_pullback_proxy","reversal_proxy",
    "preliminary_c3_score","preliminary_k100_score",
    "preliminary_rank_only","final_80_score_verified","regular_1530_session_certified",
    "trade_approved","orders_enabled")
DIAGNOSTIC_FIELDS=("ticker","name","market","asof","screen_status","reason",
    "history_length","history_valid_160","official_ohlcv_equals_v18",
    "instrument_type","source_file_sha256","trade_approved","orders_enabled")
RESEARCH_FIELDS=("ticker","name","market","asof","method","setup",
    "signal_close_reference","atr14","stop_reference","first_entry_reference",
    "second_entry_reference","nearest_resistance_reference",
    "first_net_rr","second_net_rr","structure_reference_valid",
    "price_not_independent_session_certified",
    "ordinary_common_stock_verified","research_blockers",
    "trade_approved","orders_enabled")

def finite(v,allow_zero=True):
    try:
        if v is None or isinstance(v,bool) or str(v).strip()=="":return None
        v=float(str(v).strip().replace(",",""))
        if not math.isfinite(v) or v<0 or (not allow_zero and v==0):return None
        return v
    except (TypeError,ValueError):return None

def valid_bar(v):
    op,hi,lo,cl,vol=(finite(v.get(k)) for k in OHLC)
    return bool(all(x is not None and x>0 for x in (op,hi,lo,cl))
        and vol is not None and vol>0
        and lo<=min(op,cl)<=max(op,cl)<=hi)

def parse_days(rows,ticker,asof):
    if not rows:return [],"MISSING_MARKET_HISTORY"
    last=None;out=[]
    for row in rows:
        raw=row.get("Date")
        try:
            day=date.fromisoformat(raw)
            if day.isoformat()!=raw:raise ValueError()
        except (ValueError,TypeError):return [],"INVALID_OR_MISSING_HISTORY_DATE"
        if last is not None and day<=last:return [],"HISTORY_NOT_STRICTLY_CHRONOLOGICAL"
        if day>asof:return [],"FUTURE_DAILY_BAR_IN_SOURCE"
        last=day
        prices={k:finite(row.get(k.capitalize())) for k in OHLC}
        prices["turnover_krw"]=finite(row.get("TurnoverKRW"))
        out.append(dict(ticker=ticker,date=raw,**prices,
                        data_source="pykrx"))
    if not out or out[-1]["date"]!=asof.isoformat():
        return out,"LATEST_HISTORY_ASOF_MISSING"
    return out,None

def name_kind(name):
    text=str(name or "").strip()
    upper=text.upper()
    if (not text or any(k.upper() in upper for k in EXCLUDED_NAME)
        or text.endswith("우") or text.endswith("우1") or
        text.endswith("우2") or re.search(r"우[1-9][A-Z]?$",text)):
        return "NON_COMMON_OR_SPECIAL" if text else "UNKNOWN"
    return "UNKNOWN"  # no common-share proof from security name alone

def group_end_period(bars,kind):
    groups={}
    for b in bars:
        d=date.fromisoformat(b["date"])
        key=((d.isocalendar().year,d.isocalendar().week)
             if kind=="week" else (d.year,d.month))
        groups[key]=b["close"]
    return list(groups.values())

def candidate_features(bars):
    if len(bars)<REQUIRED_WARMUP:
        raise ValueError("INSUFFICIENT_160DAY_CANDIDATE_WARMUP")
    if any(not valid_bar(b) for b in bars[-REQUIRED_WARMUP:]):
        raise ValueError("INVALID_160DAY_FULL_PRICE_GEOMETRY")
    closes=[b["close"] for b in bars]
    vols=[b["volume"] for b in bars]
    def av(n,arr=closes):
        return sum(arr[-n:])/n
    ma20,ma60,ma120=av(20),av(60),av(120)
    c=closes[-1]
    last_rv=sum(vols[-21:-1])/20
    rvol=vols[-1]/last_rv if last_rv>0 else None
    previous20high=max(b["high"] for b in bars[-21:-1])
    breakout=(c>previous20high and rvol is not None
        and rvol>=1.5 and c>ma60)
    pullback=(ma20>ma60>ma120 and c>ma20 and
              abs(c/ma20-1)<=0.035)
    ma60prior=sum(closes[-61:-1])/60
    ma20prior5=sum(closes[-25:-5])/20
    reversal=(closes[-2]<ma60prior and c>ma60 and ma20>ma20prior5)
    weekly=group_end_period(bars,"week")
    monthly=group_end_period(bars,"month")
    weekly_ok=(len(weekly)>=30 and
        weekly[-1]>sum(weekly[-10:])/10)
    monthly_ok=(len(monthly)>=8 and
        monthly[-1]>sum(monthly[-6:])/6)
    return dict(close=c,ma20=ma20,ma60=ma60,ma120=ma120,
        rvol20=rvol or 0,
        breakout=breakout,first_pullback_proxy=pullback,
        reversal_proxy=reversal,weekly_filter=weekly_ok,
        monthly_filter=monthly_ok)

def latest_market(v18,asof):
    status=read_json(v18/"diagnostics/collection_status.json")
    if (status.get("asof")!=str(asof)
        or status.get("orders_enabled") is not False
        or status.get("datasets",{}).get("prices",{}).get("status")!="OK"
        or status.get("datasets",{}).get("krx_preflight",{}).get("asof")!=str(asof)
        or status.get("datasets",{}).get("krx_preflight",{}).get("status")!="OK"):
        raise ValueError("V18_DATE_OR_MARKET_COMPLETENESS_UNVERIFIED")
    records={}
    counts={}
    source_hashes={}
    for market in ("KOSPI","KOSDAQ"):
        path=v18/"market/daily_prices"/market/(str(asof)+".csv")
        if not path.is_file():raise ValueError("MISSING_FULL_MARKET_DAILY_SNAPSHOT")
        source_hashes[market]=digest(path.read_bytes())
        with path.open(encoding="utf-8-sig",newline="") as f:
            reader=csv.DictReader(f)
            if tuple(reader.fieldnames or ())!=DAY_FIELDS:
                raise ValueError("MARKET_SNAPSHOT_SCHEMA_MISMATCH")
            count=0
            for r in reader:
                t=r["ticker"]
                if (not re.fullmatch(r"[0-9A-Z]{6}",t or "")
                    or t in records or r.get("Date")!=str(asof)):
                    raise ValueError("MARKET_DATE_DUPLICATED_OR_INVALID_CODE")
                vals={k:finite(r.get(k.capitalize())) for k in OHLC}
                vals["turnover_krw"]=finite(r.get("TurnoverKRW"))
                records[t]=(market,vals)
                count+=1
            counts[market]=count
        if count<100:raise ValueError("MARKET_UNIVERSE_TOO_SMALL")
    if len(records)!=sum(counts.values()):
        raise ValueError("DUPLICATE_MARKET_UNIVERSE")
    return status,records,counts,source_hashes

def build(v18,official_root):
    source=read_json(official_root/"krx_v65_collect_status.json")
    try:asof=date.fromisoformat(source.get("asof",""))
    except (ValueError,TypeError):raise ValueError("OFFICIAL_REFERENCE_DATE_MISSING")
    if (asof.isoformat()!=source["asof"]
        or source.get("schema")!=COLLECT_SCHEMA
        or source.get("official_dataset_usable") is not True
        or source.get("krx_eod_authenticated") is not True
        or source.get("independent_1530_regular_session_certified") is not False
        or source.get("source_price_authorized_for_trading") is not False
        or source.get("orders_enabled") is not False
        or source.get("trade_approved") is not False):
        raise ValueError("OFFICIAL_API_ASOF_OR_TRADING_SAFETY_INVALID")
    official=official_rows(official_root,source)
    v18status,raw,counts,sourcehashes=latest_market(v18,asof)
    if set(raw)!=set(official):
        raise ValueError("KRX_OFFICIAL_AND_V18_DIFFERENT_ASOF_UNIVERSE")
    for t,(market,values) in raw.items():
        if market!=official[t][0] or any(values[k]!=official[t][1][k]
            for k in (*OHLC,"turnover_krw")):
            raise ValueError("KRX_OFFICIAL_V18_OHLCV_TURNOVER_MISMATCH")
    diag=[];candidates=[];histories=[];setups=[];ranked=[]
    skips=Counter()
    for t,(market,current) in sorted(raw.items()):
        p=v18/"market/prices"/(t+".csv")
        def diagnostic(reason,kind="",numrows=0,valid=False):
            skips[reason]+=1
            diag.append(dict(ticker=t,name=official[t][1].get("name",""),
                market=market,asof=str(asof),screen_status="EXCLUDED",
                reason=reason,history_length=numrows,history_valid_160=valid,
                official_ohlcv_equals_v18=True,
                instrument_type=kind,source_file_sha256=digest(p.read_bytes())
                if p.is_file() else "",
                trade_approved=False,orders_enabled=False))
        # Name must come from authenticated official API, NOT from inferred
        # current listing or an old candidate-selection bias.
        name=source_name(official_root,t,market)
        kind=name_kind(name)
        if not p.is_file():
            diagnostic("MISSING_UNIFORM_HISTORY",kind)
            continue
        parsed,error=parse_days(read_csv(p),t,asof)
        if error:
            diagnostic(error,kind,len(parsed))
            continue
        if len(parsed)<REQUIRED_WARMUP:
            diagnostic("INSUFFICIENT_160DAY_WARMUP",kind,len(parsed))
            continue
        if any(not valid_bar(b) for b in parsed[-REQUIRED_WARMUP:]):
            diagnostic("INVALID_RECENT_160_DAILY_OHLCV",kind,len(parsed))
            continue
        if any(parsed[-1][k]!=current[k] for k in (*OHLC,"turnover_krw")):
            raise ValueError("HISTORY_LAST_BAR_DIFFERS_FROM_OFFICIAL_KRX")
        if current["turnover_krw"] is None or current["turnover_krw"]<=0:
            diagnostic("MISSING_SOURCE_REPORTED_TURNOVER",kind,len(parsed),True)
            continue
        try:fea=candidate_features(parsed)
        except ValueError as exc:
            diagnostic(str(exc),kind,len(parsed))
            continue
        if kind=="NON_COMMON_OR_SPECIAL":
            diagnostic("SUSPECTED_NON_COMMON_SPECIAL_NAME_EXCLUDED",kind,len(parsed),True)
            continue
        if not any(fea[x] for x in ("breakout","first_pullback_proxy","reversal_proxy")):
            diagnostic("NO_PRELIMINARY_MOMENTUM_OR_PULLBACK_SETUP",kind,len(parsed),True)
            continue
        row=dict(ticker=t,name=name,market=market,
            latest_date=str(asof),data_source="pykrx",
            instrument_type=kind,turnover_source="SOURCE_REPORTED",
            turnover_krw=current["turnover_krw"],
            **fea)
        preliminary=preliminary_score(row)
        if preliminary is None:
            diagnostic("PRELIMINARY_SCORE_UNAVAILABLE",kind,len(parsed),True)
            continue
        cand=dict(ticker=t,name=name,market=market,asof=str(asof),
            source_file_sha256=digest(p.read_bytes()),
            source_latest_ohlcv_vs_krx_eod_verified=True,
            history_bars=len(parsed),history_min_160_valid=True,
            history_last_120_sha256=digest(json.dumps(
                parsed[-120:],ensure_ascii=False,sort_keys=True).encode("utf-8")),
            instrument_type=kind,instrument_name_exclusion=False,
            turnover_source="SOURCE_REPORTED",
            turnover_krw=current["turnover_krw"],
            close=fea["close"],ma20=round(fea["ma20"],2),
            ma60=round(fea["ma60"],2),ma120=round(fea["ma120"],2),
            rvol20=round(fea["rvol20"],3),
            weekly_filter=fea["weekly_filter"],monthly_filter=fea["monthly_filter"],
            breakout=fea["breakout"],first_pullback_proxy=fea["first_pullback_proxy"],
            reversal_proxy=fea["reversal_proxy"],
            preliminary_c3_score=preliminary["c3_preliminary_score"],
            preliminary_k100_score=preliminary["k100_preliminary_score"],
            preliminary_rank_only=True,final_80_score_verified=False,
            regular_1530_session_certified=False,
            trade_approved=False,orders_enabled=False)
        candidates.append(cand)
        ranked.append((t,preliminary))
        # Full as-of history for 120 daily structure, never rewritten using
        # the old per-ticker adjusted feed.
        histories.extend(parsed[-HISTORICAL_BARS_TO_SAVE:])
        for method in METHODS:
            x=evaluate(row,parsed[-HISTORICAL_BARS_TO_SAVE:],asof,method,
                paired=dict(category="OHLC_EXACT_MATCH_UNCERTIFIED",close_equal=True))
            setups.append(dict(ticker=t,name=name,market=market,asof=str(asof),
                method=method,setup=x["setup"],
                signal_close_reference=x["asof_close_research"],
                atr14=x["atr14"],stop_reference=x["stop_reference"],
                first_entry_reference=x["first_entry_reference"],
                second_entry_reference=x["second_entry_reference"],
                nearest_resistance_reference=x["nearest_resistance_reference"],
                first_net_rr=x["first_net_rr"],second_net_rr=x["second_net_rr"],
                structure_reference_valid=x["technical_research_ready"],
                price_not_independent_session_certified=True,
                ordinary_common_stock_verified=False,
                research_blockers=";".join(x["blocking_reasons"]),
                trade_approved=False,orders_enabled=False))
        diag.append(dict(ticker=t,name=name,market=market,asof=str(asof),
            screen_status="RESEARCH_SCREENED",reason="PRELIMINARY_ONLY_NOT_ORDER",
            history_length=len(parsed),history_valid_160=True,
            official_ohlcv_equals_v18=True,
            instrument_type=kind,source_file_sha256=digest(p.read_bytes()),
            trade_approved=False,orders_enabled=False))
    if len(diag)!=len(raw):
        raise ValueError("NOT_ALL_UNIVERSE_SECURITIES_ACCOUNTED_FOR")
    if len(setups)!=len(candidates)*len(METHODS):
        raise ValueError("INCOMPLETE_CANDIDATE_METHOD_EVALUATIONS")
    order_c3=sorted(candidates,key=lambda x:(-x["preliminary_c3_score"],-x["turnover_krw"],x["ticker"]))
    order_k100=sorted(candidates,key=lambda x:(-x["preliminary_k100_score"],-x["turnover_krw"],x["ticker"]))
    triggers=[x for x in setups if x["setup"]=="RESEARCH_TRIGGER_CONFIRMED_ASOF"]
    report=dict(schema=SCHEMA,asof=str(asof),
        source_v18_run_asof=v18status["asof"],
        krx_official_collection_timestamp=source["retrieval_utc"],
        official_market_stock_count=source["official_market_rows"],
        official_market_source_response_sha256=source["raw_response_sha256"],
        market_v18_daily_source_sha256=sourcehashes,
        market_counts=counts,asof_universe_count=len(raw),
        independent_date_universe_includes_excluded_securities=True,
        source_marketwide_ticker_history_only=True,
        legacy_adjusted_per_security_history_used=False,
        official_krx_and_v18_latest_all_fields_match=True,
        histories_screened=len(candidates),
        archived_candidate_120_daily_rows=len(histories),
        rejected_and_nontrigger_universe_rows=len(raw)-len(candidates),
        source_exclusion_counts=dict(skips),
        method_research_rows=len(setups),
        completed_method_triggers=len(triggers),
        prelim_c3_top5=[x["ticker"] for x in order_c3[:5]],
        prelim_k100_top5=[x["ticker"] for x in order_k100[:5]],
        intermediate_score_out_of_85_only=True,
        final_80point_score_verified=False,
        instrument_common_share_type_verified=False,
        sector_flow_catalyst_and_financials_verified=False,
        historical_120day_official_API_authenticated=False,
        regular_1530_only_price_certified=False,
        full_universe_historical_PIT_verified=False,
        orders_enabled=False,trade_approved=False,decision="CASH")
    return report,candidates,diag,histories,setups

def source_name(root,ticker,market):
    # KRX official CSV includes ISU_NM but v6.5 archived normalized columns
    # store it as 'name'; only the exact same official dated file is used.
    # Return empty if not present, which excludes ordinary-share inference.
    path=root/(market+"_official.csv")
    if not hasattr(source_name,"_cache") or source_name._cache_root!=str(root):
        d={}
        for mk in ("KOSPI","KOSDAQ"):
            for r in read_csv(root/(mk+"_official.csv")):
                d[(mk,r["ticker"])]=r.get("name","")
        source_name._cache=d
        source_name._cache_root=str(root)
    return source_name._cache.get((market,ticker),"")

def write_outputs(output,report,candidates,diagnostics,histories,setups):
    output.mkdir(parents=True,exist_ok=True)
    for file,fields,rows in (
        ("full_market_v68_candidates.csv",CAND_FIELDS,candidates),
        ("full_market_v68_universe_audit.csv",DIAGNOSTIC_FIELDS,diagnostics),
        ("full_market_v68_method_research.csv",RESEARCH_FIELDS,setups),
        ("full_market_v68_candidate_120bars.csv",
            ("ticker","date","open","high","low","close","volume","turnover_krw","data_source"),histories)):
        with (output/file).open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    # Bind the derived 52-candidate universe to its complete 120-day
    # history and method outcomes. A downstream liquidity screen must never
    # silently accept modified candidate prices or altered past turnover.
    report["artifact_file_sha256"]={
        filename:digest((output/filename).read_bytes())
        for filename in (
            "full_market_v68_candidates.csv",
            "full_market_v68_universe_audit.csv",
            "full_market_v68_method_research.csv",
            "full_market_v68_candidate_120bars.csv")}
    (output/"full_market_v68_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lookup={x["ticker"]:x for x in candidates}
    lines=["# C3·K100 v6.8 KRX 전체시장 동일출처 스캐너","",
        f"**{report['asof']}** 최종 판단: **CASH / 주문 0**",
        f"해당 날짜 전체시장 {report['asof_universe_count']}종목에서 출발. "+
          f"일관된 160일 유효 이력과 기초 기술조건을 통과한 연구후보 {report['histories_screened']}개.",
        "기존 82개 회복스캔 후보로 출발하지 않았습니다.",
        "최신 시고저종/거래량/실제 거래대금은 공식 KRX 일봉과 전부 일치했지만 "+
          "정규장 15:30 전용 인증은 아닙니다.",
        "기초 예비점수(최대 85점)는 최종 80점 게이트 또는 5일 상승확률이 아닙니다.",
        "", "## C3 예비연구 상위 5 (매수 추천 아님)",
        "| 종목 | C3 예비점수 | 최신 종가 | 실측 거래대금(억원) |",
        "|---|---:|---:|---:|"]
    for ticker in report["prelim_c3_top5"]:
        x=lookup[ticker]
        lines.append(f"| {x['name']} {ticker} | {x['preliminary_c3_score']} | "+
            f"{x['close']:,.0f} | {x['turnover_krw']/1e8:,.1f} |")
    lines.extend(["","## K100 예비연구 상위 5 (매수 추천 아님)",
        "| 종목 | K100 예비점수 | 최신 종가 | 실측 거래대금(억원) |",
        "|---|---:|---:|---:|"])
    for ticker in report["prelim_k100_top5"]:
        x=lookup[ticker]
        lines.append(f"| {x['name']} {ticker} | {x['preliminary_k100_score']} | "+
            f"{x['close']:,.0f} | {x['turnover_krw']/1e8:,.1f} |")
    lines.extend(["", "## 기술 신호 및 데이터 제약",
        f"방법별 검토 {report['method_research_rows']}행, 기술패턴 감지 {report['completed_method_triggers']}건.",
        "모든 진입·구조손절가 연구값은 120일 시장전체 pykrx 자료로 계산했으며 "+
            "주문가 또는 확정 손실제한가가 아닙니다.",
        "보통주 법적 유형, 외국인/기관 섹터 자금흐름, 실적/촉매, "+
            "정규장 종가 독립검증, 계좌 현금 및 실제체결 조건을 통과한 종목은 0건.",
        "", "## Required Next Data",
        "15:30 정규장 명시 공식 가격, 120일 수정주가 정책과 동일 공급원 인증, "+
            "당시 PIT 보통주 종목유형, 기관·외국인 수급과 실적·촉매, 최신 계좌 현금.",
        ""])
    (output/"full_market_v68_mobile.md").write_text(
        "\n".join(lines),encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    for name in ("--v18","--official","--outdir"):
        p.add_argument(name,required=True,type=Path)
    a=p.parse_args()
    report,candidates,diag,histories,setup=build(a.v18,a.official)
    write_outputs(a.outdir,report,candidates,diag,histories,setup)
    print("V68_FULL_KRX_UNBIASED_ASOF_RESEARCH",json.dumps({k:report[k]
        for k in ("asof","asof_universe_count","histories_screened",
            "completed_method_triggers","prelim_c3_top5",
            "prelim_k100_top5","decision")},ensure_ascii=False))
if __name__=="__main__":main()
