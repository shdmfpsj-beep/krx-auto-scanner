"""Run provisional TOP2 research on pykrx bars; never certify or trade."""
import argparse
import csv
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from c3_price_concordance_v1 import read_rows
from c3_top2_research_readiness_v1 import build

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
    result=report(plans,read_rows(a.prices),manifest)
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status=result["research_status"],coverage=result["coverage"],
                          trade_approved=False,orders_enabled=False),ensure_ascii=False))

if __name__=="__main__":
    main()
