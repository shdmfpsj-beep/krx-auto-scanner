"""Manual research-only frozen-cohort OHLCV collection; no trade approval.
Run: python scripts/c3_frozen_history_collect_v8.py --registry reports/c3_registered_reclaim_registry_v1.json --outdir reports/c3_frozen_history_v8 --asof 2026-11-02
Fetch each ticker independently, preserving source family, and fail closed.
"""
import argparse,csv,hashlib,json,time
from datetime import date,datetime,timezone,timedelta
from pathlib import Path

def collect(registry,outdir,asof,days=450):
    from pykrx import stock
    end=date.fromisoformat(asof)
    if end>datetime.now(timezone(timedelta(hours=9))).date():
        raise ValueError("future asof prohibited")
    start=end-timedelta(days=days)
    regpath=Path(registry);reg=json.loads(regpath.read_text(encoding="utf-8-sig"))
    setups=reg["setups"]
    if len(setups)!=reg["registered_count"] or len({x["setup_id"] for x in setups})!=len(setups):
        raise ValueError("registry integrity")
    target=Path(outdir);target.mkdir(parents=True,exist_ok=True)
    results=[]
    for s in setups:
        t=s["ticker"];record={"ticker":t,"setup_id":s["setup_id"],"registered_at_utc":s["registered_at_utc"],
            "frozen_price_asof":s["price_asof"],"source_family":"PYKRX_ADJUSTED_BY_DATE_V8",
            "regular_session_certified":False,"source_continuity_certified":False,
            "buy_approved":False,"status":"WAIT_FETCH","bars":0}
        try:
            frame=stock.get_market_ohlcv_by_date(start.strftime("%Y%m%d"),end.strftime("%Y%m%d"),t,adjusted=True)
            if frame is None or frame.empty:raise ValueError("EMPTY_RESPONSE")
            output=[];seen=set()
            for idx,row in frame.iterrows():
                d=idx.date().isoformat() if hasattr(idx,"date") else str(idx)[:10]
                if d in seen or d>end.isoformat():raise ValueError("DUPLICATE_OR_FUTURE_DATE")
                seen.add(d)
                o,h,l,c,v=[int(row[k]) for k in ("시가","고가","저가","종가","거래량")]
                if min(o,h,l,c)<=0 or v<0 or l>min(o,c) or max(o,c)>h:raise ValueError("INVALID_OHLCV")
                output.append((d,o,h,l,c,v))
            if output!=sorted(output,key=lambda x:x[0]):raise ValueError("UNSORTED_DATES")
            if len(output)<120 or output[-1][0]<s["price_asof"]:
                raise ValueError("INSUFFICIENT_OR_STALE_BARS")
            path=target/(t+".csv")
            # Write only after validation, atomically replace individual research cache.
            temp=target/(t+".csv.tmp")
            with temp.open("w",newline="",encoding="utf-8") as stream:
                writer=csv.writer(stream);writer.writerow(["date","open","high","low","close","volume"]);writer.writerows(output)
            temp.replace(path)
            record.update(status="AVAILABLE_UNCERTIFIED",bars=len(output),
                first_date=output[0][0],last_date=output[-1][0],
                file=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        except Exception as exc:
            record["status"]="WAIT_FETCH_OR_VALIDATION"
            record["error"]=str(exc)[:160]
        results.append(record)
        time.sleep(0.2)
    report={"schema":"C3_FROZEN_HISTORY_V8_RESEARCH_ONLY","asof":asof,
        "registry_sha256":hashlib.sha256(regpath.read_bytes()).hexdigest(),
        "registered_denominator":len(results),"available_uncertified":sum(r["status"]=="AVAILABLE_UNCERTIFIED" for r in results),
        "regular_session_certified":False,"buy_approvals":0,"records":results}
    dest=target/"manifest.json";dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",required=True);p.add_argument("--outdir",required=True);p.add_argument("--asof",required=True)
    a=p.parse_args();r=collect(a.registry,a.outdir,a.asof)
    print(json.dumps({"registered":r["registered_denominator"],"available_uncertified":r["available_uncertified"],"approved":0}))
    if r["available_uncertified"] == 0:
        raise SystemExit("COLLECTION_FAILED: zero valid dated ticker files; inspect manifest.json errors")
if __name__=="__main__":main()
