#!/usr/bin/env python3
"""Independent close-price evidence checker. Does not fetch or certify a source."""
import argparse
import json
import re
from pathlib import Path

def verify(receipt, evidence):
    out={"schema":"C3_INDEPENDENT_PRICE_EVIDENCE_V1","status":"UNVERIFIED",
         "regular_session_price_certified":False,"corporate_actions_certified":False,
         "decision":"CASH","trade_approved":False,"matched":[]}
    if evidence.get("source_type") != "INDEPENDENT_OFFICIAL_EXCHANGE":
        out["status"]="NON_INDEPENDENT_SOURCE"
        return out
    if evidence.get("asof") != receipt.get("asof"):
        out["status"]="ASOF_MISMATCH"
        return out
    if evidence.get("adjustment_policy_verified") is not True:
        out["status"]="ADJUSTMENT_POLICY_UNVERIFIED"
        return out
    candidates=receipt.get("candidates",[])
    rows=evidence.get("prices",[])
    if not isinstance(candidates,list) or not candidates or not isinstance(rows,list):
        out["status"]="NO_COMPARABLE_PRICES"
        return out
    lookup={}
    for r in rows:
        if not isinstance(r,dict) or not re.fullmatch(r"\d{6}",str(r.get("code",""))) or r["code"] in lookup:
            out["status"]="INVALID_EVIDENCE"
            return out
        lookup[r["code"]]=r
    for c in candidates:
        if not isinstance(c,dict) or c.get("code") not in lookup:
            out["status"]="INCOMPLETE_EVIDENCE"
            return out
        r=lookup[c["code"]]
        try:
            close=int(c["close"])
            independent=int(r["close"])
        except (ValueError,TypeError,KeyError):
            out["status"]="INVALID_PRICE"
            return out
        if close<=0 or independent<=0 or close!=independent or r.get("regular_session") is not True:
            out["status"]="PRICE_MISMATCH_OR_SESSION_UNVERIFIED"
            return out
        out["matched"].append(c["code"])
    out["status"]="PRICE_EVIDENCE_MATCHED"
    out["regular_session_price_certified"]=True
    out["corporate_actions_certified"]=True
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=verify(json.loads(a.receipt.read_text()),json.loads(a.evidence.read_text()))
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("INDEPENDENT_PRICE_EVIDENCE",result["status"],"decision=CASH")
if __name__=="__main__":main()
