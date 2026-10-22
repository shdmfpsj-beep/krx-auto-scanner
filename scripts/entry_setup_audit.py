#!/usr/bin/env python3
"""Real as-of KRX daily geometry for market-close research, never a BUY.

Use validated independent 65+ bars, held pivot + ATR, first entry range,
support retest, and *conservative high-side* entry reward/risk vs 60d high.
Only completed as-of candles. No next-day price or retrospective fills.
Technical setup grade is NOT the user's independently verified 80/100 score.
"""
import argparse,json,math,re
from datetime import date
from pathlib import Path

SCHEMA="sector_first_entry_geometry_v1"
SOURCES=("V18_KRX_CACHED","pykrx","FinanceDataReader")

def number(x):
    if isinstance(x,bool):return None
    try:
        v=float(str(x).replace(",","").strip())
        return v if math.isfinite(v) and v>0 else None
    except (TypeError,ValueError):return None

def dated(x):
    try:return date.fromisoformat(str(x)[:10])
    except (TypeError,ValueError):return None

def level_range(x):
    """Source ranges are display hints, never assumed filled orders."""
    if isinstance(x,(float,int)) and not isinstance(x,bool):
        a=number(x)
        return (a,a) if a else None
    if not isinstance(x,str) or not x.strip():return None
    parts=re.split(r"\s*[~〜–]\s*",x.strip())
    if len(parts)!=2:return None
    nums=[number(z) for z in parts]
    if any(v is None for v in nums) or nums[0]>nums[1]:return None
    return nums[0],nums[1]

def quote_step(value):
    """KRX ordinary share price bands, research only (ETF exceptions)."""
    v=number(value)
    if v is None:return None
    return (1 if v<2000 else 5 if v<5000 else 10 if v<20000 else
            50 if v<50000 else 100 if v<200000 else
            500 if v<500000 else 1000)

def down_tick(value):
    step=quote_step(value)
    return int(math.floor(value/step)*step) if step else None

def up_tick(value):
    step=quote_step(value)
    if step is None:return None
    val=int(math.ceil(value/step)*step)
    # Crossing KRX band boundaries must not create invalid increments.
    if val!=value and quote_step(val)!=step:return up_tick(val)
    return val

