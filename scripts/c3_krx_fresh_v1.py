"""Independent KRX Open API daily scanner. No Kiwoom, legacy panel or orders."""
import argparse,csv,json,math,os,time
from datetime import date,timedelta
from pathlib import Path
from krx_official_eod_v65 import fetch_official,normalize_payload,MARKETS

def scan(bars):
    if len(bars)<80:return None
    bars=sorted(bars,key=lambda x:x["asof"])
    if len({x["asof"] for x in bars})!=len(bars):return None
    c=[float(x["close"]) for x in bars];v=[float(x["volume"]) for x in bars]
    if any(not math.isfinite(x) or x<=0 for x in c) or any(not math.isfinite(x) or x<0 for x in v):return None
    avg=lambda a:sum(a)/len(a)
    p=c[-1];ma20=avg(c[-20:]);ma60=avg(c[-60:]);prev20=avg(c[-40:-20])
    atr=avg([max(float(bars[i]["high"])-float(bars[i]["low"]),abs(float(bars[i]["high"])-c[i-1]),abs(float(bars[i]["low"])-c[i-1])) for i in range(len(bars)-14,len(bars))])
    low10=min(float(x["low"]) for x in bars[-10:]);resistance=max(float(x["high"]) for x in bars[-21:-1])
    stop=min(low10,ma20-1.2*atr);risk=p-stop
    if risk<=0:return None
    target=max(resistance,p+2*risk);rr=(target-p)/risk
    rvol=v[-1]/max(avg(v[-21:-1]),1)
    entry_low=max(low10,ma20*.985);entry_high=min(p,ma20*1.02)
    ready=p>ma60 and ma20>ma60 and ma20>prev20 and -.025<=p/ma20-1<=.055 and rvol>=.65 and entry_low<=entry_high and rr>=2
    score=round(30*min(max((p/ma60-1)/.2,0),1)+25*min(max((ma20/prev20-1)/.1,0),1)+20*min(rvol/2,1)+25*min(rr/3,1),1)
    return dict(ticker=bars[-1]["ticker"],name=bars[-1]["name"],asof=bars[-1]["asof"],close=p,entry_low=round(entry_low,2),entry_high=round(entry_high,2),stop=round(stop,2),target=round(target,2),rr=round(rr,2),rvol=round(rvol,2),score=score,technical_ready=ready)

def collect(start,end,root,key,pause=.1):
    root.mkdir(parents=True,exist_ok=True)
    result={}
    day=start
    while day<=end:
        iso=day.isoformat();rows=[]
        for market,endpoint in MARKETS.items():
            try:
                payload,digest=fetch_official(endpoint,iso,key)
                normalized,_=normalize_payload(payload,iso,market)
                rows.extend(x for x in normalized if x["valid_daily_bar"])
                result[iso+":"+market]=dict(status="OK",rows=len(normalized),raw_sha256=digest)
            except Exception as exc:
                result[iso+":"+market]=dict(status="FAILED",error_type=type(exc).__name__,reason=str(exc) if isinstance(exc,ValueError) else "SOURCE_ERROR")
            time.sleep(pause)
        if len([x for x in rows if x["market"]=="KOSPI"])>0 and len([x for x in rows if x["market"]=="KOSDAQ"])>0:
            (root/(iso+".json")).write_text(json.dumps(rows,ensure_ascii=False))
        day+=timedelta(days=1)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--start",required=True);p.add_argument("--end",required=True);p.add_argument("--out",required=True);p.add_argument("--financial");p.add_argument("--max-days",type=int,default=100);a=p.parse_args()
    start,end=date.fromisoformat(a.start),date.fromisoformat(a.end)
    if not 1<= (end-start).days+1 <=a.max_days:raise SystemExit("INVALID_DATE_RANGE")
    key=os.environ.get("KRX_AUTH_KEY")
    if not key:raise SystemExit("KRX_AUTH_KEY_NOT_CONNECTED")
    out=Path(a.out);receipts=collect(start,end,out/"raw",key)
    by={}
    for path in sorted((out/"raw").glob("*.json")):
        for row in json.loads(path.read_text()):by.setdefault(row["ticker"],[]).append(row)
    financial=json.loads(Path(a.financial).read_text()) if a.financial else {}
    candidates=[]
    for ticker,bars in by.items():
        candidate=scan(bars)
        if candidate:
            f=financial.get(ticker,{})
            candidate["financial_verified"]=f.get("verified") is True and f.get("operating_profit_positive") is True and f.get("debt_ratio",999)<=150 and f.get("revenue_growth_yoy",-999)>=0
            candidate["eligible"]=candidate["technical_ready"] and candidate["financial_verified"]
            candidates.append(candidate)
    latest=end.isoformat()
    top=sorted((x for x in candidates if x["eligible"] and x["asof"]==latest),key=lambda x:x["score"],reverse=True)[:2]
    latest_market_rows=sum(1 for rows in by.values() if rows and rows[-1]["asof"]==latest)
    complete_days=sum(1 for p in (out/"raw").glob("*.json"))
    source_ready=latest_market_rows>=2000 and complete_days>=80
    report=dict(source_ready=source_ready,complete_days=complete_days,latest_market_rows=latest_market_rows,schema="C3_KRX_FRESH_V1",source="KRX_OPEN_API_ONLY",days_requested=(end-start).days+1,source_receipts=receipts,universe=len(by),analyzed=len(candidates),top2_research_only=top,candidates=candidates,stage_gate="HOLD_REGULAR_ONLY_UNCERTIFIED",cash=True,orders_enabled=False,telegram_requests=0)
    out.mkdir(parents=True,exist_ok=True);(out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(dict(universe=len(by),analyzed=len(candidates),top2=len(top),source_ready=source_ready,complete_days=complete_days,latest_market_rows=latest_market_rows,stage_gate=report["stage_gate"])))
    if not source_ready:raise SystemExit("KRX_SOURCE_NOT_CERTIFIED: latest market or 80 dated sessions unavailable")
if __name__=="__main__":main()
