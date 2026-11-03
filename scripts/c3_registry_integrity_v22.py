"""v22: retrospective audit of frozen C3 selections, without rewriting history."""
import argparse,csv,json
from pathlib import Path

SPECIAL=("스팩","SPAC","리츠","REIT","ETF","ETN")
def audit(registry,preliminary,evidence):
    names={r.get("ticker","").zfill(6):r.get("name","") for r in preliminary}
    ev={r.get("ticker","").zfill(6):r for r in evidence}
    results=[]
    for row in registry:
        ticker=row.get("ticker","").zfill(6)
        name=names.get(ticker,"")
        e=ev.get(ticker,{})
        reasons=[]
        if not name:reasons.append("NAME_NOT_IN_CURRENT_PRELIMINARY")
        if any(x in name.replace(" ","").upper() for x in SPECIAL):
            reasons.append("SPECIAL_INSTRUMENT_NAME")
        if e.get("instrument_review") in ("EXCLUDE_SPECIAL","EXCLUDE_NON_COMMON"):
            reasons.append("EXCLUDED_INSTRUMENT_EVIDENCE")
        if not e:reasons.append("EVIDENCE_MISSING")
        results.append({"key":row.get("key"),"run":row.get("run"),"ticker":ticker,
                        "registered_utc":row.get("registered_utc"),
                        "original_status":row.get("status"),"audit_reasons":sorted(set(reasons)),
                        "evaluation_group":"EXCLUDE_FROM_ELIGIBLE_PERFORMANCE" if reasons else "RESEARCH_ONLY_UNCERTIFIED"})
    return {"schema":"C3_REGISTRY_INTEGRITY_V22","total_registered":len(results),
            "excluded_from_eligible_performance":sum(x["evaluation_group"]=="EXCLUDE_FROM_ELIGIBLE_PERFORMANCE" for x in results),
            "items":results,"decision":"CASH","buy_approvals":0,
            "note":"Historical rows retained unchanged. This audit uses current reference metadata, not point-in-time proof."}
def read(path):
    with open(path,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for x in ("registry","preliminary","evidence","output"):p.add_argument("--"+x,required=True)
    a=p.parse_args()
    result=audit(read(a.registry),read(a.preliminary),read(a.evidence))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"registered":result["total_registered"],"excluded":result["excluded_from_eligible_performance"]}))
