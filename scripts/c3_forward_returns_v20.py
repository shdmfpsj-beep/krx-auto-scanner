"""C3 v20: prospective 5/10/20 session close observation, no trade inference."""
import argparse,csv,json
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

def audit(registry,calendar,prices,asof):
    sessions=sorted({date.fromisoformat(x) for x in calendar if x<=asof})
    lookup={(r["ticker"].zfill(6),r["date"]):r for r in prices}
    results=[]
    for plan in registry:
        ticker=plan.get("ticker","").zfill(6)
        result={"ticker":ticker,"key":plan.get("key"),"horizons":{}}
        try:
            registered=datetime.fromisoformat(plan["registered_utc"].replace("Z","+00:00"))
            origin=date.fromisoformat(plan["price_date"])
            start=max(origin,registered.astimezone(timezone(timedelta(hours=9))).date())
            base=lookup.get((ticker,origin.isoformat()),{})
            close=float(base["close"])
            if close<=0 or start not in sessions:raise ValueError("bad base")
            for n in (5,10,20):
                i=sessions.index(start)+n
                if i>=len(sessions):
                    result["horizons"][str(n)]={"status":"PENDING"}
                else:
                    day=sessions[i].isoformat()
                    row=lookup.get((ticker,day),{})
                    try:
                        target=float(row["close"])
                        if target<=0:raise ValueError()
                        result["horizons"][str(n)]={"status":"OBSERVED_UNCERTIFIED",
                            "date":day,"close_change_pct":round(100*(target/close-1),3)}
                    except (KeyError,ValueError):
                        result["horizons"][str(n)]={"status":"PRICE_MISSING"}
        except (ValueError,KeyError,TypeError):
            result["status"]="BASE_OR_REGISTRATION_INVALID"
        results.append(result)
    return {"schema":"C3_FORWARD_RETURNS_V20","denominator":len(registry),
      "items":results,"fills":None,"trade_pnl":None,
      "note":"Reference calendar and prices unverified; close change is not a trade return."}

def read(path):
    with open(path,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    for flag in ("registry","calendar","prices","asof","output"):p.add_argument("--"+flag,required=True)
    a=p.parse_args()
    dates=json.loads(Path(a.calendar).read_text(encoding="utf-8"))["dates"]
    result=audit(read(a.registry),dates,read(a.prices),a.asof)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
