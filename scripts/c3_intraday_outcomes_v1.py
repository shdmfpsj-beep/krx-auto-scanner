"""Prospective watch-zone outcomes from later verified snapshots only.
NOT actual fills, returns, intrabar extrema, or an investable backtest.
"""
import argparse,csv,json
from datetime import datetime,timedelta
from pathlib import Path
from c3_intraday_episodes_v1 import episodes
def outcomes(rows,minutes=(30,60,120)):
    events=episodes(rows)
    observations={}
    for r in rows:
        try:
            t=datetime.fromisoformat(r["observed_at"]);price=float(r["observed_price"])
            if t.tzinfo is None or price<=0:continue
            if r["status"] not in ("WATCH_ZONE","BELOW_ZONE","ABOVE_ZONE"):continue
            observations.setdefault(r["ticker"],[]).append((t,price))
        except (ValueError,KeyError,TypeError):continue
    result=[]
    for e in events:
        start=datetime.fromisoformat(e["first_observed"]);base=e["first_price"]
        for horizon in minutes:
            end=start+timedelta(minutes=horizon)
            later=[(t,p) for t,p in observations.get(e["ticker"],[])
                   if start<t<=end and t.date()==start.date()]
            item={"ticker":e["ticker"],"entry_observed_at":e["first_observed"],
                  "reference_price":base,"horizon_minutes":horizon,
                  "later_observations":len(later),"is_realized_return":False,
                  "is_trade_fill":False,"complete_path_verified":False}
            if later:
                vals=[p for _,p in later]
                item.update(min_observed_price=min(vals),max_observed_price=max(vals),
                    min_observed_change_pct=round((min(vals)/base-1)*100,3),
                    max_observed_change_pct=round((max(vals)/base-1)*100,3),
                    last_observed_at=max(t for t,_ in later).isoformat())
            else:item["status"]="NO_FOLLOWUP_OBSERVATION"
            result.append(item)
    return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default="output/c3_intraday_observations.csv")
    p.add_argument("--out",default="output/c3_intraday_outcomes.json")
    a=p.parse_args()
    with open(a.ledger,encoding="utf-8",newline="") as f:rows=list(csv.DictReader(f))
    results=outcomes(rows)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"schema":"c3_intraday_observed_outcomes_v1",
         "results":results,"realized_pnl_available":False,"trade_approved":False},
         ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"evaluated_event_horizons":len(results),"followup_observed":sum("min_observed_price" in r for r in results),"realized_pnl_available":False}))
if __name__=="__main__":main()
