#!/usr/bin/env python3
"""C3 optional *read-only* independent-date KRX OpenAPI availability recheck.

A current official daily EOD response is useful corroboration, not proof of
market-wide 09:00–15:30 regular-only OHLCV or investor flows. If a day returns
an empty official OutBlock_1, never replace it with 11/05 or cache 11/06.

All official raw CSVs stay under the chosen private temp working directory.
Published output contains status/counts and SHA hashes only.
"""
import argparse
import json
import os
from pathlib import Path

from krx_official_eod_v65 import collect

def run(day,outdir,auth_key,source_summary=None,collect_fn=collect):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    # Source data must be a date-locked query, not a later-price replacement.
    if len(day)!=10 or day[4]!='-' or day[7]!='-':
        raise ValueError("EXPECTED_ISO_DAY")
    same=collect_fn(day,out/"private"/"target",auth_key)
    if same["asof"]!=day:raise ValueError("OFFICIAL_DATE_LOCK_MISMATCH")
    # Earlier verified 11/05 control only when Nov6 official target unavailable;
    # never promote control-day prices to the requested Nov6 decision.
    prior=None
    if same.get("official_dataset_usable") is not True and day=="2026-11-06":
        prior=collect_fn("2026-11-05",out/"private"/"prior_control",auth_key)
        if prior["asof"]!="2026-11-05":
            raise ValueError("OFFICIAL_CONTROL_DATE_MISMATCH")
    manifest=dict(
        schema="C3_OFFICIAL_DATED_READ_ONLY_RECHECK_V19",
        requested_asof=day,
        official_target_status=same["status"],
        official_target_rows=same.get("official_market_rows",0),
        official_target_authenticated=same.get("krx_eod_authenticated",False),
        raw_response_sha256=same.get("raw_response_sha256",{}),
        original_source_price_basis="UNADJUSTED_AS_TRADED",
        original_source_snapshot_sha256=(source_summary or {}).get(
            "actual_data",{}).get("original_snapshot_sha256"),
        same_ultimate_krx_origin_not_independent_vendor=True,
        official_daily_eod_not_regular_only_certified=True,
        independent_0900_1530_price_certified=False,
        independent_0900_1530_volume_certified=False,
        independent_0900_1530_turnover_certified=False,
        independent_historical_issuer_census_certified=False,
        target_prices_were_never_replaced_with_prior_control=True,
        complete_forward_horizon_result_count=0,
        trading_approved=False,orders_enabled=False,decision="CASH",
        prior_day_control=(dict(asof=prior["asof"],status=prior["status"],
                                rows=prior.get("official_market_rows",0))
                           if prior is not None else None))
    path=out/"c3_official_dated_recheck_v19.json"
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("C3_OFFICIAL_DATE_RECHECK="+json.dumps({
      "target":day,"status":manifest["official_target_status"],
      "rows":manifest["official_target_rows"],
      "prior_control":manifest["prior_day_control"],
      "regular_certified":False,"trading_approved":False
    },ensure_ascii=False),flush=True)
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--original-audit",default="reports/c3_operations_v18_20261107/execution_evidence.json")
    args=p.parse_args()
    audit=json.loads(Path(args.original_audit).read_text()) if Path(args.original_audit).exists() else {}
    run(args.date,args.outdir,os.environ.get("KRX_AUTH_KEY",""),audit)

if __name__=="__main__":main()
