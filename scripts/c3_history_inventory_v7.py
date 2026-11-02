"""Read-only C3 OHLCV inventory and freshness audit. Never approves trades.
Usage: python scripts/c3_history_inventory_v7.py --registry reports/c3_registered_reclaim_registry_v1.json --current reports/candidate_daily_history_v52.csv --legacy-dir reports/v36_ohlcv_cache --out reports/c3_history_inventory_v7.json
"""
import argparse,csv,json,hashlib
from collections import defaultdict
from datetime import date
from pathlib import Path

def audit(registry,current,legacy_dir):
    regpath=Path(registry);currentpath=Path(current);directory=Path(legacy_dir)
    reg=json.loads(regpath.read_text(encoding="utf-8-sig"))
    setups=reg["setups"]
    if len(setups)!=reg["registered_count"] or len({s["setup_id"] for s in setups})!=len(setups):
        raise ValueError("registry invalid")
    current_bars=defaultdict(list)
    with currentpath.open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            current_bars[row["ticker"].zfill(6)].append(row)
    records=[]
    for s in setups:
        ticker=s["ticker"];f=directory/(ticker+".csv")
        sources=[]
        if ticker in current_bars:
            bars=current_bars[ticker]
            sources.append(_describe(bars,"CURRENT_V52",currentpath,["date","open","high","low","close","volume"],s["price_asof"]))
        if f.is_file():
            with f.open(encoding="utf-8-sig",newline="") as stream:
                bars=list(csv.DictReader(stream))
            sources.append(_describe(bars,"LEGACY_V36",f,["Date","Open","High","Low","Close","Volume"],s["price_asof"]))
        usable=[x for x in sources if x["shape_valid"] and x["last_date"]>=s["price_asof"] and x["rows"]>=120]
        records.append({"ticker":ticker,"name":s["name"],"setup_id":s["setup_id"],"registered_at_utc":s["registered_at_utc"],"price_asof":s["price_asof"],
            "sources":sources,"dated_120_bar_coverage":bool(usable),
            "state":"WAIT_SOURCE_CERTIFICATION" if usable else "WAIT_CURRENT_HISTORY",
            "buy_approved":False})
    return {"schema":"C3_HISTORY_INVENTORY_V7","registry_sha256":_sha(regpath),"current_sha256":_sha(currentpath),
        "registered_count":len(records),"has_any_file":sum(bool(r["sources"]) for r in records),
        "dated_120_bar_coverage":sum(r["dated_120_bar_coverage"] for r in records),
        "source_regular_certified":False,"buy_approvals":0,"records":records}

def _sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def _describe(bars,label,path,columns,asof):
    dates=[];valid=True
    for row in bars:
        try:
            d=date.fromisoformat(row[columns[0]]);o,h,l,c,v=[float(row[k]) for k in columns[1:]]
            if min(o,h,l,c)<=0 or v<0 or l>min(o,c) or max(o,c)>h:valid=False
            dates.append(d.isoformat())
        except (ValueError,TypeError,KeyError):valid=False
    valid=valid and bool(dates) and dates==sorted(set(dates)) and len(dates)==len(bars)
    return {"family":label,"path":str(path),"sha256":_sha(path) if label=="LEGACY_V36" else None,
            "rows":len(bars),"first_date":dates[0] if dates else None,"last_date":dates[-1] if dates else None,
            "shape_valid":valid,"covers_registration_date":bool(valid and dates[-1]>=asof),
            "regular_session_certified":False}

def main():
    p=argparse.ArgumentParser()
    for name in ("registry","current","legacy-dir","out"):p.add_argument("--"+name,required=True)
    a=p.parse_args();r=audit(a.registry,a.current,a.legacy_dir)
    Path(a.out).write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:r[k] for k in ("registered_count","has_any_file","dated_120_bar_coverage","buy_approvals")}))
if __name__=="__main__":main()
