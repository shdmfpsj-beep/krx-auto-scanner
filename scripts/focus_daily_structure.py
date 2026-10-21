#!/usr/bin/env python3
"""Independent, free completed-daily-bar verification for user focus/watch names.

Structural stop *reference* is computed independently of a BUY setup. Rejected
setups still show independently sourced historical support when available.
No intraday claims, corporate action validation, final 85-score or order API.
"""
import argparse,csv,json,math
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FOCUS={
 "005930":"삼성전자","000660":"SK하이닉스","010120":"LS ELECTRIC",
 "267260":"HD현대일렉트릭","373220":"LG에너지솔루션",
 "004490":"세방전지","042700":"한미반도체","005380":"현대차"}
OUTPUT_FIELDS=("ticker","name","data_source","latest_complete_date",
    "close","bar_count","atr14","pivot_date","pivot_low","historical_stop_reference",
    "stop_distance_pct","entry1_research_range","entry2_support_research_range",
    "no_chase_reference","prior_60d_high","prior_high_rr",
    "structure_state","trade_state","data_problems","next_action")

def numeric(v):
    try:
        x=float(v)
        return x if math.isfinite(x) and x>0 else None
    except (TypeError,ValueError):
        return None

def normalize(ticker,records):
    bars=[]
    for r in records:
        try:d=date.fromisoformat(str(r["date"])[:10])
        except (ValueError,TypeError,KeyError):return [],"INVALID_DATE"
        nums=[numeric(r.get(k)) for k in ("open","high","low","close")]
        if any(x is None for x in nums):return [],"MISSING_OHLC"
        op,hi,lo,cl=nums
        if not lo<=min(op,cl)<=max(op,cl)<=hi:return [],"INVALID_OHLC"
        v=r.get("volume",None)
        if v is not None:
            try:
                if float(v)<0:return [],"INVALID_VOLUME"
            except (TypeError,ValueError):return [],"INVALID_VOLUME"
        bars.append({"date":d,"open":op,"high":hi,"low":lo,"close":cl,
                     "volume":v,"ticker":ticker})
    ds=[b["date"] for b in bars]
    if len(set(ds))!=len(ds) or any(a>=b for a,b in zip(ds,ds[1:])):
        return [],"DUPLICATE_OR_UNSORTED_DATE"
    if len(bars)<65:return [],"LESS_THAN_65_DAILY_BARS"
    return bars,None

def fetch_history(ticker,through):
    start=(through-timedelta(days=210)).isoformat()
    end=(through+timedelta(days=1)).isoformat()
    errors=[]
    try:
        import FinanceDataReader as fdr
        raw=fdr.DataReader(ticker,start,end)
        if not raw.empty:
            bars=[]
            for d,r in raw.iterrows():
                if hasattr(d,"date"):d=d.date()
                bars.append(dict(date=str(d),open=r.get("Open"),
                  high=r.get("High"),low=r.get("Low"),
                  close=r.get("Close"),volume=r.get("Volume")))
            valid,why=normalize(ticker,bars)
            if not why:return valid,"FinanceDataReader",[]
            errors.append("FDR_"+why)
        else:errors.append("FDR_EMPTY")
    except Exception as e:
        errors.append("FDR_"+type(e).__name__)
    try:
        from pykrx import stock
        raw=stock.get_market_ohlcv_by_date(
            start.replace("-",""),through.strftime("%Y%m%d"),ticker,adjusted=True)
        if not raw.empty:
            bars=[dict(date=str(d.date() if hasattr(d,"date") else d),
                  open=r.get("시가"),high=r.get("고가"),low=r.get("저가"),
                  close=r.get("종가"),volume=r.get("거래량"))
                  for d,r in raw.iterrows()]
            valid,why=normalize(ticker,bars)
            if not why:return valid,"pykrx",[]
            errors.append("PYKRX_"+why)
        else:errors.append("PYKRX_EMPTY")
    except Exception as e:
        errors.append("PYKRX_"+type(e).__name__)
    return [],"NONE",errors

