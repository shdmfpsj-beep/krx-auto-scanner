"""Run provisional TOP2 research on pykrx bars; never certify or trade."""
import argparse
import csv
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from c3_price_concordance_v1 import read_rows
from c3_top2_research_readiness_v1 import build

def validate_export(plans,prices,manifest):
    """Reject incomplete or inconsistent actual collector artifacts."""
    tickers={p["ticker"] for p in plans}
    observed={ticker for ticker,_ in prices}
    if len(plans)!=2 or len(tickers)!=2:
        raise ValueError("EXPECTED_TWO_UNIQUE_PLANS")
    if manifest.get("failures"):
        raise ValueError("COLLECTOR_FAILURES")
    if manifest.get("provider")!="pykrx" or manifest.get("price_adjustment")!="ADJUSTED":
        raise ValueError("UNEXPECTED_SOURCE_METADATA")
    if manifest.get("rows")!=len(prices):
        raise ValueError("MANIFEST_ROW_COUNT_MISMATCH")
    if set(manifest.get("tickers",[]))!=observed or observed!=tickers:
        raise ValueError("MISSING_OR_UNEXPECTED_TICKER")
    if not prices:
        raise ValueError("EMPTY_PRICE_DATA")
    end=manifest.get("end","")
    if not end or any(day>end for _,day in prices):
        raise ValueError("PRICE_AFTER_MANIFEST_END")
    return True

def report(plans,prices,manifest):
    source=dict(provider="pykrx",upstream="KRX_UNVERIFIED",
                market_scope="UNKNOWN",price_adjustment="ADJUSTED",
                timezone="Asia/Seoul",retrieved_at=datetime.now(timezone(timedelta(hours=9))).isoformat())
    # Do not invent an independent reference feed.
    result=build(plans,prices,source,dict(source))
    result["collector_manifest"]=manifest
    result["independent_reference_available"]=False
    result["research_status"]="PROVISIONAL_DATA_NOT_CERTIFIED"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with Path(a.plans).open(encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    prices=read_rows(a.prices)
    validate_export(plans,prices,manifest)
    result=report(plans,prices,manifest)
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status=result["research_status"],coverage=result["coverage"],
                          trade_approved=False,orders_enabled=False),ensure_ascii=False))

if __name__=="__main__":
    main()
