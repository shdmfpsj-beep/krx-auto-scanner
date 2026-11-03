"""Fetch selected C3 TOP2 adjusted OHLCV for v23 research only."""
import argparse,csv,hashlib,json
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

def collect(selection_path,outdir,lookback=450):
    from pykrx import stock
    obj=json.loads(Path(selection_path).read_text(encoding="utf-8-sig"))
    target=Path(outdir);target.mkdir(parents=True,exist_ok=True)
    results=[]
    for item in obj.get("provisional_watch_top2",[]):
        ticker=str(item.get("ticker","")).zfill(6)
        asof=str(item.get("price_date",""))
        result={"ticker":ticker,"price_date":asof,"status":"WAIT_FETCH",
                "regular_session_certified":False,"buy_approved":False}
        try:
            day=date.fromisoformat(asof)
            if day>datetime.now(timezone(timedelta(hours=9))).date():
                raise ValueError("FUTURE_DATE")
            start=(day-timedelta(days=lookback)).strftime("%Y%m%d")
            frame=stock.get_market_ohlcv_by_date(start,day.strftime("%Y%m%d"),ticker,adjusted=True)
            if frame is None or frame.empty:raise ValueError("EMPTY_RESPONSE")
            bars=[];seen=set()
            for idx,row in frame.iterrows():
                d=idx.date().isoformat() if hasattr(idx,"date") else str(idx)[:10]
                if d in seen or d>asof:raise ValueError("DUPLICATE_OR_FUTURE")
                seen.add(d)
                o,h,l,c,v=[int(row[k]) for k in ("시가","고가","저가","종가","거래량")]
                if min(o,h,l,c)<=0 or v<0 or l>min(o,c) or h<max(o,c):
                    raise ValueError("BAD_OHLCV")
                bars.append((d,o,h,l,c,v))
            if bars!=sorted(bars) or len(bars)<35 or bars[-1][0]!=asof:
                raise ValueError("SHORT_STALE_OR_UNSORTED")
            path=target/(ticker+".csv")
            temp=target/(ticker+".csv.tmp")
            with temp.open("w",encoding="utf-8",newline="") as f:
                w=csv.writer(f);w.writerow(("date","open","high","low","close","volume"));w.writerows(bars)
            temp.replace(path)
            result.update(status="AVAILABLE_UNCERTIFIED",bars=len(bars),
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          source="PYKRX_ADJUSTED_BY_DATE")
        except Exception as exc:
            result.update(status="WAIT_FETCH_OR_VALIDATION",error=str(exc)[:120])
        results.append(result)
    report={"schema":"C3_TOP2_HISTORY_V24","records":results,
            "available_uncertified":sum(r["status"]=="AVAILABLE_UNCERTIFIED" for r in results),
            "buy_approvals":0,"decision":"CASH"}
    (target/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selection",required=True);p.add_argument("--outdir",required=True)
    a=p.parse_args();print(json.dumps(collect(a.selection,a.outdir),ensure_ascii=False))
