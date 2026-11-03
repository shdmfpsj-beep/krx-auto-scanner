"""C3 v16 evidence-aware selection: unknown is not healthy or eligible."""
import argparse,csv,json,math
from pathlib import Path

def number(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

def select(preliminary,evidence):
    lookup={r.get("ticker","").zfill(6):r for r in evidence}
    items=[];counts={}
    for r in preliminary:
        ticker=r.get("ticker","").zfill(6)
        e=lookup.get(ticker)
        if not e:
            counts["MISSING_EVIDENCE_ROW"]=counts.get("MISSING_EVIDENCE_ROW",0)+1
            continue
        # Name-based special-instrument guard is conservative and not a substitute for official instrument verification.
        name=(r.get("name") or "").replace(" ","").upper()
        if any(token in name for token in ("스팩","SPAC","리츠","REIT","ETF","ETN")):
            counts["EXCLUDED_SPECIAL_NAME"]=counts.get("EXCLUDED_SPECIAL_NAME",0)+1
            continue
        if e.get("instrument_review") in ("EXCLUDE_SPECIAL","EXCLUDE_NON_COMMON"):
            counts["EXCLUDED_INSTRUMENT_EVIDENCE"]=counts.get("EXCLUDED_INSTRUMENT_EVIDENCE",0)+1
            continue
        if e.get("business_scope_status") in ("EXCLUDE_FROM_C3","PHARMA_BIOTECH"):
            counts["EXCLUDED_BUSINESS"]=counts.get("EXCLUDED_BUSINESS",0)+1
            continue
        score=number(r.get("c3_preliminary_score"))
        extension=number(r.get("extension_vs_ma20_pct"))
        rvol=number(r.get("rvol20"))
        if None in (score,extension,rvol):
            counts["INVALID_TECHNICALS"]=counts.get("INVALID_TECHNICALS",0)+1
            continue
        blockers=[x for x in e.get("blocking_reasons","").split(";") if x]
        if e.get("instrument_review")!="CURRENT_COMMON_CONFIRMED":
            blockers.append("CURRENT_COMMON_UNVERIFIED")
        if e.get("business_scope_status") not in ("IN_SCOPE_VERIFIED","NON_BIO_VERIFIED"):
            blockers.append("BUSINESS_SCOPE_UNVERIFIED")
        if e.get("regular_session_certified")!="True":
            blockers.append("REGULAR_SESSION_UNVERIFIED")
        if e.get("actual_turnover_status")!="VERIFIED":
            blockers.append("ACTUAL_TURNOVER_UNVERIFIED")
        priority=round(score-max(0,extension-8)-2*max(0,rvol-5),2)
        items.append({"ticker":ticker,"name":r.get("name"),"price_date":r.get("latest_date"),
          "stage":r.get("setup"),"technical_priority":priority,
          "business_scope":e.get("business_scope_status"),
          "evidence_blockers":sorted(set(blockers)),
          "sector_strength":"UNVERIFIED","financial_health":"UNVERIFIED",
          "entry_range":None,"entry_status":"재산정 대기",
          "entry_registered_at":None,"structural_stop":None,
          "nearest_resistance":None,"buy_approved":False})
    items.sort(key=lambda x:(-x["technical_priority"],x["ticker"]))
    return {"schema":"C3_SELECTION_EVIDENCE_V16","input_count":len(preliminary),
      "evidence_rows":len(evidence),"joined_count":len(items),"excluded":counts,
      "provisional_watch_top2":items[:2],"buy_approvals":0,"decision":"CASH",
      "limitations":"Research-only technical priority. No verified sector/financial/structural entry model. Not full-market eligible TOP2."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--preliminary",default="reports/c3_preliminary.csv")
    p.add_argument("--evidence",default="reports/c3_candidate_evidence_v1.csv")
    p.add_argument("--output",default="reports/c3_selection_evidence_v16.json")
    a=p.parse_args()
    def read(path):
        with open(path,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
    result=select(read(a.preliminary),read(a.evidence))
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"joined":result["joined_count"],"buy_approvals":0}))
if __name__=="__main__":main()