def atr(bars):
    sample=bars[-14:]
    ranges=[]
    for i in range(len(bars)-14,len(bars)):
        r,p=bars[i],bars[i-1]
        ranges.append(max(r["high"]-r["low"],abs(r["high"]-p["close"]),
                          abs(r["low"]-p["close"])))
    return sum(ranges)/len(ranges) if ranges else None

def pivot(bars):
    # Fully confirmed two daily bars to the right, checked at historical as-of.
    last=len(bars)-1
    out=[]
    for i in range(max(2,last-40),last-1):
        v=bars[i]["low"]
        if not(v<min(bars[k]["low"] for k in (i-2,i-1)) and
               v<=min(bars[k]["low"] for k in (i+1,i+2))):
            continue
        if all(bars[j]["close"]>=v for j in range(i+1,last+1)):
            out.append((i,v))
    return max(out,key=lambda x:(x[1],x[0])) if out else None

def krw_ref(v):
    # Integer KRW research reference; actual exchange tick alignment still required.
    return int(round(v))

def calculate(ticker,name,bars,source,errors,through):
    out={key:"" for key in OUTPUT_FIELDS}
    out.update(ticker=ticker,name=name,data_source=source,
               bar_count=len(bars),structure_state="DATA_MISSING",
               trade_state="CASH_NO_BUY_APPROVAL",data_problems="|".join(errors),
               next_action="무료 일봉 재수집 및 데이터 공급원 확인")
    if not bars:return out
    latest=bars[-1]["date"]
    out["latest_complete_date"]=str(latest)
    out["close"]=krw_ref(bars[-1]["close"])
    if latest>through or (through-latest).days>6:
        out.update(structure_state="STALE_DAILY_CLOSE",next_action="최신 확정 일봉 재수집")
        return out
    clean,error=normalize(ticker,bars)
    if error:
        out.update(structure_state="INVALID_DAILY_SERIES",data_problems=error,
                   next_action="시가·고가·저가·종가 또는 이력 개수 확인")
        return out
    avg=atr(clean)
    close=clean[-1]["close"]
    out["atr14"]=round(avg,2)
    p=pivot(clean)
    if p is None:
        # A confirmed pivot may not exist; raw historical low is NOT a stop.
        out.update(structure_state="NO_HELD_CONFIRMED_PIVOT",
                   next_action="일봉 눌림·구조저점 형성 확인, 강제 손절가 산정 금지")
        return out
    index,level=p
    stop=level-max(.25*avg,.003*close)
    out["pivot_date"]=str(clean[index]["date"])
    out["pivot_low"]=krw_ref(level)
    if stop<=0 or stop>=close:
        out.update(structure_state="PIVOT_RISK_INVALID",
                   next_action="구조저점 및 분할·권리락 영향 검토")
        return out
    risk=(close-stop)/close
    out.update(historical_stop_reference=krw_ref(stop),
               stop_distance_pct=round(risk*100,2),
               structure_state="HISTORICAL_PIVOT_SUPPORT_RESEARCH_ONLY")
    # Even a disqualified buy retains the computed support/stop research level.
    if not .02<=risk<=.12:
        out.update(structure_state="STOP_DISTANCE_UNSUITABLE",
                   next_action="일봉 저점은 계산됐으나 손절거리 과소·과대. 진입가격 재탐색")
        return out
    ma20=sum(b["close"] for b in clean[-20:])/20
    if stop<ma20<close and ma20>sum(b["close"] for b in clean[-25:-5])/20:
        width=.18*avg
        lo=max(stop+1,ma20-width);hi=min(close,ma20+width)
        if lo<=hi:
            out["entry2_support_research_range"]=f"{krw_ref(lo):,}~{krw_ref(hi):,}"
    e1_lo=close-.22*avg
    e1_hi=close+.12*avg
    out["entry1_research_range"]=f"{krw_ref(e1_lo):,}~{krw_ref(e1_hi):,}"
    out["no_chase_reference"]=krw_ref(close+.5*avg)
    prior_high=max(b["high"] for b in clean[-61:-1])
    out["prior_60d_high"]=krw_ref(prior_high)
    if prior_high>e1_hi:
        rr=(prior_high-e1_hi)/(e1_hi-stop)
        out["prior_high_rr"]=round(rr,2)
    else:rr=None
    if rr is None or rr<2:
        out.update(structure_state="LOW_FORWARD_REWARD_RISK",
                   next_action="기존 고점 대비 손익비 부족, 비추격 대기")
    elif not out["entry2_support_research_range"]:
        out.update(structure_state="SECOND_SUPPORT_NOT_CONFIRMED",
                   next_action="1차는 참고만, 2차는 지지 형성 이후 검토")
    else:
        out.update(structure_state="RESEARCH_GEOMETRY_CANDIDATE",
                   next_action="섹터·실적·수급·당일 가격 확인 후 85점 검증; 자동매수 불가")
    return out

