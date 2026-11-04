"""Read-only C3 TOP2 research readiness report.

No claim of independent provider certification, trade fills or strategy PnL.
"""
import argparse
import csv
import json
from pathlib import Path
from c3_price_concordance_v1 import read_rows
from c3_price_provenance_gate_v1 import inspect
from c3_entry_style_comparison_v1 import build as entry_build
from c3_forward_horizon_observation_v1 import build as horizon_build
from c3_no_fill_opportunity_v1 import build as no_fill_build

def build(plans,prices,primary_meta,reference_meta):
    items=list(plans)
    provenance=inspect(primary_meta,reference_meta)
    entry=entry_build(items,prices)
    horizons=horizon_build(items,prices)
    missed=no_fill_build(items,prices)
    coverage={p["ticker"]:dict(
        observed_sessions=h["horizons"][-1]["observed_sessions"],
        five_session_complete=h["horizons"][0]["complete"],
        ten_session_complete=h["horizons"][1]["complete"],
        twenty_session_complete=h["horizons"][2]["complete"])
        for p,h in zip(items,horizons["plans"])}
    return dict(schema="C3_TOP2_RESEARCH_READINESS_V1",
                provenance=provenance,coverage=coverage,
                entry_opportunities=entry["plans"],
                missed_opportunities=missed["plans"],
                forward_observations=horizons["plans"],
                data_ready_for_certified_backtest=False,
                independently_verified=False,
                regular_only_certified=False,
                actual_trade_fills_verified=False,
                strategy_profitability_verified=False,
                trade_approved=False,orders_enabled=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--primary-meta",required=True)
    p.add_argument("--reference-meta",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with Path(a.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    result=build(plans,read_rows(a.prices),
                 json.loads(Path(a.primary_meta).read_text(encoding="utf-8")),
                 json.loads(Path(a.reference_meta).read_text(encoding="utf-8")))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(schema=result["schema"],coverage=result["coverage"],
                          provenance_errors=result["provenance"]["errors"],
                          trade_approved=False,orders_enabled=False),ensure_ascii=False))

if __name__=="__main__":
    main()
