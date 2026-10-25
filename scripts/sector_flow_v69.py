#!/usr/bin/env python3
"""v6.9 date-locked ETF-component sector-proxy flow + whole-KRX candidates.

This reads actual v18 raw per-ticker KRX/PyKrx foreign/institution
BUY-SELL amounts over the last five completed source dates. Recalculates
5d ETF-HOLDING membership proxy totals and reconciles each with published
sector_evidence_latest. No absent ticker may become 0, no shares of
intersecting ETFs may be claimed as market-wide industry flow.

Strict PIT vintage, official 09:00-15:30 source, ordinary-share
classification and 80-point entry approval are NOT independently verified.
Never place an order or silently promote 3rd weak sector into 3rd strong.
"""
from __future__ import annotations
import argparse,csv,json,math,re
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from pathlib import Path

from forward_ledger_v63 import read_json,read_csv,digest
from full_market_scanner_v68 import SCHEMA as MARKET_SCHEMA
from liquidity_watch_v68 import SCHEMA as LIQUID_SCHEMA,run as rebuild_liquidity,FIELDS as LIQ_FIELDS

SCHEMA="C3_K100_SECTOR_MONEY_FLOW_RESEARCH_V69"
INVESTORS={"foreign":"외국인","institution":"기관합계"}
MARKETS=("KOSPI","KOSDAQ")
SECTOR_FIELDS=("sector_id","sector_name","asof","snapshot_date","etf",
    "proxy_stock_members","foreign_5d_krw","institution_5d_krw",
    "combined_5d_krw","sector_proxy_turnover_krw","net_flow_to_turnover_pct",
    "rs_5d_pp","breadth_up_5d_pct","all_member_flows_5d_complete",
    "source_report_totals_reconciled","source_flow_coverage","relative_strength_positive",
    "net_buy_positive","sector_proxy_pit_vintage_verified",
    "sector_strength_research_score","strength_status","reason",
    "trade_approved","orders_enabled")
STOCK_FIELDS=("ticker","name","market","asof","mapped_sector_ids",
    "mapped_selected_sectors","mapped_strong_sectors",
    "is_in_research_top3_sector","is_in_strict_strong_sector",
    "five_day_source_flow_complete",
    "foreign_net_buy_5d_krw","institution_net_buy_5d_krw",
    "foreign_plus_institution_5d_krw",
    "foreign_net_buy_today_krw","institution_net_buy_today_krw",
    "turnover_krw","turnover_expansion_vs_previous20",
    "c3_technical_score","k100_technical_score",
    "c3_liquidity_ok","k100_liquidity_ok",
    "both_investor_types_net_buy_positive_5d",
    "foreign_institution_buy_signal_research_only",
    "final80_verification","regular_1530_verified","common_stock_verified",
    "earnings_catalyst_verified","trade_approved","orders_enabled")
REQUIRED_SECTOR_COLUMNS=("sector_id","sector_name","date","snapshot_date","stock_members",
    "foreign_net_buy_5d_krw","institution_net_buy_5d_krw",
    "rs_5d_pp","breadth_up_5d_pct","member_turnover_krw")
REQUIRED_FLOW_COLUMNS=("date","market","ticker","name","investor",
    "buy_krw","sell_krw","net_buy_krw","unit","source","collected_at",
    "availability_assumption")

def num(value,allow_negative=False):
    if value in ("",None) or isinstance(value,bool):return None
    try:
        v=float(value)
        if not math.isfinite(v) or (not allow_negative and v<0):return None
        return v
    except (ValueError,TypeError):return None

def iso(value):
    d=date.fromisoformat(value)
    if d.isoformat()!=value:raise ValueError("SOURCE_DATE_NOT_ISO")
    return d

