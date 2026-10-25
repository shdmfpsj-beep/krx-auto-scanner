#!/usr/bin/env python3
"""v6.8.1 raw reported turnover + 20-session expansion watchlist, not a BUY.

Filters entire KRX as-of scanner's research shortlist by measured
reported KRX turnover, NOT estimated price * volume. Keeps raw 52
research candidates and technical signals unchanged. Does not infer
foreign/institution purchases or final 80-point approval.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict,Counter
from pathlib import Path

from forward_ledger_v63 import read_json,read_csv,digest
from full_market_scanner_v68 import SCHEMA as V68

SCHEMA="C3_K100_FULL_MARKET_LIQUIDITY_OBSERVATION_V681"
C3_TURNOVER_MIN_KRW=5_000_000_000  # 50억원: configurable research heuristic
K100_TURNOVER_MIN_KRW=2_000_000_000 # 20억원
IGNITION_MIN_TURNOVER_RATIO20=1.5
FIELDS=("ticker","name","market","asof","candidate_close",
    "c3_technical_score","k100_technical_score",
    "turnover_krw","mean_previous20_turnover_krw",
    "turnover_expansion_vs_previous20",
    "turnover_observation","c3_liquid_eligible","k100_liquid_eligible",
    "common_stock_confirmed","regular_1530_only_confirmed",
    "sector_flow_institution_foreign_verified",
    "final_80_score_verified","trade_approved","orders_enabled")

def number(v):
    try:
        if v in ("",None) or isinstance(v,bool):return None
        v=float(v)
        return v if math.isfinite(v) and v>=0 else None
    except (TypeError,ValueError):return None

def classify(dayturn,ratio):
    if dayturn is None or ratio is None:return "UNKNOWN_LIQUIDITY_DATA"
    return ("RELATIVE_MONEY_FLOW_EXPANSION_150PCT"
        if ratio>=IGNITION_MIN_TURNOVER_RATIO20
        else "TURNOVER_PRESENT_NOT_RISING_150PCT")

def run(scan):
    manifest=read_json(scan/"full_market_v68_status.json")
    candidates=read_csv(scan/"full_market_v68_candidates.csv")
    histories=read_csv(scan/"full_market_v68_candidate_120bars.csv")
    if (manifest.get("schema")!=V68
        or manifest.get("decision")!="CASH"
        or manifest.get("trade_approved") is not False
        or manifest.get("orders_enabled") is not False
        or manifest.get("official_krx_and_v18_latest_all_fields_match") is not True
        or manifest.get("regular_1530_only_price_certified") is not False
        or manifest.get("instrument_common_share_type_verified") is not False
        or manifest.get("histories_screened")!=len(candidates)
        or manifest.get("archived_candidate_120_daily_rows")!=len(histories)
        or len(histories)!=120*len(candidates)):
        raise ValueError("V68_AUDITED_RAW_CANDIDATES_MISSING_OR_UNSAFE")
    files=manifest.get("artifact_file_sha256",{})
    for filename in ("full_market_v68_candidates.csv",
                     "full_market_v68_candidate_120bars.csv",
                     "full_market_v68_universe_audit.csv",
                     "full_market_v68_method_research.csv"):
        path=scan/filename
        if (not path.is_file() or
            files.get(filename)!=digest(path.read_bytes())):
            raise ValueError("V68_FROZEN_DERIVED_REPORT_SHA256_MISMATCH")
    history=defaultdict(list)
    for bar in histories:
        history[bar["ticker"]].append(bar)
    if len(history)!=len(candidates):
        raise ValueError("V68_HISTORY_MISSING_CANDIDATE_OR_DUPLICATED")
    out=[];unique=set()
    for x in candidates:
        t=x.get("ticker")
        if (t in unique or x.get("asof")!=manifest["asof"]
            or x.get("turnover_source")!="SOURCE_REPORTED"
            or x.get("trade_approved")!="False"
            or x.get("orders_enabled")!="False"
            or x.get("preliminary_rank_only")!="True"
            or x.get("instrument_type")!="UNKNOWN"
            or x.get("source_latest_ohlcv_vs_krx_eod_verified")!="True"):
            raise ValueError("V68_CANDIDATE_UNTRUSTED_OR_RELABELED")
        unique.add(t)
        bars=history.get(t,[])
        if len(bars)!=120 or bars[-1]["date"]!=manifest["asof"]:
            raise ValueError("V68_120BAR_HISTORY_CHRONOLOGY_OR_COUNT")
        seen_days=set()
        rebuild=[]
        for b in bars:
            d=b.get("date")
            if not d or d in seen_days or d>manifest["asof"] or b["ticker"]!=t:
                raise ValueError("V68_TURNOVER_LOOKAHEAD_OR_DUPLICATE_DATE")
            seen_days.add(d)
            s={k:number(b.get(k)) for k in
               ("open","high","low","close","volume","turnover_krw")}
            if any(v is None for v in s.values()):
                raise ValueError("V68_HISTORIC_NUMERIC_PRICE_MISSING")
            rebuild.append(dict(ticker=t,date=d,**s,data_source=b["data_source"]))
        hashme=digest(json.dumps(rebuild,ensure_ascii=False,
            sort_keys=True).encode("utf-8"))
        if hashme!=x["history_last_120_sha256"]:
            raise ValueError("V68_HISTORIC_120BAR_CONTENT_HASH_MISMATCH")
        turnover=number(x["turnover_krw"])
        close=number(x["close"])
        if (turnover is None or turnover<=0 or close is None or close<=0
            or turnover!=rebuild[-1]["turnover_krw"]
            or close!=rebuild[-1]["close"]):
            raise ValueError("V68_LATEST_TURNOVER_PRICE_NOT_SAME_FROZEN")
        mean20=sum(v["turnover_krw"] for v in rebuild[-21:-1])/20
        ratio=turnover/mean20 if mean20>0 else None
        c3=turnover>=C3_TURNOVER_MIN_KRW and ratio is not None and ratio>=0.5
        k100=turnover>=K100_TURNOVER_MIN_KRW and ratio is not None and ratio>=0.5
        out.append(dict(ticker=t,name=x["name"],market=x["market"],
            asof=x["asof"],candidate_close=close,
            c3_technical_score=int(x["preliminary_c3_score"]),
            k100_technical_score=int(x["preliminary_k100_score"]),
            turnover_krw=turnover,mean_previous20_turnover_krw=round(mean20),
            turnover_expansion_vs_previous20=round(ratio,4)
                if ratio is not None else None,
            turnover_observation=classify(turnover,ratio),
            c3_liquid_eligible=c3,k100_liquid_eligible=k100,
            common_stock_confirmed=False,regular_1530_only_confirmed=False,
            sector_flow_institution_foreign_verified=False,
            final_80_score_verified=False,trade_approved=False,
            orders_enabled=False))
    if len(out)!=len(candidates):
        raise ValueError("INCOMPLETE_V68_LIQUIDITY_COVERAGE")
    def top(key,score):
        selected=[r for r in out if r[key]]
        selected.sort(key=lambda r:(
            -(r["turnover_expansion_vs_previous20"]>=IGNITION_MIN_TURNOVER_RATIO20),
            -r[score],-r["turnover_krw"],r["ticker"]))
        return [dict(r) for r in selected[:5]]
    c3=top("c3_liquid_eligible","c3_technical_score")
    k100=top("k100_liquid_eligible","k100_technical_score")
    report=dict(schema=SCHEMA,asof=manifest["asof"],
        source_v68_daily_sha256=manifest["market_v18_daily_source_sha256"],
        official_krx_eod_response_sha256=manifest["official_market_source_response_sha256"],
        full_market_asof_universe=manifest["asof_universe_count"],
        candidates_observed=len(out),
        c3_min_real_turnover_krw=C3_TURNOVER_MIN_KRW,
        k100_min_real_turnover_krw=K100_TURNOVER_MIN_KRW,
        expansion_vs_prior_20days_gate=IGNITION_MIN_TURNOVER_RATIO20,
        c3_liquid_count=sum(r["c3_liquid_eligible"] for r in out),
        k100_liquid_count=sum(r["k100_liquid_eligible"] for r in out),
        c3_research_ticker_top5=[r["ticker"] for r in c3],
        k100_research_ticker_top5=[r["ticker"] for r in k100],
        liquid_money_expansion_is_not_foreign_or_institution_net_buy=True,
        raw_ranked_52_unmodified=True,
        common_share_PIT_type_verified=False,
        regular_1530_verified=False,financial_catalysts_verified=False,
        final_80point_score_verified=False,
        trade_approved=False,orders_enabled=False,decision="CASH")
    return report,out,c3,k100

def write_outputs(outdir,report,rows,c3,k100):
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"liquid_watch_v681_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (outdir/"liquid_watch_v681_all.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)
    lines=["# v6.8.1 실측 거래대금 기반 우선연구 후보","",
        f"거래일: {report['asof']} · **CASH / 매수승인 0**",
        f"시장전체 {report['full_market_asof_universe']}코드, 기존 기술조건 "+
          f"{report['candidates_observed']}후보에서 C3 당일 50억·K100 당일 20억원 이상만 유동성 연구 대상으로 분류.",
        "거래대금 증가는 외국인·기관 순매수의 증명이 아닙니다.",
        "전체 52기술후보와 120일 원본은 변경하지 않습니다.",""]
    for title,group in (("C3 유동성/증가율 우선 연구",c3),
                        ("K100 유동성/증가율 우선 연구",k100)):
        lines+=["## "+title,"",
            "| 종목 | 예비 기술점수 | 당일 실측 거래대금(억원) | 직전20일 대비 |",
            "|---|---:|---:|---:|"]
        if not group:lines.append("| 해당 없음 | — | — | — |")
        for r in group:
            score=r["c3_technical_score"] if title.startswith("C3") else r["k100_technical_score"]
            lines.append(f"| {r['name']} {r['ticker']} | {score} | "+
                f"{r['turnover_krw']/1e8:,.1f} | "+
                f"{r['turnover_expansion_vs_previous20']:.2f}배 |")
        lines.append("")
    lines +=["**상기 목록은 실제 추천·지정가 주문이 아닌 예비 연구 대상입니다.**",
        "최종 80점, 09:00~15:30 가격, 보통주 PIT, 섹터 수급/재무/현금, 구조손절 손익비 인증은 별도입니다.",
        "", "## Required Next Data",
        "정규장 가격 세션, 공식 보통주 유형, 섹터별 외국인·기관 순매수, 실적·공시 촉매, C3·K100 최신 잔고."]
    (outdir/"liquid_watch_v681_mobile.md").write_text(
        "\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--scan",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args()
    s,r,c,k=run(a.scan)
    write_outputs(a.outdir,s,r,c,k)
    print("V681_LIQUIDITY_SOURCE_REPORTED_RANK",
          json.dumps({k:s[k] for k in (
              "asof","candidates_observed","c3_liquid_count",
              "k100_liquid_count","c3_research_ticker_top5",
              "k100_research_ticker_top5","decision")},ensure_ascii=False))
if __name__=="__main__":main()
