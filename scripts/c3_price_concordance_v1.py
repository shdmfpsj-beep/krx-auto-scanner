"""Independent regular-session price concordance gate (research only).

Both CSVs must come from separately identified providers. A pykrx export
compared to another pykrx export is NOT independent confirmation.
Passing OHLC equality does not itself certify 09:00-15:30 coverage.
"""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

FIELDS = ("open", "high", "low", "close", "volume")
KEY = ("ticker", "date")

def provider_families(name):
    """Possible upstreams, not a certification of any vendor declaration.

    pykrx adjusted-by-date can route to NAVER; an unspecified pykrx request
    cannot establish independence from either KRX or NAVER.
    """
    label="".join(c for c in name.casefold() if c.isalnum())
    if "pykrx" in label:
        if "unadjusted" in label:
            return {"krx"}
        if "adjusted" in label:
            return {"naver"}
        return {"krx","naver"}
    if "naver" in label:
        return {"naver"}
    if label in ("krx","krxdata","koreaxchange","koreaexchange") or (
            "krx" in label and ("export" in label or "unverified" in label)):
        return {"krx"}
    if "yahoo" in label:
        return {"yahoo"}
    return {label}

def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("EMPTY_SOURCE")
    if not set(KEY + FIELDS).issubset(rows[0]):
        raise ValueError("MISSING_OHLCV_COLUMNS")
    result = {}
    for row in rows:
        key = tuple(row[k].strip() for k in KEY)
        if not all(key):
            raise ValueError("EMPTY_TICKER_OR_DATE")
        if key in result:
            raise ValueError("DUPLICATE_TICKER_DATE")
        vals = {k: float(row[k]) for k in FIELDS}
        if any(not math.isfinite(v) for v in vals.values()) or vals["volume"] < 0 or any(vals[k] <= 0 for k in FIELDS[:4]):
            raise ValueError("INVALID_NONFINITE_OR_NONPOSITIVE_PRICE")
        if not (vals["low"] <= min(vals["open"], vals["close"]) <=
                max(vals["open"], vals["close"]) <= vals["high"]):
            raise ValueError("INVALID_OHLC")
        result[key] = vals
    return result

def compare(primary, reference, primary_provider, reference_provider,
            reference_regular_only=False,*,observation_only=False):
    if not primary_provider or not primary_provider.strip() or not reference_provider or not reference_provider.strip():
        raise ValueError("PROVIDER_PROVENANCE_REQUIRED")
    shared_upstream=bool(provider_families(primary_provider)&provider_families(reference_provider))
    if shared_upstream and not observation_only:
        raise ValueError("NON_INDEPENDENT_PROVIDER")
    a, b = read_rows(primary), read_rows(reference)
    rows = []
    for key in sorted(a):
        if key not in b:
            rows.append(dict(ticker=key[0], date=key[1],
                             result="MISSING_REFERENCE", fields=[]))
            continue
        diffs = [field for field in FIELDS if a[key][field] != b[key][field]]
        rows.append(dict(ticker=key[0], date=key[1],
                         result="MISMATCH" if diffs else "MATCH", fields=diffs))
    for key in sorted(set(b) - set(a)):
        rows.append(dict(ticker=key[0], date=key[1],
                         result="REFERENCE_ONLY", fields=[]))
    rows.sort(key=lambda r: (r["ticker"], r["date"]))
    counts = dict(Counter(r["result"] for r in rows))
    # A reference with unclear after-hours scope cannot certify regular-only.
    certified = bool(not shared_upstream and reference_regular_only and rows and
                     all(r["result"] == "MATCH" for r in rows))
    return dict(schema="C3_INDEPENDENT_PRICE_CONCORDANCE_V1",
                primary_provider=primary_provider,
                reference_provider=reference_provider,
                reference_regular_only_claimed=bool(reference_regular_only),
                source_lineage_overlap=shared_upstream,
                provenance_warning="NON_INDEPENDENT_PROVIDER" if shared_upstream else None,
                comparison_count=len(rows), result_counts=counts,
                regular_only_concordance_passed=certified,
                regular_only_certified=False,  # provider labels alone are not certification
                trade_approved=False, orders_enabled=False,
                results=rows)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--primary", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--primary-provider", required=True)
    p.add_argument("--reference-provider", required=True)
    p.add_argument("--reference-regular-only", action="store_true")
    p.add_argument("--output", required=True)
    p.add_argument("--observation-only", action="store_true",
                   help="Record expected mismatches without failing CI; never certifies prices")
    args = p.parse_args()
    result = compare(args.primary, args.reference, args.primary_provider,
                     args.reference_provider, args.reference_regular_only,
                     observation_only=args.observation_only)
    Path(args.output).write_text(json.dumps(result, indent=2,
                                  ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"},
                     ensure_ascii=False))
    raise SystemExit(0 if args.observation_only or result["regular_only_concordance_passed"] else 2)

if __name__ == "__main__":
    main()
