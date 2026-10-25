#!/usr/bin/env python3
"""v6.18 free US/global market context for C3/K100, research-only.

Use dated U.S. ETF bars at the latest actual 16:00 America/New_York close
before the Korean evaluation cutoff. FRED CSV is free, but revised and
publication-time NOT attested: it is a corroboration, NEVER an independently
point-in-time-certified backtest or a broker signal.

Missing observations are UNKNOWN, not bullish, not zero. No auto orders.
"""
from __future__ import annotations
import argparse,csv,io,json,math,statistics,time,urllib.request
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from collections import Counter
from zoneinfo import ZoneInfo
from krx_global_leadership_v97 import (
    ETFS,ensure_history,parse_ohlc,us_asof,us_close_kst,cutoff_kst,
)
KST=ZoneInfo("Asia/Seoul")
SCHEMA="C3_K100_GLOBAL_MACRO_US_EQUITIES_V618_RESEARCH"
FRED_SERIES={
    "SP500":"US_SP500_BENCHMARK","NASDAQCOM":"US_NASDAQ_COMPOSITE",
    "VIXCLS":"US_VIX","DGS10":"US_10Y_TREASURY_PCT",
    "DGS2":"US_2Y_TREASURY_PCT","DEXKOUS":"KRW_PER_USD",
    "DTWEXBGS":"TRADE_WEIGHTED_US_DOLLAR","DCOILWTICO":"WTI_USD_BARREL",
    "BAMLH0A0HYM2":"US_HIGH_YIELD_OPTION_ADJUSTED_SPREAD_PCT",
}
US_ETF_CONTEXT=("SPY","SMH","SOXX","XLK","XLE","XLI","XLU","EWT","EWJ","FXI")
FRED_BASE="https://fred.stlouisfed.org/graph/fredgraph.csv?id="

def float_or_none(x):
    try:
        if x is None or str(x).strip() in ("",".","nan","NaN"):return None
        n=float(x)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None

def fred_parse(blob,series):
    if len(blob)>2000000:raise ValueError("FRED_RESPONSE_TOO_LARGE")
    rows=list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
    if not rows or len(rows)>30000:raise ValueError("FRED_EMPTY_OR_EXCESSIVE_RESPONSE")
    hd=set(rows[0])
    dcol="DATE" if "DATE" in hd else "observation_date" if "observation_date" in hd else None
    if dcol is None or series not in hd:raise ValueError("FRED_UNEXPECTED_COLUMN_SCHEMA")
    result=[];last=None
    for r in rows:
        d=date.fromisoformat(r[dcol])
        if last is not None and d<=last:raise ValueError("FRED_DUPLICATE_UNSORTED_DATE")
        last=d
        v=float_or_none(r[series])
        if v is not None:
            if series in ("SP500","NASDAQCOM","DGS10","DGS2","DEXKOUS","DTWEXBGS","DCOILWTICO","VIXCLS","BAMLH0A0HYM2") and v<=0:continue
            result.append((d,v))
    return result

def fred_fetch(series,cache,fetch=True,timeout=12):
    path=Path(cache)/(series+".csv")
    if fetch:
        try:
            request=urllib.request.Request(FRED_BASE+series,headers={
                "User-Agent":"C3-K100-research-v618/1.0",
                "Accept":"text/csv"})
            with urllib.request.urlopen(request,timeout=timeout) as rsp:
                if int(getattr(rsp,"status",200))!=200:raise ValueError("HTTP_STATUS_NON200")
                blob=rsp.read(2000001)
            obs=fred_parse(blob,series)
            if len(obs)<30:raise ValueError("FRED_INSUFFICIENT_SERIES")
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix(".tmp")
            temp.write_bytes(blob);temp.replace(path)
            return obs,"FETCHED_NO_HISTORICAL_VINTAGE_PROOF"
        except Exception as exc:
            # Preserve existing cache for research, but never upgrade stale
            # fallback to a green or verified signal.
            message="FETCH_ERROR_"+type(exc).__name__
    else:message="NO_NEW_FETCH"
    if path.is_file():
        try:
            obs=fred_parse(path.read_bytes(),series)
            return obs,"CACHED_UNVERIFIED_FRESHNESS_"+message
        except Exception:return [],"INVALID_CACHE_"+message
    return [],"MISSING_"+message

