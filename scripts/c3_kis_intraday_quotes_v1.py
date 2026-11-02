"""KIS KRX-only quote adapter for C3 research. Read-only, fail closed.
Never label a quote verified without actual KIS response and dated minute.
"""
import argparse,json,os,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from kis_regular_minute_cli import get_access_token,fetch_page
KST=ZoneInfo("Asia/Seoul")
def parse_latest(rows,ticker,now):
    local=now.astimezone(KST)
    today=local.strftime("%Y%m%d")
    valid=[]
    for r in rows:
        if not isinstance(r,dict) or str(r.get("stck_bsop_date"))!=today:continue
        hhmmss=str(r.get("stck_cntg_hour",""))
        if not re.fullmatch(r"\d{6}",hhmmss) or not "090000"<=hhmmss<"153000":continue
        try:
            price=int(str(r["stck_prpr"]).replace(",",""))
            stamp=datetime.strptime(today+hhmmss,"%Y%m%d%H%M%S").replace(tzinfo=KST)
        except (ValueError,KeyError,TypeError):continue
        age=(local-stamp).total_seconds()
        if price>0 and 0<=age<=900:valid.append((stamp,price))
    if not valid:return None
    stamp,price=max(valid,key=lambda x:x[0])
    return {"ticker":ticker,"price":price,"observed_at":stamp.isoformat(),"source":"verified_provider"}
def collect(tickers,now,key,secret):
    local=now.astimezone(KST)
    if local.weekday()>=5 or not ((9<=local.hour<15) or (local.hour==15 and local.minute<30)):
        return {"status":"OUTSIDE_REGULAR_SESSION","quotes":[]}
    if not key or not secret:return {"status":"PENDING_PROVIDER_CREDENTIALS","quotes":[]}
    try:token=get_access_token(key,secret)
    except Exception:return {"status":"PROVIDER_AUTH_FAILURE","quotes":[]}
    quotes=[];errors=[]
    for ticker in tickers:
        try:
            rows=fetch_page(token,key,secret,ticker,local.strftime("%Y%m%d"),local.strftime("%H%M%S"))
            q=parse_latest(rows,ticker,now)
            if q:quotes.append(q)
            else:errors.append({"ticker":ticker,"reason":"NO_FRESH_KRX_MINUTE"})
        except Exception:errors.append({"ticker":ticker,"reason":"PROVIDER_QUOTE_FAILURE"})
    return {"status":"QUOTES_VERIFIED" if len(quotes)==len(tickers) else "PARTIAL_OR_UNAVAILABLE",
            "quotes":quotes,"errors":errors}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--tickers",default="271560,026960")
    p.add_argument("--out",default="output/c3_intraday_quotes.json")
    a=p.parse_args()
    tickers=a.tickers.split(",")
    if not tickers or len(tickers)>5 or any(not re.fullmatch(r"\d{6}",x) for x in tickers):p.error("1-5 six-digit tickers")
    now=datetime.now(KST)
    key=os.getenv("KIS_APP_KEY","");secret=os.getenv("KIS_APP_SECRET","")
    if not key or not secret:
        result={"status":"PENDING_PROVIDER_CREDENTIALS","quotes":[]}
    else:
        result=collect(tickers,now,key,secret)
    result["checked_at"]=now.isoformat()
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"status":result["status"],"verified_quote_count":len(result["quotes"]),"errors":result.get("errors",[])},ensure_ascii=False))
if __name__=="__main__":main()
