"""C3 independent Kiwoom-only research selector; no orders or Telegram."""
import argparse,csv,json
from pathlib import Path
from datetime import date
from kiwoom_daily_readonly import fetch_daily

def assess(rows,financial):
    bars=sorted(rows,key=lambda r:r["Date"])
    if len(bars)<80 or len({r["Date"] for r in bars})!=len(bars):return None
    for r in bars:
        o,h,l,c,v=(float(r[k]) for k in ("Open","High","Low","Close","Volume"))
        if not (0<l<=min(o,c)<=max(o,c)<=h and v>0):return None
    c=[float(r["Close"]) for r in bars];v=[float(r["Volume"]) for r in bars]
    avg=lambda a:sum(a)/len(a)
    ma20,ma60=avg(c[-20:]),avg(c[-60:]);prior20=avg(c[-40:-20])
    p=c[-1];rvol=v[-1]/max(avg(v[-21:-1]),1)
    low10=min(float(r["Low"]) for r in bars[-10:])
    high20=max(float(r["High"]) for r in bars[-21:-1])
    atr=avg([max(float(bars[i]["High"])-float(bars[i]["Low"]),abs(float(bars[i]["High"])-c[i-1]),abs(float(bars[i]["Low"])-c[i-1])) for i in range(len(bars)-14,len(bars))])
    stop=min(low10,ma20-1.2*atr);risk=p-stop;target=max(high20,p+2*risk)
    rr=(target-p)/risk if risk>0 else 0
    entry_low=max(ma20*.985,low10);entry_high=min(p,ma20*1.02)
    trend=p>ma60 and ma20>ma60 and ma20>prior20
    opportunity=trend and -.025<=p/ma20-1<=.055 and rvol>=.65 and entry_low<=entry_high and rr>=2
    f=financial or {}
    quality=f.get("verified") is True and f.get("operating_profit_positive") is True and f.get("debt_ratio",999)<=150 and f.get("revenue_growth_yoy",-999)>=0
    score=round(30*min(max((p/ma60-1)/.20,0),1)+25*min(max((ma20/prior20-1)/.10,0),1)+20*min(rvol/2,1)+25*min(max(rr/3,0),1),1)
    return dict(asof=bars[-1]["Date"],close=p,ma20=round(ma20,2),ma60=round(ma60,2),rvol=round(rvol,2),entry_low=round(entry_low,2),entry_high=round(entry_high,2),stop=round(stop,2),target=round(target,2),rr=round(rr,2),score=score,financial_verified=quality,technical_ready=opportunity,eligible=opportunity and quality)

def main():
    p=argparse.ArgumentParser();p.add_argument("--tickers",required=True);p.add_argument("--asof",required=True);p.add_argument("--financial");p.add_argument("--out",required=True);a=p.parse_args()
    expected=date.fromisoformat(f"{a.asof[:4]}-{a.asof[4:6]}-{a.asof[6:]}").isoformat()
    financial=json.loads(Path(a.financial).read_text()) if a.financial else {}
    tickers=list(dict.fromkeys(r["ticker"].zfill(6) for r in csv.DictReader(open(a.tickers,encoding="utf-8-sig"))))
    found=[];failures=[]
    for t in tickers:
        try:
            x=assess(fetch_daily(t,a.asof,max_pages=4),financial.get(t))
            if x is None or x["asof"]!=expected:raise ValueError("INSUFFICIENT_OR_STALE_BARS")
            x["ticker"]=t;found.append(x)
        except Exception as exc:failures.append(dict(ticker=t,error_type=type(exc).__name__))
    top=sorted((r for r in found if r["eligible"]),key=lambda r:r["score"],reverse=True)[:2]
    report=dict(schema="C3_KIWOOM_FRESH_V1",provider="KIWOOM_KA10081_ADJUSTED_DAILY",requested=len(tickers),analyzed=len(found),failures=failures,ranked=found,top2_research_only=top,regular_only_certified=False,stage_gate="HOLD_REGULAR_SESSION_UNCERTIFIED",cash=True,orders_enabled=False,telegram_requests=0)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(dict(requested=len(tickers),analyzed=len(found),top2=len(top),stage_gate=report["stage_gate"])))
if __name__=="__main__":main()
