"""Fail-closed source provenance inspection for C3 price comparisons.

Metadata declarations are untrusted claims, not proof of independence or
regular-session certification. This module never enables trading.
"""
import argparse
import json
from pathlib import Path

REQUIRED=("provider","upstream","market_scope","price_adjustment","timezone","retrieved_at")
SCOPES={"REGULAR_ONLY","UNKNOWN","REGULAR_PLUS_EXTENDED"}
ADJUSTMENTS={"ADJUSTED","UNADJUSTED","UNKNOWN"}

def canonical(value):
    return "".join(c for c in str(value).casefold() if c.isalnum())

def inspect(primary,reference):
    errors=[]
    for label,meta in (("PRIMARY",primary),("REFERENCE",reference)):
        if not isinstance(meta,dict):
            errors.append(label+"_INVALID_METADATA")
            continue
        for key in REQUIRED:
            if not isinstance(meta.get(key),str) or not meta[key].strip():
                errors.append(label+"_MISSING_"+key.upper())
        if meta.get("market_scope") not in SCOPES:
            errors.append(label+"_INVALID_SCOPE")
        if meta.get("price_adjustment") not in ADJUSTMENTS:
            errors.append(label+"_INVALID_ADJUSTMENT")
        if meta.get("timezone")!="Asia/Seoul":
            errors.append(label+"_TIMEZONE_NOT_KST")
    if not errors:
        if canonical(primary["provider"])==canonical(reference["provider"]):
            errors.append("SAME_PROVIDER")
        if canonical(primary["upstream"])==canonical(reference["upstream"]):
            errors.append("SAME_UPSTREAM")
        if (canonical(primary["provider"])==canonical(reference["upstream"]) or
            canonical(reference["provider"])==canonical(primary["upstream"])):
            errors.append("CROSS_REFERENCED_PROVIDER_UPSTREAM")
        if primary["price_adjustment"]=="UNKNOWN" or reference["price_adjustment"]=="UNKNOWN":
            errors.append("UNKNOWN_ADJUSTMENT")
        elif primary["price_adjustment"]!=reference["price_adjustment"]:
            errors.append("ADJUSTMENT_MISMATCH")
        if primary["market_scope"]!="REGULAR_ONLY" or reference["market_scope"]!="REGULAR_ONLY":
            errors.append("REGULAR_SCOPE_UNVERIFIED")
    return dict(schema="C3_PRICE_PROVENANCE_GATE_V1",
                metadata_claims_consistent=not errors,
                independently_verified=False,
                regular_only_certified=False,
                trade_approved=False,orders_enabled=False,
                errors=errors,
                note="SELF_REPORTED_METADATA_NEVER_CERTIFIES_PROVIDER_OR_SESSION")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--primary-meta",required=True)
    p.add_argument("--reference-meta",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=inspect(json.loads(Path(a.primary_meta).read_text(encoding="utf-8")),
                   json.loads(Path(a.reference_meta).read_text(encoding="utf-8")))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result["metadata_claims_consistent"] else 2)

if __name__=="__main__":
    main()
