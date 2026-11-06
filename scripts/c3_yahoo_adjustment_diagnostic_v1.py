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
            "rows":output,"gap_summary":gap_summary({"rows":output}),"ratio_pattern":ratio_pattern({"rows":output})}
def ratio_pattern(report):
    grouped={}
    for row in report["rows"]:
        if row["status"]!="OBSERVED_NOT_CERTIFIED": continue
        grouped.setdefault(row["ticker"],[]).append(row["raw_gap_pct"])
    output={}
    for ticker,values in sorted(grouped.items()):
        nonzero=[v for v in values if v!=0]
        if len(nonzero)<3:
            label="INSUFFICIENT_NONZERO_OBSERVATIONS"
            spread=None
        else:
            spread=round(max(nonzero)-min(nonzero),6)
            # Heuristic only; a constant gap cannot establish its cause.
            label="NEAR_CONSTANT_GAP_HEURISTIC" if spread<=0.05 else "VARIABLE_GAP"
        output[ticker]={"nonzero_days":len(nonzero),"nonzero_gap_spread_pct_points":spread,
                        "pattern":label,"cause_verified":False}
    return output

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
    lines.append("### 종목별 종가 차이 요약")
    for ticker, stats in gap_summary(report).items():
        lines.append("- {}: 양(+) {}일, 음(-) {}일, 일치 {}일, 평균 절대차 {:.4f}%, 최대 절대차 {:.4f}%".format(
            ticker,stats["positive_gap_days"],stats["negative_gap_days"],stats["zero_gap_days"],
            stats["mean_abs_gap_pct"],stats["max_abs_gap_pct"]))
    lines.append("")
    lines.append("### 가격 차이 반복 패턴 (추정)")
    for ticker,pattern in ratio_pattern(report).items():
        spread=pattern["nonzero_gap_spread_pct_points"]
        lines.append("- {}: {}, 불일치 {}일, 차이율 범위 {}%p".format(
            ticker,pattern["pattern"],pattern["nonzero_days"],spread if spread is not None else "자료 부족"))
    lines.append("")
    lines.append("> 가격 공급원·수정주가 기준·정규장 범위 검증 전. CASH / 신규 매수 판단 보류.")
    return "\n".join(lines)+"\n"

def gap_summary(report):
    groups={}
    for row in report["rows"]:
        if row["status"]!="OBSERVED_NOT_CERTIFIED": continue
        group=groups.setdefault(row["ticker"],[])
        group.append(row["raw_gap_pct"])
    return {ticker:{"observations":len(values),
                    "zero_gap_days":sum(v==0 for v in values),
                    "positive_gap_days":sum(v>0 for v in values),
                    "negative_gap_days":sum(v<0 for v in values),
                    "max_abs_gap_pct":round(max(abs(v) for v in values),6),
                    "mean_abs_gap_pct":round(sum(abs(v) for v in values)/len(values),6)}
            for ticker,values in sorted(groups.items())}

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
                      "gap_summary":report["gap_summary"],"ratio_pattern":report["ratio_pattern"],
                      "trade_approved":False},ensure_ascii=False))
if __name__=="__main__": main()
