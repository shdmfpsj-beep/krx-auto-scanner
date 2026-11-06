"""Offline reconciliation, preserving unresolved causes rather than guessing splits."""
import argparse
import csv
import gzip
import json
from collections import Counter,defaultdict
from pathlib import Path

from c3_price_basis_v2 import classify_prices,FIELDS
from c3_competition_v2 import sha


def compare(left,right):
    counts=Counter();by_ticker=defaultdict(Counter);differences=[]
    overlap=sorted(set(left)&set(right))
    for key in overlap:
        a,b=left[key],right[key];label=classify_prices(a,b)
        counts[label]+=1;by_ticker[key[0]][label]+=1
        if label!="MATCH":
            changed=[k for k in FIELDS if a.get(k)!=b.get(k)]
            differences.append(dict(ticker=key[0],date=key[1],classification=label,changed_fields=changed,
                left={k:a.get(k) for k in FIELDS},right={k:b.get(k) for k in FIELDS}))
    return dict(compared=len(overlap),left_only=len(set(left)-set(right)),right_only=len(set(right)-set(left)),
                categories=dict(counts),by_ticker={k:dict(v) for k,v in by_ticker.items()},differences=differences)


def reconcile(panel_path,audit_path,basis_dir,cases_path,archive_path,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    audit=json.loads(Path(audit_path).read_text())
    if sha(panel_path)!=audit["panel_sha256"]:raise ValueError("OFFICIAL_PANEL_HASH_MISMATCH")
    cases=json.loads(Path(cases_path).read_text());tickers=set(cases["old_16_tickers_reserved_as_exploratory_not_confirmation"])
    tickers.update(("026960","271560"));official={};legacy={};adjusted={}
    with gzip.open(panel_path,"rt",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in tickers:
                official[(r["ticker"],r["date"])]=dict(date=r["date"],**{k:float(r[k]) for k in FIELDS})
    with gzip.open(archive_path,"rt",encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in tickers:
                legacy[(r["ticker"],r["date"])]=dict(date=r["date"],**{k:float(r[k]) for k in FIELDS})
    basis=Path(basis_dir);meta=json.loads((basis/"price_basis_report.json").read_text())
    for q in meta["queries"]:
        if q["mode"]!="adjusted_long" or q["status"]!="OK":continue
        path=basis/(q["ticker"]+"_adjusted_long.json")
        if sha(path)!=q["sha256"]:raise ValueError("BASIS_QUERY_HASH_MISMATCH")
        for r in json.loads(path.read_text())["rows"]:adjusted[(q["ticker"],r["date"])]=r
    comparisons={"legacy_adjusted_vs_official":compare(legacy,official),
                 "current_adjusted_vs_official":compare(adjusted,official),
                 "legacy_vs_current_adjusted":compare(legacy,adjusted)}
    case_checks=[]
    for c in cases["cases"]:
        days=[c["decision_date"],c["entry_date"],c["exit_date"]]
        observations=[]
        for d in days:
            key=(c["ticker"],d)
            observations.append(dict(date=d,classification=classify_prices(legacy[key],official[key])
                if key in legacy and key in official else "MISSING_PAIR"))
        case_checks.append(dict(ticker=c["ticker"],decision_date=c["decision_date"],
                                legacy_net_pct=c["net_pct"],checks=observations))
    # Do not copy wrong early heuristic labels when shares did not change.
    corrected_events=[]
    for event in audit["reference_rebase_candidates"]:
        event=dict(event);ratio=event.get("share_count_ratio")
        if event["kind"]=="SHARE_COUNT_REBASE_CANDIDATE" and (ratio is None or abs(ratio-1)<=.01):
            event["kind"]="REFERENCE_PRICE_REBASE_UNRESOLVED"
        corrected_events.append(event)
    full=dict(comparisons=comparisons)
    with gzip.open(root/"price_differences.json.gz","wt",encoding="utf-8") as f:
        json.dump(full,f,ensure_ascii=False,separators=(",",":"))
    for comp in comparisons.values():del comp["differences"]
    report=dict(schema="C3_SOURCE_RECONCILIATION_V2",comparisons=comparisons,legacy_case_checks=case_checks,
        official_panel_sha256=sha(panel_path),basis_report_sha256=sha(basis/"price_basis_report.json"),
        original_archive_sha256=sha(archive_path),
        reference_discrepancy_candidates=len(corrected_events),
        corrected_candidate_categories=dict(Counter(e["kind"] for e in corrected_events)),
        queried_raw_pykrx_failures=[q for q in meta["queries"] if q["mode"]=="unadjusted" and q["status"]!="OK"],
        prefix_tickers_compared=len(meta["prefix_comparisons"]),
        prefix_days_compared=sum(v["compared_days"] for v in meta["prefix_comparisons"].values()),
        prefix_changed_days=sum(len(v["changed_prefix_days"]) for v in meta["prefix_comparisons"].values()),
        reference_disagreements_are_not_confirmed_corporate_actions=True,
        session_mix_causes_verified=False,dividend_total_returns_verified=False,
        same_retrieval_prefix_equality_is_not_historical_vintage=True,
        executable_price_basis="OFFICIAL_RAW_ONLY_IN_COMPETITION_NO_ADJUSTED_QUOTES",
        regular_only_certified=False,trade_approved=False)
    (root/"source_reconciliation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    (root/"dated_reference_boundaries.json").write_text(json.dumps(corrected_events,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v["categories"] for k,v in comparisons.items()}));return report


def main():
    p=argparse.ArgumentParser()
    for name in ("panel","audit","basis-dir","outdir"):p.add_argument("--"+name,required=True)
    p.add_argument("--cases",default="reports/c3_work2_20261105/legacy_loss_diagnostics.json")
    p.add_argument("--archive",default="reports/c3_premove_history_v1.csv.gz");a=p.parse_args()
    reconcile(a.panel,a.audit,a.basis_dir,a.cases,a.archive,a.outdir)


if __name__=="__main__":main()
