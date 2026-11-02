"""C3 v18 prospective opportunity audit. Observed opens only; no fills inferred."""
import argparse,csv,json
from datetime import date,datetime,timezone
from pathlib import Path

def audit(registry,observations):
    by_ticker={}
    for r in observations:
        t=r.get("ticker","").zfill(6)
        by_ticker.setdefault(t,[]).append(r)
    results=[]
    for plan in registry:
        ticker=plan.get("ticker","").zfill(6)
        registered=plan.get("registered_utc","")
        try:
            registration=datetime.fromisoformat(registered.replace("Z","+00:00"))
            price_day=date.fromisoformat(plan["price_date"])
        except (ValueError,KeyError):
            results.append({"ticker":ticker,"status":"INVALID_REGISTRATION","next_open":None})
            continue
        if registration.tzinfo is None:
            results.append({"ticker":ticker,"status":"INVALID_REGISTRATION","next_open":None})
            continue
        later=[]
        for o in by_ticker.get(ticker,[]):
            try:day=date.fromisoformat(o.get("date",""))
            except ValueError:continue
            if day>price_day and day>registration.astimezone(timezone.utc).date():
                later.append((day,o))
        later.sort(key=lambda x:x[0])
        if not later:
            results.append({"ticker":ticker,"status":"NEXT_SESSION_UNOBSERVED","next_open":None})
            continue
        day,row=later[0]
        # An observation later in the file is not proof that a skipped session did not exist.
        if row.get("is_immediate_next_session")!="True":
            status="NEXT_SESSION_CALENDAR_UNVERIFIED"
        else:
            status="NEXT_OPEN_OBSERVED" if row.get("open") not in ("",None) else "NEXT_OPEN_MISSING"
        results.append({"ticker":ticker,"status":status,"next_date":day.isoformat(),
                        "next_open":row.get("open") if status=="NEXT_OPEN_OBSERVED" else None,
                        "fill_inferred":False})
    counts={}
    for r in results:counts[r["status"]]=counts.get(r["status"],0)+1
    return {"schema":"C3_FORWARD_OPPORTUNITY_V18","registered_count":len(registry),
            "status_counts":counts,"observations":results,"fills":None,
            "opportunity_rate":None,"reason":"No certified range or session-calendar proof; no inferred fills."}

def read(path):
    if not Path(path).exists():return []
    with open(path,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--registry",required=True)
    p.add_argument("--observations",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=audit(read(a.registry),read(a.observations))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result["status_counts"]))
