#!/usr/bin/env python3
"""Optional, public quote-only KIS API probe for a small audit watchlist.

No brokerage account, order API, user cash or positions are accessed.
KIS_APP_KEY and KIS_APP_SECRET are optional GitHub Secrets. If absent, this
produces a useful pending-source report without any calls or false claims.
The supported minute endpoint is GET:
 /uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice
TR: FHKST03010230. Market J:KRX ONLY. Never NX/UN.
"""
import argparse
import json
import os
import re
import time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo
from kis_regular_minute import (
    summarize_minute_rows,query_end_from_earliest,auth_is_available)

API_BASE="https://openapi.koreainvestment.com:9443"
QUOTE_PATH="/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
TOKEN_PATH="/oauth2/tokenP"
TR_ID="FHKST03010230"

def _read_json(req,seconds=12):
    with urlopen(req,timeout=seconds) as resp:
        if resp.status!=200:
            raise ValueError("PROVIDER_NON_200")
        body=resp.read(2_000_000)
    return json.loads(body)

def get_access_token(key,secret):
    data=json.dumps({"grant_type":"client_credentials",
                     "appkey":key,"appsecret":secret}).encode("utf-8")
    req=Request(API_BASE+TOKEN_PATH,data=data,
                headers={"content-type":"application/json"},method="POST")
    result=_read_json(req)
    token=result.get("access_token")
    if not isinstance(token,str) or len(token)<20:
        raise ValueError("KIS_TOKEN_MISSING")
    return token

def fetch_page(token,key,secret,ticker,day,endpoint_time):
    if not(re.fullmatch(r"\d{6}",ticker)
           and re.fullmatch(r"\d{8}",day)
           and re.fullmatch(r"\d{6}",endpoint_time)):
        raise ValueError("INVALID_MARKET_QUERY_ARGUMENTS")
    params={
        "FID_COND_MRKT_DIV_CODE":"J",
        "FID_INPUT_ISCD":ticker,
        "FID_INPUT_HOUR_1":endpoint_time,
        "FID_INPUT_DATE_1":day,
        "FID_PW_DATA_INCU_YN":"N",
        "FID_FAKE_TICK_INCU_YN":""}
    req=Request(API_BASE+QUOTE_PATH+"?"+urlencode(params),
        headers={"authorization":"Bearer "+token,
                 "appkey":key,"appsecret":secret,"tr_id":TR_ID,
                 "content-type":"application/json; charset=utf-8"},
        method="GET")
    response=_read_json(req)
    if str(response.get("rt_cd",""))!="0":
        raise ValueError("KIS_QUOTE_RESULT_UNVERIFIED")
    output=response.get("output2")
    if not isinstance(output,list):
        raise ValueError("KIS_MINUTE_SCHEMA_UNVERIFIED")
    return output

def collect_ticker(day,ticker,token,key,secret,max_pages=6):
    rows=[]
    endpoint="153000"
    seen_query=set()
    issues=[]
    for i in range(max_pages):
        if endpoint in seen_query:
            issues.append("PAGINATION_TIME_LOOP")
            break
        seen_query.add(endpoint)
        page=fetch_page(token,key,secret,ticker,day,endpoint)
        if not page:break
        rows.extend(page)
        following=query_end_from_earliest(page)
        if not following or following<"090000":
            break
        if following>=endpoint:
            issues.append("PAGINATION_NOT_PROGRESSING")
            break
        endpoint=following
        # Keep test/probe traffic low. Not intended for an entire exchange.
        time.sleep(0.5)
    else:
        issues.append("PAGE_LIMIT_REACHED")
    result=summarize_minute_rows(rows,day,ticker)
    result["page_count"]=len(seen_query)
    result["extra_validation_issues"]=issues
    if issues:
        result["regular_ohlcv_reconstruction_verified"]=False
        result["blockers"]=list(dict.fromkeys(result["blockers"]+issues))
    return result

def nominal_krx_regular_asof(now):
    local=now.astimezone(ZoneInfo("Asia/Seoul"))
    d=local.date()
    if d.weekday()>=5 or (local.hour,local.minute)<(15,31):
        d-=timedelta(days=1)
    while d.weekday()>=5:d-=timedelta(days=1)
    return d.strftime("%Y%m%d")

def build_missing(day,tickers):
    return dict(schema="kis_krx_minute_audit_v1",date=day,
        source="KIS_OFFICIAL_MINUTES_J_KRX",
        authentication="NOT_CONFIGURED",read_only=True,
        data_status="PENDING_PROVIDER_CONNECTION",
        regular_reconstructions=[],
        audited_tickers=tickers,
        ready_count=0,investor_flows_verified=False,
        investor_flow_policy="OPTIONAL_CONFIRMATION_NOT_BUY_GATE",
        sector_universe_verified=False,trade_approved=False,
        decision="CASH",blockers=["KIS_READONLY_CREDENTIALS_NOT_CONNECTED",
                   "REGULAR_MARKET_PRICE_COVERAGE_UNAVAILABLE"])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default="")
    p.add_argument("--tickers",default="005930,000660,035420")
    p.add_argument("--out",default="output/kis_regular_minute_audit.json")
    a=p.parse_args()
    date=a.date or nominal_krx_regular_asof(datetime.now(ZoneInfo("Asia/Seoul")))
    tickers=list(dict.fromkeys([x.strip() for x in a.tickers.split(",")]))
    if not tickers or len(tickers)>5 or any(not re.fullmatch(r"\d{6}",s) for s in tickers):
        p.error("A small watchlist of 1-5 six-digit tickers is required")
    if not re.fullmatch(r"\d{8}",date):p.error("Invalid --date YYYYMMDD")
    key=os.environ.get("KIS_APP_KEY","")
    secret=os.environ.get("KIS_APP_SECRET","")
    output=build_missing(date,tickers)
    if auth_is_available(os.environ):
        output["authentication"]="CONFIGURED"
        result=[]
        try:
            token=get_access_token(key,secret)
            for ticker in tickers:
                try:
                    result.append(collect_ticker(date,ticker,token,key,secret))
                except Exception:
                    result.append(dict(ticker=ticker,asof=date,
                        regular_ohlcv_reconstruction_verified=False,
                        trade_approved=False,
                        blockers=["OFFICIAL_KIS_QUOTE_UNAVAILABLE"]))
            output["regular_reconstructions"]=result
            output["ready_count"]=sum(x.get("regular_ohlcv_reconstruction_verified") is True for x in result)
            output["data_status"]=(
                "PARTIAL_REGULAR_MINUTE_PRICE_OBSERVED"
                if output["ready_count"] else "PENDING_MARKET_DATA_VALIDATION")
            output["blockers"]=["FULL_MARKET_SECTOR_UNIVERSE_NOT_VERIFIED",
                "HISTORICAL_65_REGULAR_BARS_NOT_VERIFIED"]
        except Exception:
            output["data_status"]="PENDING_PROVIDER_CONNECTION"
            output["blockers"]=["KIS_OAUTH_OR_PUBLIC_QUOTE_FAILURE"]
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in output.items() if k!="regular_reconstructions"},
                     ensure_ascii=False))
if __name__=="__main__":main()
