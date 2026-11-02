"""Daily C3 research-only TOP2 and source-quality audit.
Never generates an order, BUY approval, stop, or certified forward return.
"""
import argparse,csv,json,datetime
from pathlib import Path

def as_number(row,key):
    try:return float(row[key])
    except (KeyError,TypeError,ValueError):return None

def run(source,dest):
    with open(source,encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f);rows=list(reader)
    today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    evaluated=[];excluded={}
    for r in rows:
        ticker=str(r.get("ticker","")).zfill(6)
        close=as_number(r,"close");ma20=as_number(r,"ma20");ma60=as_number(r,"ma60")
        rvol=as_number(r,"rvol20");turnover=as_number(r,"turnover_krw")
        try:dated=datetime.date.fromisoformat(str(r.get("latest_date","")))
        except ValueError:dated=None
        reasons=[]
        if not ticker.isdigit() or len(ticker)!=6:reasons.append("INVALID_TICKER")
        if not dated or (today-dated).days>5 or dated>today:reasons.append("STALE_DATE")
        if any(v is None or v<=0 for v in (close,ma20,ma60,rvol,turnover)):reasons.append("INVALID_NUMERIC")
        if r.get("instrument_type","").upper() in ("ETF","ETN","SPAC","REIT"):reasons.append("NON_COMMON_EQUITY")
        if r.get("turnover_source")!="EXCHANGE_VERIFIED":reasons.append("TURNOVER_UNVERIFIED")
        if r.get("data_source")!="REGULAR_SESSION_CERTIFIED":reasons.append("REGULAR_SESSION_UNCERTIFIED")
        if reasons:
            for reason in reasons:excluded[reason]=excluded.get(reason,0)+1
            continue
        trend=close>ma20>ma60
        score=round(min(rvol,5)*8+(20 if trend else 0)+(15 if r.get("breakout")=="True" else 0)+(10 if r.get("first_pullback_proxy")=="True" else 0),2)
        evaluated.append({"ticker":ticker,"name":r.get("name",""),"close":close,"latest_date":str(dated),"score_research":score,
                          "rvol20":rvol,"trend_confirmed":trend,"buy_approved":False})
    evaluated.sort(key=lambda x:(-x["score_research"],x["ticker"]))
    result={"schema":"C3_DAILY_EVIDENCE_GATE_V14","generated_kst":datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
      "input_rows":len(rows),"evidence_pass":len(evaluated),"exclusion_counts":excluded,
      "research_top2":evaluated[:2],"buy_approvals":0,"decision":"CASH_RESEARCH_ONLY",
      "notes":"Candidate data cannot certify source/session or sector exclusions without independent evidence. Never place orders."}
    path=Path(dest);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"input":len(rows),"evidence_pass":len(evaluated),"decision":result["decision"]}))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",default="reports/candidates.csv")
    p.add_argument("--out",default="reports/c3_daily_evidence_gate_v14.json")
    a=p.parse_args();run(a.source,a.out)
