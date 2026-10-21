#!/usr/bin/env python3
"""Read-only Kiwoom REST daily chart adapter. No account/order endpoints.

Default is OFFLINE fixture mode. Live calls require --live AND explicit
KIWOOM_APP_KEY/KIWOOM_APP_SECRET environment secrets. Never log credentials,
bearer tokens, raw API responses, or account data.
"""
import argparse,csv,json,os,time,urllib.request,urllib.error
from datetime import date
from pathlib import Path

HOST="https://api.kiwoom.com"
CHART_PATH="/api/dostk/chart"
DAILY_ID="ka10081"

def post(path,headers,body):
    req=urllib.request.Request(HOST+path,data=json.dumps(body).encode(),
        headers=headers,method="POST")
    with urllib.request.urlopen(req,timeout=20) as response:
        payload=json.loads(response.read().decode())
        return payload,dict(response.headers.items())

def check_ok(payload):
    if not isinstance(payload,dict) or str(payload.get("return_code","0"))!="0":
        raise ValueError("KIWOOM_RESPONSE_NOT_SUCCESS")
    return payload

def normalize(payload,ticker):
    check_ok(payload)
    raw=payload.get("stk_dt_pole_chart_qry")
    if not isinstance(raw,list):raise ValueError("MISSING_DAILY_CHART_ROWS")
    result={}
    for r in raw:
        try:
            d=str(r["dt"])
            if len(d)!=8 or not d.isdigit():continue
            day=date.fromisoformat(f"{d[:4]}-{d[4:6]}-{d[6:]}")
            o,h,l,c=[abs(int(str(r[k]).replace(",",""))) for k in
                     ("open_pric","high_pric","low_pric","cur_prc")]
            v=abs(int(str(r.get("trde_qty","0")).replace(",","")))
            if not 0<l<=min(o,c)<=max(o,c)<=h:continue
            result[day.isoformat()]={"ticker":ticker,"Date":day.isoformat(),
                "Open":o,"High":h,"Low":l,"Close":c,"Volume":v}
        except (KeyError,TypeError,ValueError,OverflowError):continue
    return [result[k] for k in sorted(result)]

def fetch_daily(ticker,base_dt,max_pages=3,delay=0.3):
    key=os.environ.get("KIWOOM_APP_KEY")
    secret=os.environ.get("KIWOOM_APP_SECRET")
    if not key or not secret:raise RuntimeError("KIWOOM_CREDENTIALS_NOT_CONFIGURED")
    auth,_=post("/oauth2/token",{"Content-Type":"application/json;charset=UTF-8"},
        {"grant_type":"client_credentials","appkey":key,"secretkey":secret})
    check_ok(auth)
    token=auth.get("token")
    if not token:raise RuntimeError("KIWOOM_TOKEN_MISSING")
    merged={}
    next_key=""
    for page in range(max_pages):
        payload,headers=post(CHART_PATH,{
            "Content-Type":"application/json;charset=UTF-8",
            "authorization":"Bearer "+token,"api-id":DAILY_ID,
            "cont-yn":"Y" if next_key else "N","next-key":next_key},
            {"stk_cd":ticker,"base_dt":base_dt,"upd_stkpc_tp":"1"})
        for r in normalize(payload,ticker):merged[r["Date"]]=r
        cont=next((v for k,v in headers.items() if k.lower()=="cont-yn"),"N")
        next_key=next((v for k,v in headers.items() if k.lower()=="next-key"),"")
        if cont.upper()!="Y" or not next_key:break
        if page+1<max_pages:time.sleep(delay)
    return [merged[k] for k in sorted(merged)]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ticker",required=True,help="6-digit KRX ticker")
    p.add_argument("--base-date",default=date.today().strftime("%Y%m%d"))
    p.add_argument("--fixture",type=Path,help="Offline JSON fixture; no network")
    p.add_argument("--live",action="store_true",help="Explicitly enable read-only API")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if len(a.ticker)!=6 or not a.ticker.isdigit():raise SystemExit("INVALID_TICKER")
    if a.fixture and a.live:raise SystemExit("CHOOSE_FIXTURE_OR_LIVE")
    if a.fixture:
        rows=normalize(json.loads(a.fixture.read_text(encoding="utf-8")),a.ticker)
    elif a.live:rows=fetch_daily(a.ticker,a.base_date)
    else:raise SystemExit("DISABLED_BY_DEFAULT: supply --fixture or --live")
    if not rows:raise SystemExit("NO_VALID_DAILY_BARS")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({"ticker":a.ticker,"bars":len(rows),"first":rows[0]["Date"],
                      "last":rows[-1]["Date"],"read_only":True,"trade_approval":"NO"}))

if __name__=="__main__":main()
