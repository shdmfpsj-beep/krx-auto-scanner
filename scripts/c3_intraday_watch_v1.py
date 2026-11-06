"""Read-only C3 TOP2 intraday watch. No trades, no fake fills.
Input JSON: {"asof":"2026-11-02T10:00:00+09:00","quotes":[{"ticker":"271560","price":112000,"observed_at":"2026-11-02T10:00:00+09:00","source":"verified_provider"}]}
Only a genuine timestamped regular-session provider quote can trigger a watch.
"""
import argparse,csv,json
from datetime import datetime,time,timedelta,timezone
from pathlib import Path
KST=timezone(timedelta(hours=9))
def evaluate(plans,quotes,now):
    if now.tzinfo is None: raise ValueError("timezone required")
    local=now.astimezone(KST)
    if local.weekday()>4 or not time(9,0)<=local.time()<time(15,30):
        return {"status":"OUTSIDE_REGULAR_SESSION","trade_approved":False,"alerts":[]}
    out=[]
    by={q.get("ticker"):q for q in quotes}
    for p in plans:
        ticker=p["ticker"];q=by.get(ticker)
        item={"ticker":ticker,"name":p["name"],"status":"NO_VERIFIED_QUOTE","paper_filled":False}
        if q:
            try:
                raw_ts=datetime.fromisoformat(q["observed_at"])
                if raw_ts.tzinfo is None or raw_ts.utcoffset() is None:
                    raise ValueError("UNZONED_QUOTE_TIMESTAMP")
                ts=raw_ts.astimezone(KST)
                price=float(q["price"])
                age=(local-ts).total_seconds()
                if q.get("source")=="verified_provider" and 0<=age<=900 and price>0 and ts.date()==local.date() and time(9)<=ts.time()<time(15,30):
                    lo,hi=float(p["watch_low"]),float(p["watch_high"])
                    item.update(status="WATCH_ZONE" if lo<=price<=hi else ("BELOW_ZONE" if price<lo else "ABOVE_ZONE"),observed_price=price,observed_at=ts.isoformat())
                    if price<=float(p["structure_stop"]):item["risk_note"]="INTRADAY_BELOW_STOP_NOT_A_CLOSE_STOP"
            except (KeyError,TypeError,ValueError,OverflowError):
                pass
        out.append(item)
    return {"status":"READ_ONLY_MONITOR","trade_approved":False,"alerts":out}
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--plans",default="config/c3_paper_top2_plans.csv")
    a.add_argument("--quotes",required=True)
    a.add_argument("--out",default="c3_intraday_watch.json")
    a.add_argument("--now",default=None)
    x=a.parse_args()
    with open(x.plans,encoding="utf-8-sig",newline="") as f:plans=list(csv.DictReader(f))
    data=json.loads(Path(x.quotes).read_text(encoding="utf-8"))
    now=datetime.fromisoformat(x.now) if x.now else datetime.now(KST)
    result=evaluate(plans,data.get("quotes",[]),now)
    result["checked_at"]=now.isoformat()
    result["quote_source"]="external_timestamped_input_required"
    Path(x.out).parent.mkdir(parents=True,exist_ok=True)
    Path(x.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
