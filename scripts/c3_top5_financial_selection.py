#!/usr/bin/env python3
"""Select up to five finance-qualified technical candidates; research only."""
import argparse
import json
from pathlib import Path

def select(geometry, financial):
    asof=geometry.get("asof")
    candidates=geometry.get("candidates",[])
    passed=set()
    status=financial.get("status")
    # Next-day OpenDART observations may inform a research shortlist but
    # must never be mistaken for a historical point-in-time certification.
    accepted=("FINANCIAL_RESEARCH_GATE_PASSED",
              "PARTIAL_OR_FAILED_FINANCIAL_GATE",
              "NEXT_DAY_FINANCIAL_RESEARCH_NOT_PIT_CERTIFIED")
    valid_date=financial.get("asof")==asof
    researched=financial.get("researched",[])
    excluded=financial.get("excluded",[])
    requested={c.get("code") for c in candidates if isinstance(c,dict)
               and c.get("status") in ("ENTRY_READY","NEAR_ENTRY")
               and isinstance(c.get("risk_pct"),(int,float))
               and 0<c["risk_pct"]<=5}
    covered=[x.get("ticker") for x in researched+excluded if isinstance(x,dict)]
    coverage_ok=(len(covered)==len(set(covered)) and set(covered)==requested)
    if valid_date and status in accepted and coverage_ok:
        passed={x.get("ticker") for x in researched
                if x.get("financial_screen_pass") is True}
    ready=[];near=[];watch=[]
    for c in candidates if isinstance(candidates,list) else []:
        if not isinstance(c,dict) or c.get("code") not in passed:
            continue
        if c.get("risk_pct") is None or not 0 < c["risk_pct"] <= 5:
            continue
        if c.get("status")=="ENTRY_READY":
            ready.append(c)
        elif c.get("status")=="NEAR_ENTRY":
            near.append(c)
        else:
            watch.append(c)
    ready.sort(key=lambda c:(-float(c.get("opportunity_score") or 0),-float(c.get("score") or 0),c["code"]))
    near.sort(key=lambda c:(-float(c.get("opportunity_score") or 0),-float(c.get("score") or 0),c["code"]))
    selected=(ready+near)[:5]
    return {"schema":"C3_TOP5_FINANCIAL_SELECTION_RESEARCH_V1","asof":asof,
            "status":"RESEARCH_ONLY","financial_evidence_status":status,
            "coverage_complete":coverage_ok,"point_in_time_certified":False,
            "decision":"CASH","trade_approved":False,
            "selected":[{"code":c["code"],"name":c.get("name"),
                         "technical_status":c.get("status")} for c in selected],
            "watch_count":len(watch),"financial_pass_count":len(passed),
            "selected_count":len(selected)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--geometry",type=Path,required=True)
    p.add_argument("--financial",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=select(json.loads(a.geometry.read_text()),json.loads(a.financial.read_text()))
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("FINANCIAL_SELECTION",result["selected_count"],"decision=CASH")
if __name__=="__main__":main()
