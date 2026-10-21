#!/usr/bin/env python3
"""Conservative sector evidence bridge: research ranking, never a trade signal."""
import argparse,csv,json,math
from pathlib import Path

EXCLUDE={"HEALTH"}
REQUIRED=("prices","flows","etf_prices","holdings","normalization")

def number(row,key):
    try:
        value=float(row.get(key,""))
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):
        return None

def build(status,rows,scan_date):
    asof=status.get("asof")
    datasets=status.get("datasets",{})
    valid=bool(asof and asof==scan_date and
               all(datasets.get(k,{}).get("status")=="OK" for k in REQUIRED))
    result=[]
    for r in rows:
        if r.get("sector_id") in EXCLUDE: continue
        reasons=[]
        if not valid: reasons.append("CORE_DATA_OR_DATE_UNVERIFIED")
        if r.get("date")!=asof: reasons.append("SECTOR_DATE_MISMATCH")
        if str(r.get("price_flow_proxy_ready","")).lower() not in ("true","1","yes"):
            reasons.append("PRICE_FLOW_PROXY_UNREADY")
        if str(r.get("live_selection_authorized","")).lower() in ("true","1","yes"):
            reasons.append("UNEXPECTED_LIVE_AUTHORIZATION")
        rs=number(r,"rs_5d_pp")
        breadth=number(r,"breadth_up_5d_pct")
        flow=number(r,"foreign_net_buy_5d_krw")
        inst=number(r,"institution_net_buy_5d_krw")
        if any(v is None for v in (rs,breadth,flow,inst)):
            reasons.append("RESEARCH_METRIC_MISSING")
        coverage_keys=("breadth_coverage","turnover_coverage",
                       "foreign_5d_coverage","institution_5d_coverage")
        coverages=[number(r,k) for k in coverage_keys]
        if any(v is None for v in coverages):
            reasons.append("COVERAGE_UNVERIFIED")
        elif any(v < 0.95 for v in coverages):
            reasons.append("LOW_METRIC_COVERAGE")
        if flow is not None and inst is not None and flow + inst <= 0:
            reasons.append("NO_POSITIVE_NET_FLOW_PROXY")
        # No 100-point sector score: catalyst PIT and fundamentals not verified.
        result.append({"sector_id":r.get("sector_id",""),
                       "sector_name":r.get("sector_name",""),
                       "asof":asof or "",
                       "rs_5d_pp":"" if rs is None else rs,
                       "breadth_up_5d_pct":"" if breadth is None else breadth,
                       "foreign_net_buy_5d_krw":"" if flow is None else flow,
                       "institution_net_buy_5d_krw":"" if inst is None else inst,
                       "research_eligible":"YES" if not reasons else "NO",
                       "warnings":";".join(reasons),
                       "final_sector_score":"","trade_approval":"NO"})
    eligible=[r for r in result if r["research_eligible"]=="YES"]
    eligible.sort(key=lambda r:(-(r["rs_5d_pp"]),-(r["breadth_up_5d_pct"]),r["sector_id"]))
    return eligible+[r for r in result if r["research_eligible"]!="YES"],{
        "asof":asof,"scan_date":scan_date,"core_data_verified":valid,
        "research_eligible_sectors":len(eligible),
        "research_top3_sector_ids":[r["sector_id"] for r in eligible[:3]],
        "research_top3_not_trade_approved":True,
        "final_sector_top3_verified":False,"trade_approvals":0,
        "decision":"CASH","note":"ETF-member flow proxy is not verified whole-sector capital inflow; catalyst PIT and earnings not scored."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True)
    p.add_argument("--scan-status",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    root=Path(a.evidence)
    status=json.loads((root/"diagnostics/collection_status.json").read_text())
    scan=json.loads(Path(a.scan_status).read_text())
    evidence_csv=root/"research/sector_evidence_latest.csv"
    if evidence_csv.is_file():
        with evidence_csv.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
    else:
        rows=[]
    ranked,summary=build(status,rows,scan.get("market_data_date"))
    if not evidence_csv.is_file():
        summary["missing_evidence"]="research/sector_evidence_latest.csv"
        summary["decision"]="CASH"
        summary["reason"]="Historical baseline-only artifact lacks current sector feature rows"
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    fields=["sector_id","sector_name","asof","rs_5d_pp","breadth_up_5d_pct",
            "foreign_net_buy_5d_krw","institution_net_buy_5d_krw",
            "research_eligible","warnings","final_sector_score","trade_approval"]
    with (out/"sector_research_ranking.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ranked)
    (out/"sector_bridge_status.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