def check_row(stock,raw,asof,conflicted):
    ticker=str(stock.get("ticker",""))
    base=dict(ticker=ticker,name=str(stock.get("name") or ticker),
        sector_id=stock.get("sector_id"),
        asof=str(asof) if asof else None,code="NO_ASOF_DAILY_STRUCTURE",
        first_entry_krw=None,second_entry_support_krw=None,stop_krw=None,
        resistance_krw=None,no_chase_krw=None,
        stop_distance_pct=None,forward_rr_at_first_ceiling=None,
        target_2r_krw=None,required_atr_to_2r=None,
        required_atr_to_60d_resistance=None,
        five_day_2r_stretch_warning=None,
        five_day_research_timing_status="UNVERIFIED",
        technical_research_pass=False,real_buy_approved=False,
        final_80_score_verified=False,
        conditional_next_action="신규매수 CASH: 완전한 65봉 구조와 계좌·실적·재료 검증 대기")
    if not asof:return base
    status=str(stock.get("independent_stop_status") or "")
    if ticker in conflicted or status=="CROSS_SOURCE_CLOSE_CONFLICT" or raw.get("price_conflict"):
        return {**base,"code":"CROSS_SOURCE_PRICE_CONFLICT"}
    if raw.get("latest_complete_date")!=str(asof) or (
        dated(raw.get("pivot_date")) and dated(raw.get("pivot_date"))>asof):
        return {**base,"code":"BAR_OR_PIVOT_DATE_MISMATCH"}
    if raw.get("data_source") not in SOURCES or number(raw.get("bar_count")) is None or (
         number(raw.get("bar_count"))<65):
        return {**base,"code":"NO_65_VERIFIED_OHLC_BARS"}
    if raw.get("data_problems") not in ("",None):
        return {**base,"code":"SOURCE_OHLC_DATA_ISSUE"}
    close=number(raw.get("close"))
    pivot=number(raw.get("pivot_low"))
    stop=number(raw.get("historical_stop_reference"))
    atr=number(raw.get("atr14"))
    high=number(raw.get("prior_60d_high"))
    chase=number(raw.get("no_chase_reference"))
    if not (close and pivot and stop and atr and high and chase
            and 0<stop<pivot<close and dated(raw.get("pivot_date")) is not None):
        return {**base,"code":"UNVERIFIED_DAILY_STOP_PIVOT_ATR"}
    # Completed close must match selected-source close, not stale generic rows.
    if stock.get("independent_stop_status")!="HISTORICAL_DAILY_REFERENCE_ONLY":
        return {**base,"code":"INDEPENDENT_PIVOT_NOT_ACCEPTED"}
    e1=level_range(raw.get("entry1_research_range"))
    if not e1:return {**base,"code":"NO_VALID_FIRST_ENTRY_RANGE"}
    a,b=e1
    if not(stop<a<=b and b<=chase and a<high and atr<close):
        return {**base,"code":"CHASE_OR_ENTRY_GEOMETRY_INVALID"}
    # Stop reference is always *rounded DOWN* (conservative wider risk), entry
    # risk tested at the more expensive UPPER limit after rounding UP.
    stopq=down_tick(stop)
    lo=up_tick(a)
    hi=up_tick(b)
    highq=down_tick(high)
    chaseq=down_tick(chase)
    if not (stopq and lo and hi and highq and chaseq
            and stopq<lo<=hi<=chaseq and highq>hi):
        return {**base,"code":"PRICE_BAND_ROUNDING_INVALID"}
    risk=(hi-stopq)/hi
    rr=(highq-hi)/(hi-stopq)
    if not 0.02<=risk<=0.12:
        return {**base,"code":"STOP_DISTANCE_OUTSIDE_2_TO_12_PCT",
                "stop_distance_pct":round(100*risk,2),"stop_krw":stopq,
                "first_entry_krw":[lo,hi]}
    if rr<2:
        return {**base,"code":"FORWARD_REWARD_RISK_BELOW_2R",
                "stop_distance_pct":round(100*risk,2),
                "forward_rr_at_first_ceiling":round(rr,2),
                "stop_krw":stopq,"resistance_krw":highq,
                "first_entry_krw":[lo,hi]}
    e2=level_range(raw.get("entry2_support_research_range"))
    e2q=None
    if e2:
        low=up_tick(e2[0]);upper=up_tick(e2[1])
        if low and upper and stopq<low<=upper<hi:
            e2q=[low,upper]
    required_atr=(2*(hi-stopq))/atr
    high_atr=(highq-hi)/atr
    # Empirical forecasting is NOT implied: 4*ATR in 5 sessions is a
    # deliberately conservative stretch flag awaiting out-of-sample calibration.
    # A high 60-day resistance RR by itself never establishes 5D burstability.
    stretched=required_atr>4.0
    return {**base,"code":"TECHNICAL_GEOMETRY_READY_STILL_NO_BUY",
        "required_atr_to_2r":round(required_atr,2),
        "required_atr_to_60d_resistance":round(high_atr,2),
        "five_day_2r_stretch_warning":stretched,
        "five_day_research_timing_status":(
             "5D_2R_DISTANCE_STRETCHED_OVER_4_ATR_RESEARCH_FLAG"
             if stretched else "5D_2R_WITHIN_4_ATR_RESEARCH_FLAG_NOT_PROBABILITY"),
        "first_entry_krw":[lo,hi],
        "second_entry_support_krw":e2q,
        "stop_krw":stopq,"resistance_krw":highq,"no_chase_krw":chaseq,
        "stop_distance_pct":round(100*risk,2),
        "forward_rr_at_first_ceiling":round(rr,2),
        "target_2r_krw":up_tick(hi+2*(hi-stopq)),
        "technical_research_pass":True,
        "conditional_next_action":("1차 매수가 상단 이하로 눌린 후 재확인; "
            "2차 매수는 실제 지지·계좌 여력이 별도로 확인되는 경우만 연구. "
            "검증된 80점·실질 호재·당일 가격 없으므로 CASH.")}