def read_sector_evidence(v18,asof):
    p=v18/"research/sector_evidence_latest.csv"
    rows=read_csv(p)
    if not rows or len(rows)<5:raise ValueError("SECTOR_EVIDENCE_TOO_SMALL")
    for r in rows:
        if not all(k in r for k in REQUIRED_SECTOR_COLUMNS):
            raise ValueError("SECTOR_EVIDENCE_REQUIRED_COLUMNS_MISSING")
        if r["date"]!=asof or r["live_selection_authorized"]!="False":
            raise ValueError("SECTOR_EVIDENCE_DATE_OR_LIVE_APPROVAL_UNSAFE")
        if (r["membership_status"]!="PROVIDER_DATED_PROXY_NOT_STRICT_PIT"
            or r["money_scope"]!="ETF_stock_constituents_unweighted_net_buy_not_entire_industry"
            or r.get("full_sector_score") not in ("",None)
            or r["availability_assumption"].find("not_historical_vintage_verified")<0):
            raise ValueError("ETF_MEMBERSHIP_IS_NOT_AUTHORITATIVE_PIT")
    ids=[r["sector_id"] for r in rows]
    if len(ids)!=len(set(ids)):raise ValueError("DUPLICATE_SECTOR_PROXY")
    return rows,digest(p.read_bytes())

def read_memberships(v18,asof,sector_rows):
    p=v18/"market/sector_membership_dated.csv"
    records=read_csv(p)
    if not records:raise ValueError("DATED_MEMBERSHIP_MISSING")
    membership=defaultdict(set)
    checked=set()
    current={}
    for sector in sector_rows:
        sid=sector["sector_id"]
        snap=iso(sector["snapshot_date"])
        if snap>iso(asof) or (iso(asof)-snap).days>10:
            current[sid]=False
            continue
        current[sid]=True
        checked.add((sid,str(snap)))
    for r in records:
        key=(r["sector_id"],r["snapshot_date"])
        if key not in checked:continue
        t=r.get("ticker","")
        if (not re.fullmatch(r"[A-Z0-9]{6}",t)
            or r.get("point_in_time_status")!="PROVIDER_DATED_NOT_INDEPENDENT_VINTAGE_VERIFIED"
            or num(r.get("weight_pct")) is None or
            r.get("source")!="KRX_ETF_PDF_dated_request"):
            raise ValueError("MEMBER_SECURITY_MAPPING_UNTRUSTWORTHY")
        if t in membership[key]:
            raise ValueError("ETF_COMPONENT_DUPLICATED")
        membership[key].add(t)
    return membership,current,digest(p.read_bytes())

def discover_flow_days(v18,asof):
    base=v18/"market/daily_flows"
    candidates=[]
    for p in (base/"KOSPI").glob("*_foreign.csv"):
        day=p.name[:10]
        try:d=iso(day)
        except (ValueError,TypeError):continue
        if d<=iso(asof):candidates.append(day)
    days=sorted(set(candidates))[-5:]
    if len(days)!=5 or days[-1]!=asof:
        raise ValueError("NOT_FIVE_COMPLETE_ASOF_MARKET_SOURCE_DATES")
    for day in days:
        for investor in INVESTORS:
            for market in MARKETS:
                if not (base/market/(day+"_"+investor+".csv")).is_file():
                    raise ValueError("MISSING_ONE_MARKET_INVESTOR_FOR_FIVE_DAYS")
    return days

def load_flows(v18,asof):
    days=discover_flow_days(v18,asof)
    flows={};hashes={}
    for day in days:
        for investor,expected in INVESTORS.items():
            key=(day,investor)
            data={}
            for market in MARKETS:
                path=v18/"market/daily_flows"/market/(day+"_"+investor+".csv")
                hashes[str(path.relative_to(v18))]=digest(path.read_bytes())
                rows=read_csv(path)
                if not rows or tuple(rows[0].keys())!=REQUIRED_FLOW_COLUMNS:
                    raise ValueError("INVALID_FLOW_FILE_HEADER_OR_EMPTY")
                for r in rows:
                    t=r.get("ticker","")
                    if (r.get("date")!=day or r.get("market")!=market
                        or r.get("investor")!=expected or r.get("unit")!="KRW"
                        or r.get("source")!="KRX_via_PyKrx"
                        or r.get("availability_assumption")!="final_after_18KST_not_intraday_PIT_verified"
                        or not re.fullmatch(r"[0-9A-Z]{6}",t or "")
                        or t in data):
                        raise ValueError("FLOW_DUPLICATED_TICKER_OR_WRONG_PROVENANCE")
                    buy=num(r.get("buy_krw"));sell=num(r.get("sell_krw"))
                    net=num(r.get("net_buy_krw"),allow_negative=True)
                    if (buy is None or sell is None or net is None
                        or abs((buy-sell)-net)>1.01):
                        raise ValueError("FLOW_NET_BUY_ACCOUNTING_NOT_RECONCILED")
                    data[t]=(market,net)
            flows[key]=data
    return days,flows,hashes