def latest_fred(obs,asof,max_days):
    usable=[(d,v) for d,v in obs if d<=asof]
    if not usable:return None
    d,v=usable[-1]
    if (asof-d).days>max_days:return None
    return {"date":d.isoformat(),"value":round(v,5),
        "last_available_date_not_release_timestamp":True}

def etf_context(path,day,hour="08:35"):
    h=parse_ohlc(path)
    i=us_asof(h,day,at=hour,max_stale_days=5)
    if i is None or i<20:return None
    b=h[i];c=b["close"];p=h[i-1]["close"];p5=h[i-5]["close"]
    ma=statistics.mean(x["close"] for x in h[i-19:i+1])
    return dict(us_session=b["day"].isoformat(),
       us_close_kst=us_close_kst(b["day"]).isoformat(),
       close=round(c,5),ret1_pct=round(100*(c/p-1),3),
       ret5_pct=round(100*(c/p5-1),3),
       ma20=round(ma,5),above_ma20=c>ma,
       source_adjusted_not_independent_vendor_vintage=True)

def pct(x,y):
    if x is None or y is None or y<=0:return None
    return round(100*(x/y-1),3)

def fred_change(observations,asof,max_days=5):
    latest=latest_fred(observations,asof,max_days)
    if not latest:return None
    lookback=asof-timedelta(days=7)
    previous=[(d,v) for d,v in observations if d<=lookback]
    if not previous:return None
    return dict(**latest,delta7=round(latest["value"]-previous[-1][1],4),
        pct7=pct(latest["value"],previous[-1][1]))

def classify(equities,fred):
    """Never make a positive BUY verdict. Evidence coverage independent by type.

    U.S. equity bearishness, VIX/rates/FX/oil shocks have separate explanations.
    A semiconductor-strong day does not guarantee KRX stock gains.
    """
    sp=equities.get("SPY");chip=equities.get("SMH") or equities.get("SOXX")
    groups={}
    if sp:
        groups["US_BROAD"]=("RED" if sp["ret1_pct"]<=-2.0 or
          sp["ret5_pct"]<=-4 or (not sp["above_ma20"] and sp["ret5_pct"]<-1.5)
          else "AMBER" if (sp["ret5_pct"]<0 or not sp["above_ma20"]) else "GREEN")
    if chip:
        groups["US_SEMICON"]=("RED" if chip["ret1_pct"]<=-4 or chip["ret5_pct"]<=-7
            else "AMBER" if (chip["ret5_pct"]<0 or not chip["above_ma20"]) else "GREEN")
    vx=fred.get("VIXCLS")
    if vx:groups["VIX"]=("RED" if vx["value"]>=30 else "AMBER" if vx["value"]>=22 else "GREEN")
    y10=fred.get("DGS10")
    if y10:groups["US_10Y"]=("RED" if y10.get("delta7") is not None and y10["delta7"]>=.25
       else "AMBER" if y10["value"]>=5 or (y10.get("delta7") is not None and y10["delta7"]>=.12)
       else "GREEN")
    fx=fred.get("DEXKOUS")
    if fx:groups["USDKRW"]=("RED" if fx.get("pct7") is not None and fx["pct7"]>=3
        else "AMBER" if fx.get("pct7") is not None and fx["pct7"]>=1.5 else "GREEN")
    oil=fred.get("DCOILWTICO")
    if oil:groups["WTI"]=("AMBER" if oil.get("pct7") is not None and oil["pct7"]>=8 else "NEUTRAL")
    credit=fred.get("BAMLH0A0HYM2")
    if credit:groups["US_CREDIT"]=("RED" if credit.get("delta7") is not None and credit["delta7"]>=.50
           else "AMBER" if credit.get("delta7") is not None and credit["delta7"]>=.25 else "GREEN")
    coverage=len(groups);red=sum(x=="RED" for x in groups.values())
    amber=sum(x=="AMBER" for x in groups.values())
    required=("US_BROAD" in groups and coverage>=3)
    if not required:state="GLOBAL_DATA_INCOMPLETE_RESEARCH_ONLY"
    elif groups["US_BROAD"]=="RED" or red>=2:
        state="GLOBAL_RISK_OFF_RESEARCH_ONLY"
    elif red>=1 or amber>=2:
        state="GLOBAL_CAUTION_RESEARCH_ONLY"
    elif amber==1:state="GLOBAL_MIXED_RESEARCH_ONLY"
    else:state="GLOBAL_SUPPORTIVE_RESEARCH_ONLY"
    return dict(regime=state,coverage=coverage,
      group_classifications=groups,red_factors=red,amber_factors=amber,
      positive_signal_never_authorizes_buy=True,
      confirmed_industry_stock_mapping=False)