def run(asof,fetch=fetch_history,names=FOCUS):
    records=[]
    for ticker,name in names.items():
        bars,source,errors=fetch(ticker,asof)
        records.append(calculate(ticker,name,bars,source,errors,asof))
    return records

def save(records,out):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"focus_daily_structure_prices.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=OUTPUT_FIELDS);w.writeheader();w.writerows(records)
    report=dict(schema="focus_daily_structure_v1",asof=max(
      [r["latest_complete_date"] for r in records if r["latest_complete_date"]] or ["NONE"]),
      research_count=len(records),
      stop_reference_count=sum(bool(r["historical_stop_reference"]) for r in records),
      reasons={r["ticker"]:r["structure_state"] for r in records},
      decision="CASH",trade_approved=False,orders_enabled=False,
      caveat="Completed daily bars only; historic pivots are computed automatically but NOT validated executable stop orders. Corporate actions/price feed issues require review.")
    (out/"focus_daily_structure_status.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    md=["# 관심종목 무료 일봉 구조 분석","",
        "**신규매수 최종 승인: 없음 (CASH)** — 가격 산정 여부와 BUY 적합성은 별개입니다.","",
        "| 종목 | 자료일 | 종가 | 일봉 구조손절 참고 | 1차 가격 연구 | 2차 지지 연구 | 결과 |",
        "|---|---|---:|---:|---|---|---|"]
    for r in records:
        md.append(f"| {r['name']} | {r['latest_complete_date'] or '데이터 없음'} | "
           f"{r['close'] or '—'} | {r['historical_stop_reference'] or '—'} | "
           f"{r['entry1_research_range'] or '—'} | "
           f"{r['entry2_support_research_range'] or '—'} | {r['structure_state']} |")
    md+=["","## 가격이 빠진 이유 / 다음 자동 검증",""]
    for r in records:
        md.append(f"- {r['name']} ({r['ticker']}): {r['next_action']}"
          +(" / 수집 오류: "+r["data_problems"] if r["data_problems"] else ""))
    md+=["","* 표시값은 정규장 확정 일봉을 이용한 연구용 참고가격입니다. "
           "KRX 호가단위 보정·가격조정·기업행위·최신 수급 검증 전에는 지정가 주문으로 사용하지 않습니다.",""]
    (out/"focus_daily_structure_mobile.md").write_text("\n".join(md),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("output"))
    p.add_argument("--asof",default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    a=p.parse_args()
    rows=run(date.fromisoformat(a.asof))
    status=save(rows,a.out)
    print(json.dumps({"date":status["asof"],"research_count":status["research_count"],
         "stop_reference_count":status["stop_reference_count"],
         "decision":status["decision"]},ensure_ascii=False))

if __name__=="__main__":main()