def ratio_score(s):
    if s is None:return None
    return max(-15.,min(15.,s))

def score_sector(rs,breadth,relative):
    # Unvalidated descriptive heuristic, not future win probability.
    return round(50+2*max(-15,min(15,rs))
        +0.3*max(0,min(100,breadth))
        +(ratio_score(relative) if relative is not None else 0),2)

def evaluate(v18,scan):
    v=read_json(scan/"full_market_v68_status.json")
    if (v.get("schema")!=MARKET_SCHEMA
        or v.get("trade_approved") is not False
        or v.get("orders_enabled") is not False
        or v.get("regular_1530_only_price_certified") is not False
        or v.get("instrument_common_share_type_verified") is not False
        or v.get("official_krx_and_v18_latest_all_fields_match") is not True):
        raise ValueError("FULL_MARKET_ASOF_OR_APPROVAL_INVALID")
    asof=v["asof"]
    status=read_json(v18/"diagnostics/collection_status.json")
    if (status.get("asof")!=asof
        or status.get("orders_enabled") is not False
        or status.get("datasets",{}).get("flows",{}).get("status")!="OK"
        or status.get("datasets",{}).get("holdings",{}).get("status")!="OK"
        or status.get("datasets",{}).get("sector_research",{}).get("status") not in ("OK",None)):
        raise ValueError("SECTOR_FLOW_SOURCE_INCOMPLETE")
    calc_status,calc_liquid,_,_=rebuild_liquidity(scan)
    stamped=read_json(scan/"liquid_watch_v681_status.json")
    liquidity=read_csv(scan/"liquid_watch_v681_all.csv")
    if stamped!=calc_status or len(liquidity)!=len(calc_liquid):
        raise ValueError("V681_LIQUIDITY_MANIFEST_TAMPERED")
    for actual,expected in zip(liquidity,calc_liquid):
        if any(actual[k] != ("" if expected[k] is None else str(expected[k]))
               for k in LIQ_FIELDS):
            raise ValueError("V681_LIQUIDITY_RESULT_TAMPERED")
    latest,sectorhash=read_sector_evidence(v18,asof)
    members,usable,memberhash=read_memberships(v18,asof,latest)
    days,flows,flowhash=load_flows(v18,asof)
    all_sectors=[]
    member_by_ticker=defaultdict(set)
    for r in latest:
        sid=r["sector_id"]
        memberset=members[(sid,r["snapshot_date"])]
        if usable.get(sid) and len(memberset)!=int(r["stock_members"]):
            raise ValueError("MEMBERSHIP_COUNT_AND_SECTOR_REPORT_CONFLICT")
        if usable.get(sid):
            for t in memberset:member_by_ticker[t].add(sid)
        cov_count=0
        totals=defaultdict(float)
        missing=[]
        for t in sorted(memberset):
            ok=True
            for day in days:
                for key in INVESTORS:
                    f=flows[(day,key)].get(t)
                    if f is None:
                        ok=False
                    else:
                        totals[key]+=f[1]
            if ok:cov_count+=1
            else:missing.append(t)
        full=bool(usable.get(sid) and memberset and not missing)
        fv=num(r.get("foreign_net_buy_5d_krw"),allow_negative=True)
        iv=num(r.get("institution_net_buy_5d_krw"),allow_negative=True)
        replay=full and fv is not None and iv is not None and (
            abs(totals["foreign"]-fv)<=1 and abs(totals["institution"]-iv)<=1)
        if full and not replay:
            raise ValueError("SECTOR_5DAY_REPORTED_TOTAL_DIFFERS_FROM_RAW_FLOW")
        rs=num(r.get("rs_5d_pp"),allow_negative=True)
        breadth=num(r.get("breadth_up_5d_pct"))
        turn=num(r.get("member_turnover_krw"))
        cov= (cov_count/len(memberset)) if memberset else 0
        sr=(totals["foreign"]+totals["institution"]) if full else None
        relative=(100*sr/turn) if turn and sr is not None else None
        proxy_ready=(r["price_flow_proxy_ready"]=="True"
            and r.get("foreign_5d_coverage") not in ("",None)
            and num(r["foreign_5d_coverage"])>=.95
            and num(r["institution_5d_coverage"])>=.95)
        strict=(sid!="HEALTH" and full and replay and proxy_ready
            and rs is not None and rs>0 and breadth is not None and breadth>=20
            and sr is not None and sr>0 and turn is not None and turn>0)
        if strict:
            label,reason="PROXY_STRONG_RESEARCH","RS5_POSITIVE_FI_NET_BUY_POSITIVE_BREADTH_20PLUS"
        elif sid=="HEALTH":
            label,reason="SECTOR_EXCLUDED","PHARMA_BIOTECH_USER_EXCLUSION"
        elif not usable.get(sid) or not full or not replay or not proxy_ready:
            label,reason="EVIDENCE_INCOMPLETE","SECTOR_PROXY_OR_FLOW_COVERAGE_NOT_AUTHORIZED"
        elif rs is None or breadth is None or turn is None:
            label,reason="EVIDENCE_INCOMPLETE","MISSING_RS_BREADTH_OR_TURNOVER"
        elif sr and sr>0:
            label,reason="FLOW_POSITIVE_WEAK_TREND_WATCH","RS5_OR_BREADTH_NOT_STRONG"
        else:
            label,reason="NOT_STRONG_NOW","NONPOSITIVE_COMBINED_5DAY_FI_FLOW"
        all_sectors.append(dict(sector_id=sid,sector_name=r["sector_name"],
            asof=asof,snapshot_date=r["snapshot_date"],etf=r["etf"],
            proxy_stock_members=len(memberset),
            foreign_5d_krw=round(totals["foreign"],2) if full else None,
            institution_5d_krw=round(totals["institution"],2) if full else None,
            combined_5d_krw=round(sr,2) if sr is not None else None,
            sector_proxy_turnover_krw=turn,
            net_flow_to_turnover_pct=round(relative,4) if relative is not None else None,
            rs_5d_pp=rs,breadth_up_5d_pct=breadth,
            all_member_flows_5d_complete=full,
            source_report_totals_reconciled=replay,
            source_flow_coverage=round(cov,4),
            relative_strength_positive=bool(rs is not None and rs>0),
            net_buy_positive=bool(sr is not None and sr>0),
            sector_proxy_pit_vintage_verified=False,
            sector_strength_research_score=score_sector(
                rs if rs is not None else -15,breadth if breadth is not None else 0,relative),
            strength_status=label,reason=reason,
            trade_approved=False,orders_enabled=False))
    stricts=sorted((r for r in all_sectors
         if r["strength_status"]=="PROXY_STRONG_RESEARCH"),
         key=lambda r:(-r["sector_strength_research_score"],r["sector_id"]))
    other=sorted((r for r in all_sectors if r["strength_status"]==
         "FLOW_POSITIVE_WEAK_TREND_WATCH"),
         key=lambda r:(-r["sector_strength_research_score"],r["sector_id"]))
    recommended_top3=stricts[:3]
    watch=[r for r in other if r["sector_id"] not in
         {s["sector_id"] for s in recommended_top3}]
    selected_ids={r["sector_id"] for r in recommended_top3}
    top3_research=list(recommended_top3)
    if len(top3_research)<3:
        top3_research+=watch[:3-len(top3_research)]
    research_ids={r["sector_id"] for r in top3_research}
    stock_rows=[]
    for c in liquidity:
        t=c["ticker"]
        member=member_by_ticker.get(t,set())
        indices={}
        for investor in INVESTORS:
            values=[flows[(d,investor)].get(t) for d in days]
            indices[investor]=values
        complete=all(all(v is not None for v in vs) for vs in indices.values())
        foreign=sum(v[1] for v in indices["foreign"]) if complete else None
        inst=sum(v[1] for v in indices["institution"]) if complete else None
        together=foreign+inst if complete else None
        stock_rows.append(dict(ticker=t,name=c["name"],market=c["market"],asof=asof,
            mapped_sector_ids=";".join(sorted(member)),
            mapped_selected_sectors=";".join(sorted(member&research_ids)),
            mapped_strong_sectors=";".join(sorted(member&selected_ids)),
            is_in_research_top3_sector=bool(member&research_ids),
            is_in_strict_strong_sector=bool(member&selected_ids),
            five_day_source_flow_complete=complete,
            foreign_net_buy_5d_krw=round(foreign,2) if foreign is not None else None,
            institution_net_buy_5d_krw=round(inst,2) if inst is not None else None,
            foreign_plus_institution_5d_krw=round(together,2) if together is not None else None,
            foreign_net_buy_today_krw=indices["foreign"][-1][1] if complete else None,
            institution_net_buy_today_krw=indices["institution"][-1][1] if complete else None,
            turnover_krw=num(c["turnover_krw"]),
            turnover_expansion_vs_previous20=num(c["turnover_expansion_vs_previous20"]),
            c3_technical_score=int(c["c3_technical_score"]),
            k100_technical_score=int(c["k100_technical_score"]),
            c3_liquidity_ok=c["c3_liquid_eligible"]=="True",
            k100_liquidity_ok=c["k100_liquid_eligible"]=="True",
            both_investor_types_net_buy_positive_5d=bool(complete and foreign>0 and inst>0),
            foreign_institution_buy_signal_research_only=bool(
                complete and together>0),
            final80_verification=False,regular_1530_verified=False,
            common_stock_verified=False,earnings_catalyst_verified=False,
            trade_approved=False,orders_enabled=False))
    if len(stock_rows)!=len(liquidity):
        raise ValueError("FLOW_CANDIDATE_SET_INCOMPLETE")
    stocks_qualified=sorted((r for r in stock_rows if
        r["is_in_strict_strong_sector"] and r["five_day_source_flow_complete"]
        and r["foreign_institution_buy_signal_research_only"]
        and r["c3_liquidity_ok"]),
        key=lambda r:(-r["both_investor_types_net_buy_positive_5d"],
          -r["c3_technical_score"],-r["foreign_plus_institution_5d_krw"],r["ticker"]))
    output=dict(schema=SCHEMA,asof=asof,
        sector_source_sha256=sectorhash,
        membership_source_sha256=memberhash,flow_source_sha256=flowhash,
        validated_flow_dates=days,
        v68_market_sha256=v["market_v18_daily_source_sha256"],
        v68_official_response_sha256=v["official_market_source_response_sha256"],
        v68_candidate_count=v["histories_screened"],
        v681_count=calc_status["candidates_observed"],
        total_proxy_sectors=len(all_sectors),
        strict_strong_proxy_sector_count=len(stricts),
        strict_strong_sectors=[s["sector_id"] for s in stricts[:3]],
        top3_research_sectors=[
            dict(sector_id=s["sector_id"],status=s["strength_status"])
            for s in top3_research],
        third_strong_sector_confirmed=len(stricts)>=3,
        individual_ticker_flow_rows=len(stock_rows),
        selected_strong_sector_and_liquid_fi_flow_count=len(stocks_qualified),
        selected_strong_sector_and_liquid_tickers=[r["ticker"] for r in stocks_qualified],
        excluded_pharma_biotech_sector=True,
        ETF_membership_not_independent_PIT=True,
        raw_money_flows_aftermarket_date_not_intraday_verifiable=True,
        overlapping_etf_constituents_must_not_be_deduplicated_as_industry_sector=True,
        official_regular_1530_not_certified=True,
        full_80_score_not_certified=True,
        orders_enabled=False,trade_approved=False,decision="CASH")
    return output,all_sectors,stock_rows,top3_research,stocks_qualified

