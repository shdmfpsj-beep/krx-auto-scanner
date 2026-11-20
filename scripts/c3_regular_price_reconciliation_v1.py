#!/usr/bin/env python3
"""C3 trade price safety: compare scanner closes to independently supplied declarations.

A user CSV is NOT official certification. Treat any mismatch as a visible
blocker; even a match requires separately authenticated KRX regular-session
provenance before buy approval. Do not adjust structural stops or targets
by a simple raw close difference.
"""
from __future__ import annotations
import argparse,csv,json,hashlib,math
from pathlib import Path

SCHEMA="C3_DECLARED_REGULAR_CLOSE_RECONCILIATION_V1_NO_TRADES"

def parse_positive(text):
    try:value=float(text)
    except (TypeError,ValueError):raise ValueError("INVALID_REFERENCE_PRICE")
    if not math.isfinite(value) or value<=0 or not value.is_integer():
        raise ValueError("INVALID_REFERENCE_PRICE")
    return int(value)

def reference_records(path):
    if not path:return {}
    with open(path,encoding="utf-8-sig",newline="") as stream:
        rows=list(csv.DictReader(stream))
    required={"ticker","asof","regular_close","source_url","source_scope"}
    if rows and not required<=set(rows[0]):
        raise ValueError("REQUIRED_REFERENCE_PROVENANCE_MISSING")
    out={}
    for r in rows:
        ticker=str(r["ticker"]).zfill(6)
        if not ticker.isdigit() or len(ticker)!=6 or ticker in out:
            raise ValueError("REFERENCE_DUPLICATE_OR_BAD_CODE")
        close=parse_positive(r["regular_close"])
        source_url=str(r["source_url"]).strip()
        scope=str(r["source_scope"]).strip()
        if not source_url.startswith("https://") or len(source_url)>1000:
            raise ValueError("REFERENCE_URL_MISSING")
        if scope!="KRX_REGULAR_0900_1530_DECLARED":
            raise ValueError("REFERENCE_SESSION_SCOPE_INVALID")
        out[ticker]=dict(reference_date=r["asof"],reference_close=close,
                         reference_url=source_url,source_scope=scope)
    return out

def compare(ticker,asof,model_close,ref):
    close=parse_positive(model_close)
    if ref is None:
        return dict(ticker=ticker,asof=asof,scanner_close=close,
          regular_reference_close=None,price_state="REGULAR_REFERENCE_NOT_SUPPLIED",
          close_difference_krw=None,close_difference_pct=None,
          source_url=None,model_price_repricing_needed=True,
          authenticated_regular_source=False,
          structure_stop_unchanged_until_new_dated_OHLCV=True,
          buy_approved=False,orders_enabled=False)
    if str(ref["reference_date"])!=str(asof):
        raise ValueError("REFERENCE_DATE_DOES_NOT_MATCH_SOURCE_DATE")
    other=parse_positive(ref["reference_close"])
    state=("EXTERNAL_REFERENCE_DECLARATION_MATCH_UNAUDITED" if close==other
           else "EXTERNAL_REFERENCE_DECLARATION_MISMATCH")
    return dict(ticker=ticker,asof=asof,scanner_close=close,
      regular_reference_close=other,price_state=state,
      close_difference_krw=other-close,
      close_difference_pct=round(100*(other/close-1),3),
      source_url=ref["reference_url"],model_price_repricing_needed=True,
      authenticated_regular_source=False,
      structure_stop_unchanged_until_new_dated_OHLCV=True,
      buy_approved=False,orders_enabled=False)

def run(ranked,output,reference=None):
    with open(ranked,encoding="utf-8-sig",newline="") as stream:
        rows=list(csv.DictReader(stream))
    if not rows or len({r["ticker"] for r in rows})!=len(rows):
        raise ValueError("RANKED_SOURCE_INVALID")
    references=reference_records(reference)
    audits=[compare(str(r["ticker"]).zfill(6),str(r["asof"]),r["close"],
                    references.get(str(r["ticker"]).zfill(6))) for r in rows]
    missing=[x for x in audits if x["regular_reference_close"] is None]
    mismatch=[x for x in audits if x["price_state"]=="EXTERNAL_REFERENCE_DECLARATION_MISMATCH"]
    # Trade approval NEVER toggled here; authenticated source reconciliation
    # is an independent future feature, not inferred from user-supplied CSV.
    status=dict(schema=SCHEMA,candidate_count=len(audits),
       declared_reference_count=len(audits)-len(missing),
       missing_reference_count=len(missing),mismatch_count=len(mismatch),
       mismatch_tickers=[x["ticker"] for x in mismatch],
       matching_reference_not_official_certification=True,
       regular_session_price_authoritatively_certified=False,
       any_repricing_allowed=False,
       trade_approved=False,orders_enabled=False)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with (output/"c3_regular_price_declared_comparison.csv").open(
        "w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(audits[0]))
        w.writeheader();w.writerows(audits)
    status["audit_sha256"]=hashlib.sha256(
       (output/"c3_regular_price_declared_comparison.csv").read_bytes()).hexdigest()
    (output/"c3_regular_price_reconciliation_status.json").write_text(
        json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    return status,audits

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--ranked",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--reference-csv",help="Optional independent declaration; NOT trusted certification")
    a=p.parse_args()
    status,_=run(a.ranked,a.output,a.reference_csv)
    print(json.dumps(status,ensure_ascii=False))
