#!/usr/bin/env python3
"""Reconstruct observed KRX regular OHLCV from dated, timestamped KIS 1m rows.

Official KIS [domestic-stock-213] inquire-time-dailychartprice:
  market J: KRX (not NX:NXT nor UN: consolidated)
  response output2: stck_bsop_date, stck_cntg_hour, stck_oprc,
    stck_hgpr, stck_lwpr, stck_prpr, cntg_vol, acml_tr_pbmn.
Never use time-after-15:30 records, including 15:40+ off-hours/aftermarket.
Time-scoped price evidence is not investor flow, broad-market coverage,
65 completed historic bars, or authority for BUY.
"""
import re
from datetime import datetime

TIME_START="090000"
TIME_END="153000"
FIELDS=("stck_oprc","stck_hgpr","stck_lwpr","stck_prpr","cntg_vol")

def positive_int(value):
    try:
        if isinstance(value,bool):return None
        x=int(str(value).replace(",",""))
        return x if x>0 else None
    except (ValueError,TypeError):return None

def nonnegative_int(value):
    try:
        if isinstance(value,bool):return None
        x=int(str(value).replace(",",""))
        return x if x>=0 else None
    except (ValueError,TypeError):return None

def minute_id(raw):
    m=str(raw or "")
    if not re.fullmatch(r"\d{6}",m):return None
    if not (m[2:4]<"60" and m[4:6]<"60" and m[:2]<"24"):return None
    return m

def summarize_minute_rows(rows,date,ticker,source_market="J",min_minutes=300):
    errors=[]
    if not re.fullmatch(r"\d{8}",str(date)):errors.append("INVALID_DATE")
    if not re.fullmatch(r"\d{6}",str(ticker)):errors.append("INVALID_TICKER")
    if source_market!="J":errors.append("NON_KRX_MARKET_SOURCE")
    by_time={}
    outside=0
    wrong_date=0
    corrupt=0
    conflict=0
    if not isinstance(rows,list):rows=[]
    for raw in rows:
        if not isinstance(raw,dict):
            corrupt+=1
            continue
        row_day=str(raw.get("stck_bsop_date",""))
        if row_day!=date:
            wrong_date+=1
            continue
        tm=minute_id(raw.get("stck_cntg_hour"))
        if tm is None:
            corrupt+=1
            continue
        if not TIME_START<=tm<=TIME_END:
            outside+=1
            continue
        op,hi,lo,cl=(positive_int(raw.get(x)) for x in FIELDS[:4])
        vol=nonnegative_int(raw.get("cntg_vol"))
        if (None in (op,hi,lo,cl,vol) or
                not (lo<=op<=hi and lo<=cl<=hi)):
            corrupt+=1
            continue
        canonical=(op,hi,lo,cl,vol)
        if tm in by_time and by_time[tm]!=canonical:
            conflict+=1
        else:
            by_time[tm]=canonical
    if wrong_date:errors.append("SOURCE_ROW_DATE_MISMATCH")
    if corrupt:errors.append("CORRUPT_MINUTE_ROW")
    if conflict:errors.append("CONFLICTING_DUPLICATE_MINUTE")
    times=sorted(by_time)
    if len(times)<min_minutes:errors.append("INSUFFICIENT_MINUTE_COVERAGE")
    if not times or times[0]>"090200":errors.append("REGULAR_OPEN_NOT_OBSERVED")
    if not times or times[-1]<"153000":errors.append("CLOSING_AUCTION_NOT_OBSERVED")
    if not times:errors.append("NO_REGULAR_MINUTE_PRICE")
    prices=None
    if times and not errors:
        op=by_time[times[0]][0]
        hi=max(v[1] for v in by_time.values())
        lo=min(v[2] for v in by_time.values())
        cl=by_time[times[-1]][3]
        vol=sum(v[4] for v in by_time.values())
        if not(0<lo<=op<=hi and lo<=cl<=hi and vol>=0):
            errors.append("AGGREGATE_OHLC_CONFLICT")
        else:
            prices={"Open":op,"High":hi,"Low":lo,"Close":cl,"Volume":vol}
    return {"schema":"kis_krx_regular_minutes_v1","asof":date,
            "ticker":ticker,"market_code":source_market,
            "session":"KRX_REGULAR_0900_1530",
            "minutes_seen":len(times),"first_minute":times[0] if times else None,
            "last_minute":times[-1] if times else None,
            "outside_regular_rows_excluded":outside,
            "wrong_date_rows":wrong_date,
            "invalid_minute_rows":corrupt,
            "duplicate_time_conflicts":conflict,
            "regular_ohlcv":prices,
            "regular_ohlcv_reconstruction_verified":bool(prices and not errors),
            "investor_net_flow_regular_verified":False,
            "historical_65_days_verified":False,
            "sector_universe_verified":False,
            "trade_approved":False,"decision":"CASH",
            "blockers":errors+["INVESTOR_FLOW_REGULAR_NOT_VERIFIED",
                                 "FULL_SECTOR_UNIVERSE_NOT_VERIFIED",
                                 "HISTORICAL_65_REGULAR_BARS_NOT_VERIFIED"]}

def query_end_from_earliest(rows):
    times=[minute_id(x.get("stck_cntg_hour")) for x in rows if isinstance(x,dict)]
    times=[x for x in times if x]
    if not times:return None
    v=min(times)
    hh,mm,ss=int(v[:2]),int(v[2:4]),int(v[4:6])
    minute=hh*60+mm-1
    if minute<9*60:return None
    return f"{minute//60:02d}{minute%60:02d}{ss:02d}"

def auth_is_available(environ):
    return bool(environ.get("KIS_APP_KEY") and environ.get("KIS_APP_SECRET"))
