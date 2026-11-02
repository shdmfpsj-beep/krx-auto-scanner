"""Prospective C3 research snapshot registry. No orders or fills."""
import argparse,csv,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

def register(source,output,run,attempt):
    payload=Path(source).read_bytes()
    obj=json.loads(payload)
    key=hashlib.sha256((run+":"+attempt+":").encode()+payload).hexdigest()
    path=Path(output)
    old=[]
    if path.exists():
        with path.open(encoding="utf-8",newline="") as f:
            old=list(csv.DictReader(f))
    if any(r["key"]==key for r in old):
        return "ALREADY_REGISTERED"
    picks=obj.get("provisional_watch_top2",[])
    if len(picks)>2:raise ValueError("too many picks")
    fields=["key","run","attempt","registered_utc","ticker","price_date","source_hash","status"]
    now=datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        if not old:writer.writeheader()
        for p in picks:
            writer.writerow({"key":key,"run":run,"attempt":attempt,"registered_utc":now,
                "ticker":p.get("ticker"),"price_date":p.get("price_date"),
                "source_hash":hashlib.sha256(payload).hexdigest(),"status":"RESEARCH_ONLY"})
    return "REGISTERED"

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--run",required=True)
    p.add_argument("--attempt",required=True)
    a=p.parse_args()
    print(register(a.source,a.output,a.run,a.attempt))
