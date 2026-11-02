"""C3 v6 read-only join of dated daily bars to frozen registration keys.
Run: python scripts/c3_history_connector_v6.py --history reports/candidate_daily_history_v52.csv --registry reports/c3_registered_reclaim_registry_v1.json --out reports/c3_history_coverage_v6.json
No network, orders, approvals, alerts, or mutation of frozen registry.
"""
import argparse,csv,hashlib,json
from collections import defaultdict
from datetime import date
from pathlib import Path

def connect(history_path,registry_path):
    hp=Path(history_path);rp=Path(registry_path)
    registry=json.loads(rp.read_text(encoding="utf-8-sig"))
    setups=registry["setups"]
    if len(setups)!=registry["registered_count"] or len({s["setup_id"] for s in setups})!=len(setups):
        raise ValueError("frozen registry count or keys invalid")
    rows=defaultdict(list);sources=defaultdict(set);invalid=defaultdict(list)
    with hp.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        required={"ticker","date","open","high","low","close","volume","data_source"}
        if not required.issubset(reader.fieldnames or []):raise ValueError("history columns missing")
        for row in reader:
            t=row["ticker"].zfill(6)
            try:
                d=date.fromisoformat(row["date"])
                o,h,l,c,v=[float(row[k]) for k in ("open","high","low","close","volume")]
                if min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError("invalid prices")
            except (ValueError,TypeError):
                invalid[t].append(row.get("date"));continue
            rows[t].append(row);sources[t].add(row["data_source"])
    output=[]
    for s in setups:
        t=s["ticker"];bars=rows.get(t,[])
        dates=[r["date"] for r in bars]
        unique=dates==sorted(set(dates))
        expected=s["price_asof"]
        latest=dates[-1] if bars else None
        # Coverage is not provenance certification: adjusted pykrx != verified regular-only.
        coverage=bool(bars) and len(bars)>=120 and unique and latest>=expected and len(sources[t])==1 and not invalid[t]
        output.append({"ticker":t,"name":s["name"],"setup_id":s["setup_id"],
            "registration_key":s["record_id"],"registered_at":s["registered_at_utc"],
            "frozen_price_date":expected,"history_rows":len(bars),"last_history_date":latest,
            "history_source":sorted(sources[t]),"history_coverage": "AVAILABLE_UNCERTIFIED" if coverage else "WAIT_HISTORY",
            "reason":None if coverage else ("NO_TICKER_HISTORY" if not bars else "INCOMPLETE_OR_INVALID_HISTORY"),
            "regular_session_certified":False,"source_continuity_certified":False,
            "financial_pit_verified":False,"buy_approved":False})
    return {"schema":"C3_HISTORY_CONNECTOR_V6_RESEARCH_ONLY",
        "history_sha256":hashlib.sha256(hp.read_bytes()).hexdigest(),
        "registry_sha256":hashlib.sha256(rp.read_bytes()).hexdigest(),
        "registered_denominator":len(setups),
        "dated_history_available_uncertified":sum(x["history_coverage"]=="AVAILABLE_UNCERTIFIED" for x in output),
        "no_buy_approvals":True,"records":output}

def main():
    p=argparse.ArgumentParser();p.add_argument("--history",required=True);p.add_argument("--registry",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();result=connect(a.history,a.registry)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"registered_denominator":result["registered_denominator"],"dated_history_available_uncertified":result["dated_history_available_uncertified"],"buy_approvals":0}))
if __name__=="__main__":main()