def collect(asof,at,cache,fetch):
    cutoff=cutoff_kst(asof,at)
    # US/Eastern market closings after cutoff are never used.
    etf_info=ensure_history(cache/"etfs",asof-timedelta(days=250),
        asof,provider="yahoo" if fetch else "none")
    etfs={s:etf_context(cache/"etfs"/(s+".csv"),asof,at)
          for s in US_ETF_CONTEXT}
    etfs={s:v for s,v in etfs.items() if v}
    # Only U.S. session labels already after US 16:00 may be selected.
    for row in etfs.values():
        if datetime.fromisoformat(row["us_close_kst"])>cutoff:
            raise ValueError("FUTURE_US_SESSION_REACHES_KOREAN_CUTOFF")
    available_sessions=[v["us_session"] for v in etfs.values()]
    us_date=max((date.fromisoformat(x) for x in available_sessions),
                default=asof-timedelta(days=5))
    fredinfo={};fred_raw={};fredstatus={}
    for s in FRED_SERIES:
        obs,status=fred_fetch(s,cache/"fred",fetch)
        # FRED observation dates alone do not prove publish timestamp.
        details=fred_change(obs,us_date,max_days=5 if s not in ("DCOILWTICO",) else 8)
        fredinfo[s]=details
        fredstatus[s]=dict(status=status,
            last_date=details["date"] if details else None,
            release_timestamp_verified=False)
        fred_raw[s]=obs
    data={k:v for k,v in fredinfo.items() if v}
    gate=classify(etfs,data)
    report=dict(schema=SCHEMA,assessment_kst=cutoff.isoformat(),
      generated_at_kst=datetime.now(KST).isoformat(timespec="seconds"),
      global_etf_data=etfs,global_etf_fetch=etf_info,
      fred_macro_data=data,fred_fetch_status=fredstatus,
      stale_or_missing_factors=[s for s in FRED_SERIES if s not in data],
      us_last_session=max(available_sessions,default=None),
      **gate,krx_session_data_included=False,
      news_catalyst_claimed=False,first_party_PIT_release_timestamps_verified=False,
      all_prices_regular_only_independently_verified=False,
      trade_approved=False,orders_enabled=False,
      trade_action="CASH_UNTIL_DOMESTIC_PRICE_RISK_ACCOUNT_GATES")
    return report

