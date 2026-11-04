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
def markdown_table(report):
    lines=["### 날짜별 종가 차이 (실험용·거래 인증 아님)",
           "| 종목 | 날짜 | pykrx | Yahoo 종가 | Yahoo 수정종가 | 일반 차이율 | 수정 차이율 |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for r in report["rows"]:
        if r["status"]=="MISSING_SIDE":
            lines.append("| {} | {} | 자료 누락 | - | - | - | - |".format(r["ticker"],r["date"]))
            continue
        adj="-" if r["yahoo_adj_close"] is None else str(r["yahoo_adj_close"])
        adj_gap="-" if r["adj_gap_pct"] is None else "{:+.4f}%".format(r["adj_gap_pct"])
        lines.append("| {} | {} | {} | {} | {} | {:+.4f}% | {} |".format(
            r["ticker"],r["date"],r["pykrx_close"],r["yahoo_close"],adj,r["raw_gap_pct"],adj_gap))
    lines.append("")
    lines.append("> 가격 공급원·수정주가 기준·정규장 범위 검증 전. CASH / 신규 매수 판단 보류.")
    return "\\n".join(lines)+"\\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--primary",required=True);p.add_argument("--yahoo",required=True);p.add_argument("--output",required=True);p.add_argument("--markdown")
    a=p.parse_args()
    report=compare(a.primary,a.yahoo)
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if a.markdown: Path(a.markdown).write_text(markdown_table(report),encoding="utf-8")
    print(json.dumps({"schema":report["schema"],"rows":len(report["rows"]),
                      "raw_equal":sum(r.get("raw_equal") is True for r in report["rows"]),
                      "adjusted_equal":sum(r.get("adj_equal") is True for r in report["rows"]),
                      "trade_approved":False},ensure_ascii=False))
if __name__=="__main__": main()
