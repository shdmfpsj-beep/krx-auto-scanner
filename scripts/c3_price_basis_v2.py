"""Compare requested-end vintages and adjusted/unadjusted adapters without inventing action labels."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

FIELDS=("open","high","low","close","volume")
CHILD=r'''
import json,sys,inspect,hashlib
from pathlib import Path
from pykrx import stock
code,start,end,adjusted,path=sys.argv[1:]
df=stock.get_market_ohlcv_by_date(start.replace('-',''),end.replace('-',''),code,adjusted=adjusted=='true')
if df is None or df.empty:raise SystemExit(3)
rows=[]
for idx,r in df.iterrows():
    rows.append(dict(date=idx.strftime('%Y-%m-%d'),**{k:float(r[v]) for k,v in [('open','시가'),('high','고가'),('low','저가'),('close','종가'),('volume','거래량')]}))
meta=dict(ticker=code,start=start,end=end,adjusted=adjusted=='true',rows=rows,source_function_sha256=hashlib.sha256(inspect.getsource(stock.get_market_ohlcv_by_date).encode()).hexdigest())
Path(path).write_text(json.dumps(meta,allow_nan=False))
'''


def classify_prices(a,b,tolerance=.00001):
    if any(a.get(k) is None or b.get(k) is None or a[k]<=0 or b[k]<=0 for k in FIELDS[:4]):
        return "INVALID_PRICE_PAIR"
    changed=[k for k in FIELDS if a.get(k)!=b.get(k)]
    if not changed:return "MATCH"
    if changed==["close"]:return "CLOSE_ONLY_PROVIDER_OR_SESSION_DIFFERENCE_UNRESOLVED"
    if changed==["volume"]:return "VOLUME_SCOPE_OR_PROVIDER_DIFFERENCE_UNRESOLVED"
    ratios=[a[k]/b[k] for k in FIELDS[:4]]
    if max(ratios)-min(ratios)<=tolerance and abs(ratios[0]-1)>tolerance:
        return "UNIFORM_OHLC_SCALE_CANDIDATE_NOT_CONFIRMED_ACTION"
    return "MULTIFIELD_PRICE_BASIS_DISAGREEMENT_UNRESOLVED"


def prefix_comparison(short,long,cutoff):
    left={r["date"]:r for r in short if r["date"]<=cutoff}
    right={r["date"]:r for r in long if r["date"]<=cutoff}
    missing=sorted(set(left)^set(right));changes=[]
    for day in sorted(set(left)&set(right)):
        fields=[k for k in FIELDS if left[day][k]!=right[day][k]]
        if fields:changes.append(dict(date=day,fields=fields))
    return dict(compared_days=len(set(left)&set(right)),missing_prefix_dates=missing,
                changed_prefix_days=changes,
                same_retrieval_time_different_requested_end_only=True,
                point_in_time_historical_vintage_certified=False)


def fetch_query(code,start,end,adjusted,path,timeout=30):
    try:
        result=subprocess.run([sys.executable,"-c",CHILD,code,start,end,"true" if adjusted else "false",str(path)],
                              capture_output=True,timeout=timeout)
        if result.returncode!=0:
            return dict(status="EMPTY_RESPONSE" if result.returncode==3 else "PROVIDER_REQUEST_FAILED")
    except subprocess.TimeoutExpired:
        return dict(status="PROVIDER_REQUEST_TIMEOUT")
    # Do not persist arbitrary stderr, HTTP headers or exception text.
    return dict(status="OK",sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def collect(tickers,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    queries=[];data={}
    for code in sorted(set(tickers)):
        for mode,end,adjusted in (("adjusted_short","2026-03-31",True),
                                  ("adjusted_long","2026-11-04",True)):
            path=root/(code+"_"+mode+".json")
            result=fetch_query(code,"2025-05-02",end,adjusted,path)
            query=dict(ticker=code,mode=mode,requested_end=end,**result)
            queries.append(query)
            if result["status"]=="OK":data[(code,mode)]=json.loads(path.read_text())["rows"]
            time.sleep(1)
    for code in ("007810","012330","271560"):
        path=root/(code+"_unadjusted.json")
        result=fetch_query(code,"2025-05-02","2026-11-04",False,path,timeout=20)
        queries.append(dict(ticker=code,mode="unadjusted",requested_end="2026-11-04",**result))
        if result["status"]=="OK":data[(code,"unadjusted")]=json.loads(path.read_text())["rows"]
        time.sleep(1)
    prefixes={};pairs={}
    for code in sorted(set(tickers)):
        if (code,"adjusted_short") in data and (code,"adjusted_long") in data:
            prefixes[code]=prefix_comparison(data[(code,"adjusted_short")],data[(code,"adjusted_long")],"2026-03-31")
        if (code,"unadjusted") in data and (code,"adjusted_long") in data:
            raw={r["date"]:r for r in data[(code,"unadjusted")]}
            adjusted={r["date"]:r for r in data[(code,"adjusted_long")]}
            pairs[code]=dict(Counter(classify_prices(adjusted[d],raw[d]) for d in set(raw)&set(adjusted)))
    report=dict(schema="C3_PRICE_BASIS_V2",queries=queries,prefix_comparisons=prefixes,
                adjusted_vs_unadjusted=pairs,regular_only_certified=False,
                corporate_action_causes_verified=False,execution_price_basis_certified=False,
                same_time_prefix_equality_is_not_historical_pit_proof=True,
                adjusted_signal_prices_must_not_be_used_as_historical_executable_quotes=True,
                orders_enabled=False,decision="CASH")
    (root/"price_basis_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(dict(queries=len(queries),successful=sum(q["status"]=="OK" for q in queries),failed=sum(q["status"]!="OK" for q in queries))))
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument("--cases",required=True);p.add_argument("--outdir",required=True)
    a=p.parse_args();cases=json.loads(Path(a.cases).read_text());tickers=cases["tickers"]+["026960","271560"]
    collect(tickers,a.outdir)


if __name__=="__main__":main()