def build(report):
    asof=dated(report.get("asof"))
    refs={str(x.get("ticker","")):x for x in (
        report.get("focus_daily_structure_research") or [])}
    conflicts=set(str(x) for x in (report.get("focus_close_conflict_tickers") or []))
    picks=[]
    for stock in (report.get("stock_research_top5") or [])[:5]:
        ticker=str(stock.get("ticker",""))
        picks.append(check_row(stock,refs.get(ticker,{}),asof,conflicts))
    return dict(schema=SCHEMA,asof=str(asof) if asof else None,
        candidates=picks,stock_count=len(picks),
        technical_geometry_pass_count=sum(
            bool(x["technical_research_pass"]) for x in picks),
        forward_2r_is_guaranteed_5d_target=False,
        theoretical_prices_not_limit_orders=True,
        prospective_trades_created=0,trade_approved=False,
        final_80_point_approval=False,decision="CASH")

def money(x):
    return f"{x:,.0f}" if isinstance(x,(int,float)) else "—"

def rng(x):
    if not x:return "—"
    return "~".join(money(z) for z in x)

def render(report):
    lines=["","## 기술적 진입 타점 품질 (실제 일봉 기준)","",
        "**CASH — 유리한 가격 구조와 종합 매수 승인은 별개입니다.**","",
        "| 종목 | 1차 연구 | 2차 지지 연구 | 구조 손절 | 60일 저항 | 손익비 | 2R 필요 ATR |",
        "|---|---|---|---:|---:|---:|---:|"]
    for x in report["candidates"]:
        lines.append("| "+x["name"].replace("|","/")[:20]+" | "+
          rng(x["first_entry_krw"])+" | "+rng(x["second_entry_support_krw"])+
          " | "+money(x["stop_krw"])+" | "+money(x["resistance_krw"])+
          " | "+(str(x["forward_rr_at_first_ceiling"])+"R"
                 if x["forward_rr_at_first_ceiling"] is not None else "—")+
          " | "+(str(x["required_atr_to_2r"])+"배"
                  if x["required_atr_to_2r"] is not None else "—")+" |")
    if not report["candidates"]:
        lines.append("| 검증된 TOP5 없음 | — | — | — | — | — | — |")
    lines+=["","### 종목별 매매 준비가 안 된 정확한 이유",""]
    for x in report["candidates"]:
        lines.append("- "+x["name"].replace("|","/")[:25]+": "+
                     x["code"]+
            (" / 5거래일 2R 목표 4ATR 초과(상당한 가격 이동 필요)"
             if x["five_day_2r_stretch_warning"] else "")+
            (f" / 구조손절 거리 {x['stop_distance_pct']}%"
                if x["stop_distance_pct"] is not None else ""))
    lines+=["","*진입 참고가는 기존 확정 일봉의 ATR·피벗·최근 60일 고점에서 계산했고,"
            " KRX 일반 주식 호가단위로 보수적으로 조정했습니다.",
      "*목표 2R까지 필요한 ATR 배수를 병기합니다. 4ATR 초과는 단기 목표가 도달을"
       " 쉽게 가정하지 않도록 만든 연구 경고이며 통계적 확률이나 확정 탈락 기준이 아닙니다.",
      "*전고점까지 2R 이상이더라도 1~5거래일 내 도달 확률이 검증된 것은 아닙니다.",
      "*장중 갭·미체결·수수료·기업행위 및 현재 보유 여부는 별도로 확인해야 하므로 자동 주문하지 않습니다.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    target=a.root/"sector_first_with_financials.json"
    if not target.is_file():raise SystemExit("MISSING_SECTOR_FINANCIAL_REPORT")
    report=json.loads(target.read_text(encoding="utf-8"))
    study=build(report)
    (a.root/"entry_setup_audit.json").write_text(
      json.dumps(study,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.root/"entry_setup_audit_mobile.md").write_text(render(study),encoding="utf-8")
    compact=a.root/"sector_first_compact_mobile.md"
    if compact.is_file():
        with compact.open("a",encoding="utf-8") as f:
            f.write("\n"+render(study))
    print(json.dumps(dict(asof=study["asof"],
       technical=study["technical_geometry_pass_count"],
       considered=study["stock_count"],decision=study["decision"]),
       ensure_ascii=False))
if __name__=="__main__":main()
