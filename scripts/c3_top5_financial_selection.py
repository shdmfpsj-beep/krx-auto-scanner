#!/usr/bin/env python3
"""Select up to five finance-qualified technical candidates; research only."""
import argparse
import json
from pathlib import Path

def select(geometry, financial):
    asof=geometry.get("asof")
    candidates=geometry.get("candidates",[])
    passed=set()
    if financial.get("asof")==asof and financial.get("status") in (
        "FINANCIAL_RESEARCH_GATE_PASSED","PARTIAL_OR_FAILED_FINANCIAL_GATE"):
        passed={x.get("ticker") for x in financial.get("researched",[])
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
    selected=(ready+near)[:5]
    return {"schema":"C3_TOP5_FINANCIAL_SELECTION_RESEARCH_V1","asof":asof,
            "status":"RESEARCH_ONLY","decision":"CASH","trade_approved":False,
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