def render(r):
    x=["# C3·K100 v6.18 글로벌·미국증시 모닝 리스크 브리프","",
       "**최종 신규매수 판단: CASH / 해외 자료만으로 BUY 금지**","",
       "- 한국 기준시각: "+r["assessment_kst"],
       "- 사용 가능한 미국 마감 세션: "+str(r["us_last_session"]),
       "- 해외 위험: **"+r["regime"]+"**",
       "- 데이터 요소 수: "+str(r["coverage"])+"개 (불완전 데이터는 0점 또는 호재로 간주하지 않음)","",
       "## 미국 주식 및 해외 섹터 프록시","",
       "| 미국 ETF | 마감일 | 1일 등락 | 5일 등락 | 20일선 |",
       "|---|---|---:|---:|---|"]
    for name in US_ETF_CONTEXT:
        v=r["global_etf_data"].get(name)
        if v:x.append(f"| {name} | {v['us_session']} | {v['ret1_pct']}% | {v['ret5_pct']}% | {'상회' if v['above_ma20'] else '하회'} |")
        else:x.append(f"| {name} | 확인 불가 | — | — | 검증 필요 |")
    x+=["","## 글로벌 매크로: 미국 위험과 국내 전파 경로","",
       "| 변수 (FRED) | 확인일 | 값 | 7일 변화 | 데이터 상태 |",
       "|---|---|---:|---:|---|"]
    for key in FRED_SERIES:
        f=r["fred_macro_data"].get(key)
        if f:x.append(f"| {key} | {f['date']} | {f['value']} | {f.get('delta7','—')} | 공개시각 PIT 미확인 |")
        else:x.append(f"| {key} | — | — | — | 결측/지연 |")
    x+=["","## 국내 종목 후보 평가에 미치는 영향","",
        "- SPY/QQQ 대표지수 약세: 단기 전체 시장 위험 가산, 국내 수급·일봉 구조 먼저 재검증",
        "- SMH/SOXX 반도체 약세: 국내 반도체·AI 후보의 진입 신호 추가 확인. 한국 기업별 직접 수익 연결 입증 전 기계적 제외 금지",
        "- VIX/10년 국채/신용스프레드 급등: 시장 위험 심화, CASH 우선",
        "- 달러/원 급등: 외국인 수급 변동성 유의, 환율 자체를 한국 개별종목 매도 신호로 치환 금지",
        "- WTI 급등: 수입비용 부담과 에너지업종 수혜의 방향이 다르므로 산업별 별도 검토",
        "- 달러·금리·VIX FRED 자료는 발표지연/수정 가능; 과거 백테스트 당시 공개 여부를 별도로 검증할 때까지 수익성 입증 사용 금지.",
        "- 미국 원천 ETF, 해외 기사나 해외뉴스로 국내 보통주를 자동매수하지 않음.",
        "","**필수 최종 확인:** 국내 정규장-only 15:30 데이터, 종목별 80점 검증, 1차 진입/일봉 손절 후 비용 2R, 매수가능 현금, 기존 보유/물타기 금지.",
        "**Required Next Data:** 정규장 출처, 별도 미국 매크로 최초 발표 시각, KRX 국내 섹터 수급 및 키움 계좌."]
    return "\n".join(x)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--cutoff",choices=("08:35","16:00"),default="08:35")
    p.add_argument("--cache",type=Path,default=Path("output/global_macro_cache"))
    p.add_argument("--outdir",type=Path,default=Path("output"))
    p.add_argument("--provider",choices=("yahoo_and_fred","none"),default="none")
    q=p.parse_args();day=date.fromisoformat(q.date)
    r=collect(day,q.cutoff,q.cache,q.provider=="yahoo_and_fred")
    q.outdir.mkdir(parents=True,exist_ok=True)
    (q.outdir/"v618_global_macro_status.json").write_text(
        json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (q.outdir/"v618_global_macro_mobile.md").write_text(render(r),encoding="utf-8")
    print("V618_GLOBAL_MACRO",json.dumps({k:r[k] for k in ("assessment_kst","us_last_session","regime","coverage","trade_approved","orders_enabled")},ensure_ascii=False))
if __name__=="__main__":main()
