"""Accumulate read-only C3 intraday observations without inventing fills.
Only a provider-verified, fresh observation is recorded. Idempotent by ticker/timestamp.
"""
import argparse,csv,json
from pathlib import Path
FIELDS=["ticker","name","observed_at","observed_price","status","risk_note"]
def merge(existing,watch):
    if watch.get("status")!="READ_ONLY_MONITOR" or watch.get("trade_approved") is not False:
        return existing,[]
    seen={(x["ticker"],x["observed_at"]) for x in existing}
    new=[]
    for item in watch.get("alerts",[]):
        if item.get("status") not in ("WATCH_ZONE","BELOW_ZONE","ABOVE_ZONE"):continue
        if item.get("paper_filled") is not False:continue
        if not item.get("observed_at") or not item.get("observed_price"):continue
        key=(item["ticker"],item["observed_at"])
        if key in seen:continue
        row={k:str(item.get(k,"")) for k in FIELDS}
        new.append(row);seen.add(key)
    return sorted(existing+new,key=lambda x:(x["observed_at"],x["ticker"])),new
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--watch",required=True)
    p.add_argument("--ledger",default="output/c3_intraday_observations.csv")
    p.add_argument("--out",default="output/c3_intraday_observations.csv")
    a=p.parse_args()
    src=Path(a.ledger)
    existing=[]
    if src.exists():
        with src.open(encoding="utf-8",newline="") as f:existing=list(csv.DictReader(f))
    watch=json.loads(Path(a.watch).read_text(encoding="utf-8"))
    rows,new=merge(existing,watch)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    print(json.dumps({"observations_total":len(rows),"new_verified_observations":len(new),"paper_fills":0,"trade_approved":False}))
if __name__=="__main__":main()
