#!/usr/bin/env python3
"""Offline-first daily bar merge and ten-session research ranking.

Ranking requires same 11 observed exchange sessions for every candidate.
No future data beyond asof; incomplete/stale series are excluded. This is
not a complete KRX universe unless the input universe has been audited.
"""
import argparse,csv,json
from collections import defaultdict
from datetime import date
from pathlib import Path

FIELDS=["ticker","Date","Open","High","Low","Close","Volume"]

def valid(row):
    try:
        ticker=str(row["ticker"]).strip()
        day=date.fromisoformat(str(row["Date"]))
        o,h,l,c=[float(row[k]) for k in ("Open","High","Low","Close")]
        vol=float(row.get("Volume",0))
        return len(ticker)==6 and ticker.isdigit() and 0<l<=min(o,c)<=max(o,c)<=h and vol>=0 and day
    except (KeyError,ValueError,TypeError,OverflowError):
        return False

def merge(existing,incoming,asof):
    records={}
    for r in list(existing)+list(incoming):
        if valid(r) and r["Date"]<=asof:
            records[(r["ticker"],r["Date"])]=dict((k,r.get(k,"")) for k in FIELDS)
    return [records[k] for k in sorted(records)]

def rank(rows,asof,window=10,min_universe=1):
    by_ticker=defaultdict(dict)
    for r in rows:
        if valid(r) and r["Date"]<=asof:
            by_ticker[r["ticker"]][r["Date"]]=r
    # An explicit common market calendar prevents using stale 10-bar windows.
    counts=defaultdict(int)
    for ticker,series in by_ticker.items():
        for day in series:counts[day]+=1
    if not counts:return [],{"reason":"NO_DATA","trade_approval":"NO"}
    calendar=sorted(counts)
    if len(calendar)<window+1:return [],{"reason":"INSUFFICIENT_SESSIONS","trade_approval":"NO"}
    dates=calendar[-(window+1):]
    output=[]
    for ticker,series in by_ticker.items():
        if not all(d in series for d in dates):continue
        prior=float(series[dates[0]]["Close"])
        last=float(series[dates[-1]]["Close"])
        if prior<=0:continue
        output.append({"ticker":ticker,"start_date":dates[0],"end_date":dates[-1],
                       "return_10d_pct":round(100*(last/prior-1),4),
                       "last_close":last,"trade_approval":"NO"})
    output.sort(key=lambda x:(-x["return_10d_pct"],x["ticker"]))
    for i,r in enumerate(output,1):r["rank"]=i
    info={"asof":asof,"start_date":dates[0],"end_date":dates[-1],
          "input_tickers":len(by_ticker),"eligible_tickers":len(output),
          "excluded_incomplete":len(by_ticker)-len(output),
          "universe_verified_full_krx":False,
          "research_only":True,"trade_approval":"NO"}
    if len(output)<min_universe:info["reason"]="INSUFFICIENT_UNIVERSE"
    return output,info

def read(path):
    if not path.exists():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def write(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--existing",type=Path,required=True)
    p.add_argument("--incoming",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--merged",type=Path,required=True)
    p.add_argument("--ranking",type=Path,required=True)
    p.add_argument("--summary",type=Path,required=True)
    a=p.parse_args()
    date.fromisoformat(a.asof)
    if not a.incoming.exists():raise SystemExit("MISSING_INCOMING")
    rows=merge(read(a.existing),read(a.incoming),a.asof)
    write(a.merged,rows,FIELDS)
    ranked,info=rank(rows,a.asof)
    write(a.ranking,ranked,["rank","ticker","start_date","end_date",
                           "return_10d_pct","last_close","trade_approval"])
    a.summary.parent.mkdir(parents=True,exist_ok=True)
    a.summary.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(info,ensure_ascii=False))

if __name__=="__main__":main()
