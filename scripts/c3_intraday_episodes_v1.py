"""C3 research: event-level intraday watch-zone episodes, not simulated orders.
Rows are verified snapshots; gaps > 30 minutes split episodes to avoid claiming continuous presence.
"""
import argparse,csv,json
from datetime import datetime,timedelta
from pathlib import Path
def episodes(rows,max_gap_minutes=30):
    grouped={}
    for r in rows:
        if r.get("status")!="WATCH_ZONE":continue
        try:
            stamp=datetime.fromisoformat(r["observed_at"])
            if stamp.tzinfo is None:continue
            price=float(r["observed_price"])
            if price<=0:continue
        except (KeyError,ValueError,TypeError):continue
        grouped.setdefault(r["ticker"],[]).append((stamp,price))
    out=[]
    for ticker,records in sorted(grouped.items()):
        records.sort()
        current=None
        for stamp,price in records:
            if current is None or stamp-current["last_dt"]>timedelta(minutes=max_gap_minutes) or stamp.date()!=current["last_dt"].date():
                if current:out.append(current)
                current={"ticker":ticker,"first_dt":stamp,"last_dt":stamp,"first_price":price,"last_price":price,"min_price":price,"max_price":price,"observations":1}
            elif stamp>current["last_dt"]:
                current["last_dt"]=stamp;current["last_price"]=price
                current["min_price"]=min(current["min_price"],price)
                current["max_price"]=max(current["max_price"],price)
                current["observations"]+=1
        if current:out.append(current)
    return [{"ticker":e["ticker"],"first_observed":e["first_dt"].isoformat(),
             "last_observed":e["last_dt"].isoformat(),"first_price":e["first_price"],
             "last_price":e["last_price"],"min_observed_price":e["min_price"],
             "max_observed_price":e["max_price"],"observations":e["observations"],
             "is_fill":False,"continuous_presence_proven":False} for e in out]
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default="output/c3_intraday_observations.csv")
    p.add_argument("--out",default="output/c3_intraday_episodes.json")
    a=p.parse_args()
    with open(a.ledger,encoding="utf-8",newline="") as f:rows=list(csv.DictReader(f))
    result={"schema":"c3_intraday_watch_episodes_v1","events":episodes(rows),
            "paper_fills_verified":False,"trade_approved":False}
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"watch_zone_episodes":len(result["events"]),"paper_fills_verified":False}))
if __name__=="__main__":main()
