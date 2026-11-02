"""C3 v19 calendar-checked forward observation, research only.
Reference calendar is a hypothesis, not certified KRX session proof.
"""
import argparse,csv,json,math
from datetime import datetime,date,timedelta,timezone
from pathlib import Path

KST=timezone(timedelta(hours=9))

def valid_price(value):
    try:
        n=float(value)
        return n if math.isfinite(n) and n>0 else None
    except (ValueError,TypeError):return None

def evaluate(registry,calendar,prices,asof):
    days=sorted(set(date.fromisoformat(x) for x in calendar if date.fromisoformat(x)<=asof))
    index={d:i for i,d in enumerate(days)}
    by_key={}
    for row in prices:
        key=(row.get("ticker","").zfill(6),row.get("date",""))
        by_key.setdefault(key,[]).append(row)
    output=[]
    for plan in registry:
        ticker=plan.get("ticker","").zfill(6)
        item={"ticker":ticker,"key":plan.get("key"),"status":"WAIT","next_open":None,"filled":None}
        try:
            registration=datetime.fromisoformat(plan["registered_utc"].replace("Z","+00:00"))
            origin=date.fromisoformat(plan["price_date"])
            if registration.tzinfo is None:raise ValueError("timezone missing")
            start=max(origin,registration.astimezone(KST).date())
            if start not in index:
                item["status"]="REFERENCE_DATE_UNVERIFIED"
            elif index[start]+1>=len(days):
                item["status"]="NEXT_SESSION_PENDING"
            else:
                nxt=days[index[start]+1]
                item["next_date"]=nxt.isoformat()
                matches=by_key.get((ticker,nxt.isoformat()),[])
                if len(matches)!=1:
                    item["status"]="NEXT_PRICE_MISSING_OR_DUPLICATE"
                else:
                    value=valid_price(matches[0].get("open"))
                    if value is None:item["status"]="NEXT_OPEN_INVALID"
                    else:
                        item["status"]="NEXT_OPEN_OBSERVED_UNCERTIFIED"
                        item["next_open"]=value
        except (ValueError,KeyError,TypeError):
            item["status"]="INVALID_REGISTRATION"
        output.append(item)
    counts={}
    for item in output:counts[item["status"]]=counts.get(item["status"],0)+1
    return {"schema":"C3_FORWARD_CALENDAR_AUDIT_V19","denominator":len(registry),
      "status_counts":counts,"observations":output,"range_opportunity_rate":None,
      "fills":None,"source_scope":"REFERENCE_ETF_CALENDAR_NOT_CERTIFIED",
      "note":"No later open substitution. No buy ranges, fills, or returns inferred."}

def read_csv(path):
    with open(path,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--registry",required=True)
    p.add_argument("--calendar",required=True)
    p.add_argument("--prices",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--asof",required=True)
    a=p.parse_args()
    cal=json.loads(Path(a.calendar).read_text(encoding="utf-8"))
    result=evaluate(read_csv(a.registry),cal["dates"],read_csv(a.prices),date.fromisoformat(a.asof))
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result["status_counts"]))
