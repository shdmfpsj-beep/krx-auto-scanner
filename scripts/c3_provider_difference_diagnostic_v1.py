"""Summarize experimental provider discrepancies without certifying either feed."""
import argparse
import json
from collections import Counter,defaultdict
from pathlib import Path

def summarize(payload):
    by_ticker=defaultdict(lambda:{"rows":0,"matches":0,"mismatches":0,"missing":0,"field_mismatches":Counter()})
    for item in payload["results"]:
        rec=by_ticker[item["ticker"]]
        rec["rows"]+=1
        if item["result"]=="MATCH":
            rec["matches"]+=1
        elif item["result"]=="MISMATCH":
            rec["mismatches"]+=1
            rec["field_mismatches"].update(item.get("fields",[]))
        else:
            rec["missing"]+=1
    return {"schema":"C3_PROVIDER_DIFFERENCE_DIAGNOSTIC_V1",
            "status":"UNVERIFIED_PRICE_DISCREPANCY",
            "upstream_independence_verified":False,
            "adjustment_basis_verified":False,
            "regular_only_certified":False,
            "trade_approved":False,"orders_enabled":False,
            "tickers":{ticker:{**{k:v for k,v in rec.items() if k!="field_mismatches"},
                                "field_mismatches":dict(rec["field_mismatches"])}
                       for ticker,rec in sorted(by_ticker.items())}}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=summarize(json.loads(Path(a.input).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":
    main()
