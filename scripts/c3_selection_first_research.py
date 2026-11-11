#!/usr/bin/env python3
"""C3 selection-first exploratory ranking. No orders, ledger writes, or BUY approval.
Input bars must be dated OHLCV; financial evidence must be dated as-of same day.
Only selection-day information can influence ranks, entries, stops and targets.
"""
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path
from c3_three_entry_replay import signals

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

def eligible(fin,day):
    if fin.get("schema")!="opendart_annual_research_v1" or fin.get("asof")!=day:
        return {}
    result={}
    for x in fin.get("researched",[]):
        ticker=str(x.get("ticker",""))
        if not (len(ticker)==6 and ticker.isdigit() and
            x.get("status")=="DATED_ANNUAL_RESEARCH_ONLY" and
            x.get("financial_screen_pass") is True and
            x.get("annual_plus_interim_growth_pass") is True and
            x.get("recent_financial_weakening_veto") is False and
            x.get("sector_id") not in ("BANK","INSURANCE","SECURITIES") and
            str(x.get("receipt_date") or "")<=day and
            bool(x.get("receipt_date")) and
            str(x.get("latest_periodic_receipt_date") or "")<=day and
            bool(x.get("latest_periodic_receipt_date"))):
            continue
        result[ticker]=x
    return result

def candidate(bars,i,fin,benchmark=None):
    if i<60:return None
    h=bars[:i+1];cl=[b["close"] for b in h];now=cl[-1]
    ma5=sum(cl[-5:])/5;ma20=sum(cl[-20:])/20;ma60=sum(cl[-60:])/60
    if not (now>ma20>ma60 and ma5>ma20):return None
    if len(h)<21 or cl[-21]<=0:return None
    momentum=now/cl[-21]-1
    if momentum<=0:return None
    benchmark_momentum=None
    if benchmark and len(benchmark)>=21 and benchmark[-21]>0:
        benchmark_momentum=benchmark[-1]/benchmark[-21]-1
    volumes=[b["volume"] for b in h]
    if sum(volumes[-21:-1])<=0:return None
    rvol=volumes[-1]/(sum(volumes[-21:-1])/20)
    if rvol<=0:return None
    relative=momentum-benchmark_momentum if benchmark_momentum is not None else None
    # No claimed investor flow from OHLCV. Flow remains unverified, not zero.
    flow="NOT_AVAILABLE_FROM_OHLCV"
    stop=min(b["low"] for b in h[-10:])
    if stop>=now:return None
    resistance=max(b["high"] for b in h[-20:-1])
    entries=[]
    for name,price,model_stop,target in signals(bars,i):
        if model_stop<=0 or price<=model_stop:continue
        entries.append((name,price,model_stop,target))
    if not entries:return None
    # Entry 1/2 are independently grounded in MA20 / ATR candidate limits.
    entries.sort(key=lambda x:x[1],reverse=True)
    first=entries[0];second=entries[1] if len(entries)>1 else None
    if first[1]>=now*1.02:return None
    risk=(first[1]-first[2])/first[1]
    if not 0<risk<=.12:return None
    t1=max(resistance,first[1]+2*(first[1]-first[2]))
    t2=first[1]+3*(first[1]-first[2])
    if t2<=t1:t2=t1+(first[1]-first[2])
    # Transparent research proxy, not a certified 85-point stock score.
    proxy=round(min(momentum,.3)*100+min(rvol,3)*5+(min(relative,.3)*50 if relative is not None else 0),4)
    return {"ticker":bars[i]["ticker"],"signal_date":bars[i]["date"],
        "research_proxy":proxy,"momentum_20d_pct":round(momentum*100,3),
        "benchmark_relative_20d_pct":round(relative*100,3) if relative is not None else None,
        "rvol_20d":round(rvol,3),"investor_flow":flow,
        "entry1_range":[round(first[1]*.995,4),round(first[1],4)],
        "entry2_range":[round(second[1]*.995,4),round(second[1],4)] if second else None,
        "stop":round(first[2],4),"target1":round(t1,4),"target2":round(t2,4),
        "entry_model1":first[0],"entry_model2":second[0] if second else None,
        "price_action":"PASS_UNTIL_ENTRY_RANGE_AND_STRUCTURE_CONFIRMED",
        "buy_approval":"NO"}

def selection_outcome(bars,i):
    base=bars[i]["close"];out={}
    for n in (5,10,20):
        if i+n>=len(bars):
            out[str(n)]={"status":"CENSORED"};continue
        future=bars[i+1:i+n+1]
        out[str(n)]={"status":"OBSERVED_EXPLORATORY",
            "close_return_pct":round((bars[i+n]["close"]/base-1)*100,4),
            "mfe_pct":round((max(b["high"] for b in future)/base-1)*100,4),
            "mae_pct":round((min(b["low"] for b in future)/base-1)*100,4)}
    return out

def research(rows,finance,asof,benchmark=None):
    by=defaultdict(list)
    for r in rows:
        b={"ticker":str(r["ticker"]),"date":str(r["date"])}
        for k in ("open","high","low","close","volume"):
            b[k]=float(r[k])
        if not (0<b["low"]<=min(b["open"],b["close"])<=max(b["open"],b["close"])<=b["high"] and b["volume"]>=0):
            raise ValueError("INVALID_BAR")
        by[b["ticker"]].append(b)
    fin=eligible(finance,asof)
    all_candidates=[]
    for ticker,bars in by.items():
        bars.sort(key=lambda b:b["date"])
        if len({b["date"] for b in bars})!=len(bars):raise ValueError("DUPLICATE_DATE")
        index=next((i for i,b in enumerate(bars) if b["date"]==asof),None)
        if index is None or ticker not in fin:continue
        c=candidate(bars,index,fin[ticker],benchmark)
        if c:
            c["selection_outcomes"]=selection_outcome(bars,index)
            all_candidates.append(c)
    all_candidates.sort(key=lambda x:(-x["research_proxy"],x["ticker"]))
    top=all_candidates[:2]
    return {"status":"SELECTION_FIRST_EXPLORATORY","asof":asof,
        "financial_eligible_count":len(fin),"technically_eligible_count":len(all_candidates),
        "top2_research":top,"selection_outcomes_not_trade_returns":True,
        "entry_hit_or_trade_pnl_not_counted_as_selection_success":True,
        "benchmark_relative_verified":benchmark is not None,
        "investor_flow_verified":False,"certified_score_available":False,
        "performance_publication_allowed":False,"trade_approved":False,
        "decision":"CASH"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--bars",type=Path,required=True)
    p.add_argument("--financial",type=Path,required=True);p.add_argument("--asof",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.bars.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    result=research(rows,json.loads(a.financial.read_text()),a.asof)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("C3_SELECTION_FIRST",json.dumps({"financial_eligible_count":result["financial_eligible_count"],"technically_eligible_count":result["technically_eligible_count"],"top2_count":len(result["top2_research"]),"decision":"CASH"}))
if __name__=="__main__":main()
