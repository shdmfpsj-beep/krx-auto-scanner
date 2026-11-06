"""Read-only current-date KRX EOD probe using the existing optional connection.

    Never logs the auth key. Authenticated EOD is not automatically a
    09:00-15:30-only feed and is never an order authorization.
"""
import argparse
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from c3_price_concordance_v1 import FIELDS,read_rows
from krx_official_eod_v65 import collect,official_rows


def compare_snapshot(prices,official,asof):
    date.fromisoformat(asof)
    compared=[]
    for (ticker,day),bar in sorted(prices.items()):
        if day!=asof:
            continue
        ref=official.get(ticker)
        if ref is None:
            compared.append(dict(ticker=ticker,date=day,result="OFFICIAL_REFERENCE_MISSING",fields=[]))
            continue
        values=ref[1]
        mismatches=[k for k in FIELDS if bar[k]!=values.get(k)]
        compared.append(dict(ticker=ticker,date=day,result="MISMATCH" if mismatches else "MATCH",fields=mismatches))
    return dict(asof=asof,compared_rows=len(compared),
                result_counts=dict(Counter(x["result"] for x in compared)),results=compared,
                comparison_is_adjusted_vs_official_basis_unverified=True,
                regular_only_certified=False,trade_approved=False,orders_enabled=False)


def run(asofs,prices,outdir,auth_key=None,collector=collect):
    if not asofs or len(set(asofs))!=len(asofs):
        raise ValueError("EMPTY_OR_DUPLICATE_PROBE_DATES")
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    records=[]
    for day in sorted(asofs):
        if date.fromisoformat(day).isoformat()!=day:
            raise ValueError("NONCANONICAL_PROBE_DATE")
        folder=root/day
        manifest=collector(day,folder,auth_key=auth_key)
        official=official_rows(folder,manifest)
        comparison=compare_snapshot(prices,official,day)
        records.append(dict(asof=day,status=manifest["status"],
                            authenticated=manifest["krx_eod_authenticated"],
                            official_market_rows=manifest["official_market_rows"],
                            comparison=comparison))
    report=dict(schema="C3_CURRENT_OFFICIAL_SNAPSHOT_PROBE_V1",dates=records,
                api_key_recorded=False,regular_only_certified=False,
                trade_approved=False,orders_enabled=False,decision="CASH")
    (root/"official_snapshot_probe.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument("--asof",nargs="+",required=True)
    p.add_argument("--prices",required=True);p.add_argument("--outdir",required=True)
    a=p.parse_args()
    report=run(a.asof,read_rows(a.prices),a.outdir,auth_key=os.environ.get("KRX_AUTH_KEY"))
    # Allowlisted summary only. Never print request objects or key material.
    print(json.dumps({"dates":[dict(asof=r["asof"],status=r["status"],rows=r["official_market_rows"])
                               for r in report["dates"]],"orders_enabled":False}))


if __name__=="__main__":
    main()