def write_outputs(output,report,sectors,stocks,top3,qualified):
    output.mkdir(parents=True,exist_ok=True)
    (output/"sector_money_v69_status.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for file,fields,rows in (
        ("sector_money_v69_all.csv",SECTOR_FIELDS,sectors),
        ("sector_money_v69_candidates.csv",STOCK_FIELDS,stocks)):
        with (output/file).open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            writer.writeheader();writer.writerows(rows)
    lines=["# v6.9 외국인·기관 실측 금액 + 섹터 ETF 구성종목 대용 수급",
        "",f"2026-10-23 기준 / **CASH / 신규매수 0**" if report["asof"]=="2026-10-23"
             else report["asof"]+" / CASH / 신규매수 0",
        f"정확한 완료된 5개 시세일: {', '.join(report['validated_flow_dates'])}",
        f"강세 세부요건을 모두 통과한 섹터: **{report['strict_strong_proxy_sector_count']}개**",
        "여기서 섹터란 KRX 종목의 공식 업종분류가 아니라 **날짜가 붙은 테마 ETF 구성종목 대용**입니다.",
        "", "## 강한 섹터 / 세 번째 관찰 섹터 (5일 합산)",
        "| 분야 | 검증 상태 | 외국인+기관 5일 순매수(억원) | ETF RS5(%p) | 5일 상승비중 |",
        "|---|---|---:|---:|---:|"]
    for r in top3:
        lines.append(f"| {r['sector_name']} | {r['strength_status']} | "+
            f"{(r['combined_5d_krw'] or 0)/1e8:,.1f} | "+
            f"{r['rs_5d_pp'] if r['rs_5d_pp'] is not None else '미확인'} | "+
            f"{r['breadth_up_5d_pct'] if r['breadth_up_5d_pct'] is not None else '미확인'}% |")
    if len(top3)<3:lines.append(f"| 세 번째 강세 섹터 부족 | **미선정** | — | — | — |")
    if top3 and top3[-1]["strength_status"]!="PROXY_STRONG_RESEARCH":
        lines.append("**주의: 관찰 섹터는 강한 섹터 Top3에 합격한 것이 아닙니다.**")
    lines+=["","## 강세 섹터와 유동성·외국인기관 순매수를 함께 통과한 종목 (연구 후보)",
        "| 종목 | 속한 강세 섹터 | 5일 외국인(억원) | 5일 기관(억원) | C3 예비점수 |",
        "|---|---|---:|---:|---:|"]
    if not qualified:lines.append("| 해당 없음 | — | — | — | — |")
    for r in qualified[:8]:
        lines.append(f"| {r['name']} {r['ticker']} | {r['mapped_strong_sectors']} | "+
            f"{r['foreign_net_buy_5d_krw']/1e8:,.1f} | "+
            f"{r['institution_net_buy_5d_krw']/1e8:,.1f} | "+
            f"{r['c3_technical_score']} |")
    lines+=["","**기관·외국인 순매수 데이터는 실제 KRX/PyKrx 보고 금액이지만, ETF 구성종목 집계의 투자시점 PIT 및 09:00~15:30 정규장 범위를 독립 인증하지 않았습니다.**",
        "섹터 proxy 구성종목이 여러 ETF에 중복 포함되는 경우 금액을 산업 전체로 더하지 않습니다.",
        "기업실적/기사/보통주 분류/최종 80점/구조손절 2R 및 계좌현금 확인 전에는 모든 진입안 승인 금지.",
        "", "## Required Next Data",
        "정규장 독립 15:30 마감봉, PIT 섹터 구성종목/일별 업종분류, 외국인·기관 5일 금액 교차검증, 재무·수주 공시 시각, 계좌 잔고."]
    (output/"sector_money_v69_mobile.md").write_text(
        "\n".join(lines)+"\n",encoding="utf-8")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--v18",type=Path,required=True)
    parser.add_argument("--scan",type=Path,required=True)
    parser.add_argument("--outdir",type=Path,required=True)
    args=parser.parse_args()
    report,sectors,stocks,top3,qual=evaluate(args.v18,args.scan)
    write_outputs(args.outdir,report,sectors,stocks,top3,qual)
    print("V69_SECTOR_FOREIGN_INSTITUTION_MONEY_PROXY",
        json.dumps({k:report[k] for k in (
            "asof","total_proxy_sectors","strict_strong_proxy_sector_count",
            "top3_research_sectors","selected_strong_sector_and_liquid_tickers",
            "decision")},ensure_ascii=False))
if __name__=="__main__":main()
