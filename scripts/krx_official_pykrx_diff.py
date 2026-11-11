#!/usr/bin/env python3
"""Read-only, date-locked KRX official vs PyKRX daily comparison.
A matching daily bar is NOT certification of regular-session 15:30 scope.
"""
import argparse,csv,json
from pathlib import Path

FIELDS=("close","volume","turnover_krw")
def compare(official,pykrx_rows,day):
    out=[];seen=set()
    for r in official:
        assert r["asof"]==day
        ticker=r["ticker"];assert ticker not in seen;seen.add(ticker)
        p=pykrx_rows.get(ticker)
        row={"asof":day,"market":r["market"],"ticker":ticker,
             "official_close":r["close"],"pykrx_close":"" if p is None else p.get("close",""),
             "official_volume":r["volume"],"pykrx_volume":"" if p is None else p.get("volume",""),
             "official_turnover_krw":r["turnover_krw"],"pykrx_turnover_krw":"" if p is None else p.get("turnover_krw",""),
             "status":"PYKRX_UNAVAILABLE" if p is None else "MATCH"}
        if p is not None:
            for k in FIELDS:
                try:
                    a=float(r[k]);b=float(p[k])
                    if abs(a-b)>max(0.000001,abs(a)*1e-9):
                        row["status"]="DIFF"
                except (ValueError,TypeError,KeyError):
                    row["status"]="INCOMPLETE"
        out.append(row)
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--official",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    manifest=json.loads((a.official/"krx_v65_collect_status.json").read_text())
    assert manifest["asof"]==a.date and manifest["official_dataset_usable"]
    official=[]
    for market in ("KOSPI","KOSDAQ"):
        with (a.official/(market+"_official.csv")).open(encoding="utf-8-sig",newline="") as f:
            official.extend(csv.DictReader(f))
    py={};errors={}
    try:
        from pykrx import stock
        for market in ("KOSPI","KOSDAQ"):
            try:
                frame=stock.get_market_ohlcv_by_ticker(a.date.replace("-",""),market=market)
                if frame is None or frame.empty:raise ValueError("EMPTY_RESPONSE")
                for ticker,r in frame.iterrows():
                    py[str(ticker).zfill(6)]={"close":r.get("종가"),
                        "volume":r.get("거래량"),"turnover_krw":r.get("거래대금")}
            except Exception as exc:
                errors[market]=type(exc).__name__
    except Exception as exc:
        errors["library"]=type(exc).__name__
    rows=compare(official,py,a.date)
    a.out.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0])
    with (a.out/"official_pykrx_daily_diff.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    counts={key:sum(r["status"]==key for r in rows) for key in ("MATCH","DIFF","INCOMPLETE","PYKRX_UNAVAILABLE")}
    summary={"asof":a.date,"official_rows":len(official),"pykrx_rows":len(py),
             "counts":counts,"pykrx_errors":errors,
             "regular_1530_certified":False,"trade_approved":False,
             "orders_enabled":False,"decision":"CASH",
             "status":"DAILY_SOURCE_DIFF_ONLY_NOT_REGULAR_CERTIFICATION"}
    (a.out/"official_pykrx_daily_diff_status.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("OFFICIAL_PYKRX_DAILY_DIFF",json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
