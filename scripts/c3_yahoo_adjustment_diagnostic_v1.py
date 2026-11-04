"""Research-only comparison of pykrx close with Yahoo Close and Adj Close."""
import argparse,csv,json,math
from pathlib import Path

def read(path):
    with open(path,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    result={}
    for row in rows:
        key=(row["ticker"],row["date"])
        if key in result: raise ValueError("DUPLICATE_TICKER_DATE")
        result[key]=row
    return result

def compare(primary,yahoo):
    a,b=read(primary),read(yahoo)
    output=[]
    for key in sorted(set(a)|set(b)):
        if key not in a or key not in b:
            output.append(dict(ticker=key[0],date=key[1],status="MISSING_SIDE"))
            continue
        p=float(a[key]["close"])
        raw=float(b[key]["close"])
        adj=float(b[key]["adj_close"]) if b[key].get("adj_close") else None
        if not math.isfinite(p) or not math.isfinite(raw) or (adj is not None and not math.isfinite(adj)):
            raise ValueError("NONFINITE_PRICE")
        output.append(dict(ticker=key[0],date=key[1],pykrx_close=p,
                           yahoo_close=raw,yahoo_adj_close=adj,
                           raw_equal=p==raw,adj_equal=(p==adj if adj is not None else None),
                           raw_gap_pct=round((raw/p-1)*100,6),
                           adj_gap_pct=round((adj/p-1)*100,6) if adj is not None else None,
                           status="OBSERVED_NOT_CERTIFIED"))
    return {"schema":"C3_YAHOO_ADJUSTMENT_DIAGNOSTIC_V1",
            "adjustment_basis_verified":False,"upstream_independence_verified":False,
            "regular_only_certified":False,"trade_approved":False,"orders_enabled":False,
            "rows":output}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--primary",required=True);p.add_argument("--yahoo",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    report=compare(a.primary,a.yahoo)
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"schema":report["schema"],"rows":len(report["rows"]),
                      "raw_equal":sum(r.get("raw_equal") is True for r in report["rows"]),
                      "adjusted_equal":sum(r.get("adj_equal") is True for r in report["rows"]),
                      "trade_approved":False},ensure_ascii=False))
if __name__=="__main__": main()
