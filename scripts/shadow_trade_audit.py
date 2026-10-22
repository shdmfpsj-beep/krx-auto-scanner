#!/usr/bin/env python3
"""Prospective C3/K100 5-session shadow journal on free completed KRX daily bars.

Record a signal only AFTER its sector-first as-of report; enter hypothetically
at the NEXT day's open (never use today's closing fill from a 22:00 report).
Evaluate only future evidence already completed. Same-bar target+stop assumes
STOP first. Fees/slippage are scenario assumptions, not broker fee quotes.
This is a research ledger, not a brokerage order or proof of live performance.
"""
import argparse,csv,json,math
from collections import defaultdict
from datetime import date,datetime
from zoneinfo import ZoneInfo
from pathlib import Path

VERSION="next_open_5d_v1"
HORIZON=5
ROUNDTRIP_COST_PCT=0.40  # conservative modeled friction, adjustable later
COLUMNS=("signal_date","ticker","sector_id","signal_close","signal_atr14",
         "stop_reference","no_chase_reference","prior_high",
         "research_proxy_index","plan_version")

def finite(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>0 else None
    except (ValueError,TypeError):
        return None

def datestr(x):
    try:return date.fromisoformat(str(x)[:10]).isoformat()
    except (TypeError,ValueError):return None

def new_signals(report,price_rows,run_date=None):
    asof=datestr(report.get("asof"))
    run_date=run_date or datetime.now(ZoneInfo("Asia/Seoul")).date()
    # An old report rerun tonight is NOT a signal received on the old date.
    # Fail closed rather than retroactively create a profitable paper trade.
    if not asof or asof!=run_date.isoformat() or report.get("status")!="PROVISIONAL_RESEARCH_ONLY":
        return []
    indices={str(r.get("ticker","")):r for r in price_rows}
    disputed=set(report.get("focus_close_conflict_tickers") or [])
    signals=[]
    for row in (report.get("stock_research_top5") or [])[:5]:
        t=str(row.get("ticker",""))
        # Never create a prospective simulated trade off a price known to
        # disagree across same-date feeds: 2026-10-21 LS ELECTRIC showed why.
        if t in disputed or row.get("independent_stop_status")=="CROSS_SOURCE_CLOSE_CONFLICT":
            continue
        ref=indices.get(t,{})
        close=finite(ref.get("close"))
        stop=finite(ref.get("historical_stop_reference"))
        atr=finite(ref.get("atr14"))
        chase=finite(ref.get("no_chase_reference"))
        resistance=finite(ref.get("prior_60d_high"))
        if ref.get("latest_complete_date")!=asof or ref.get("data_source") not in (
           "V18_KRX_CACHED","FinanceDataReader","pykrx"):
            continue
        if not (len(t)==6 and t.isdigit() and close and atr and stop and chase and resistance):
            continue
        if not (stop<close<=chase and resistance>close):
            continue
        if (close-stop)/close>0.20:
            continue
        signals.append(dict(signal_date=asof,ticker=t,sector_id=row.get("sector_id",""),
            signal_close=round(close,2),signal_atr14=round(atr,2),
            stop_reference=round(stop,2),no_chase_reference=round(chase,2),
            prior_high=round(resistance,2),
            research_proxy_index=row.get("proxy_index"),
            plan_version=VERSION))
    return signals

def merge_signals(old,new,max_age_sessions=None):
    kept={}
    for r in list(old)+list(new):
        date_=datestr(r.get("signal_date"));ticker=str(r.get("ticker",""))
        if not date_ or len(ticker)!=6 or not ticker.isdigit():
            continue
        if r.get("plan_version")!=VERSION:continue
        if not all(finite(r.get(k)) for k in (
             "signal_close","signal_atr14","stop_reference",
             "no_chase_reference","prior_high")):continue
        key=(date_,ticker,VERSION)
        # Never mutate a previously recorded forward signal when the stock
        # is rescored or later becomes a top candidate again.
        kept.setdefault(key,{key_:r.get(key_) for key_ in COLUMNS})
    return [kept[k] for k in sorted(kept)]

def price_history(evidence_root,tickers):
    found=defaultdict(dict)
    roots=list(Path(evidence_root).rglob("market/daily_prices"))
    if len(roots)!=1:return {}
    for market in ("KOSPI","KOSDAQ"):
        directory=roots[0]/market
        if not directory.is_dir():continue
        for path in sorted(directory.glob("*.csv")):
            if datestr(path.stem) is None:continue
            with path.open(encoding="utf-8-sig",newline="") as f:
                for row in csv.DictReader(f):
                    t=str(row.get("ticker",""))
                    if t not in tickers:continue
                    d=datestr(row.get("Date"))
                    op=finite(row.get("Open"));high=finite(row.get("High"))
                    low=finite(row.get("Low"));close=finite(row.get("Close"))
                    if not (d and op and high and low and close and
                       low<=min(op,close)<=max(op,close)<=high):
                        continue
                    if d in found[t]:
                        # duplicate source dates are not safe to use for fill
                        found[t][d]=None
                    else:
                        found[t][d]=dict(date=d,open=op,high=high,low=low,close=close)
    return {t:sorted((x for x in values.values() if x),
               key=lambda x:x["date"]) for t,values in found.items()}

def market_session_calendar(evidence_root):
    """Use dated market-price file names as an observed trading-session calendar.
    A missing stock candle on a market session must not disappear from PnL."""
    roots=list(Path(evidence_root).rglob("market/daily_prices"))
    if len(roots)!=1:return []
    d=set()
    for market in ("KOSPI","KOSDAQ"):
        folder=roots[0]/market
        if not folder.is_dir():continue
        for p in folder.glob("*.csv"):
            day=datestr(p.stem)
            if day:d.add(day)
    return sorted(d)

def evaluate(signal,bars,horizon=HORIZON,cost_pct=ROUNDTRIP_COST_PCT,
             market_sessions=None):
    """Next-open fill and 5-day conservative exit, net return in percent.

    Partial pending runs cannot be counted as losses or wins. Stops/targets
    both reached in one daily candle -> assume loss due unknown ordering.
    """
    t0=datestr(signal.get("signal_date"))
    if not t0:return dict(status="INVALID_SIGNAL")
    future=[r for r in bars if r["date"]>t0]
    calendar=[d for d in (market_sessions or []) if d>t0]
    if not future:
        return dict(status="MISSING_NEXT_SESSION_PRICE" if calendar
                    else "PENDING_NEXT_TRADING_DAY")
    if calendar and future[0]["date"]!=calendar[0]:
        return dict(status="MISSING_NEXT_SESSION_PRICE")
    first=future[0]
    if (date.fromisoformat(first["date"])-date.fromisoformat(t0)).days>10:
        return dict(status="MISSING_NEXT_SESSION_HISTORY")
    stop=finite(signal.get("stop_reference"))
    cap=finite(signal.get("no_chase_reference"))
    previous=finite(signal.get("signal_close"))
    old_high=finite(signal.get("prior_high"))
    if not (stop and cap and previous and old_high and stop<previous<=cap):
        return dict(status="INVALID_SIGNAL")
    buy=first["open"]
    if buy>=cap:return dict(status="SKIP_GAP_UP_ABOVE_NO_CHASE")
    if buy<=stop:return dict(status="SKIP_OPEN_BELOW_STRUCTURE")
    risk=buy-stop
    if not 0.015<=risk/buy<=0.15:
        return dict(status="SKIP_RISK_DISTANCE")
    target=buy+2*risk
    if old_high<target:
        return dict(status="SKIP_PRIOR_RESISTANCE_BLOCKS_2R")
    observed=future[:horizon]
    for n,bar in enumerate(observed,1):
        if calendar and n<=len(calendar) and bar["date"]!=calendar[n-1]:
            return dict(status="MISSING_INTERMEDIATE_SESSION_PRICE")
        # A price gap through stop gets worse opening execution.
        if n>1 and bar["open"]<=stop:
            exit_price=bar["open"];reason="STOP_GAP_DOWN"
        elif bar["low"]<=stop:
            exit_price=stop;reason="STOP_FIRST_CONSERVATIVE"
        elif bar["high"]>=target:
            exit_price=target;reason="TARGET_2R"
        else:
            continue
        net=100*(exit_price/buy-1)-cost_pct
        return dict(status="CLOSED",exit_reason=reason,hold_sessions=n,
            next_open_entry=round(buy,2),target_2r=round(target,2),
            effective_stop=round(stop,2),exit_price=round(exit_price,2),
            net_return_pct=round(net,3),net_r=round(net/(100*risk/buy),3))
    if calendar and len(observed)<min(horizon,len(calendar)):
        return dict(status="MISSING_INTERMEDIATE_SESSION_PRICE")
    if len(observed)<horizon:
        return dict(status="OPEN_WAIT_MORE_BARS",bars_seen=len(observed),
                    entry_reference=round(buy,2),target_2r=round(target,2))
    exit_price=observed[-1]["close"]
    net=100*(exit_price/buy-1)-cost_pct
    return dict(status="CLOSED",exit_reason="HORIZON_5D_CLOSE",
         hold_sessions=horizon,next_open_entry=round(buy,2),
         target_2r=round(target,2),effective_stop=round(stop,2),
         exit_price=round(exit_price,2),net_return_pct=round(net,3),
         net_r=round(net/(100*risk/buy),3))

def summarise(signals,prices,previous_results=(),market_sessions=None):
    """Freeze completed/skip outcomes once first evaluated, avoiding later
    archive roll-offs or revised historical OHLC rewriting observed results."""
    frozen={}
    for old in previous_results:
        if not isinstance(old,dict):continue
        if old.get("plan_version")!=VERSION:continue
        if old.get("status")=="CLOSED" or str(old.get("status","")).startswith("SKIP_"):
            key=(old.get("signal_date"),old.get("ticker"),old.get("plan_version"))
            frozen.setdefault(key,old)
    results=[]
    for r in signals:
        key=(r["signal_date"],r["ticker"],VERSION)
        old=frozen.get(key)
        if old and all(str(old.get(field))==str(r.get(field))
                       for field in ("signal_close","stop_reference","no_chase_reference","prior_high")):
            results.append(old)
        else:
            res=evaluate(r,prices.get(r["ticker"],[]),
                         market_sessions=market_sessions)
            results.append(dict(**r,**res))
    closed=[x for x in results if x["status"]=="CLOSED"]
    outcomes=[x["net_return_pct"] for x in closed]
    winners=[x for x in closed if x["net_return_pct"]>0]
    stats=dict(schema="shadow_trade_outcomes_v1",signal_count=len(signals),
       closed_count=len(closed),closed_wins=len(winners),
       pending_count=sum(x["status"].startswith(("OPEN_","PENDING_"))
                         for x in results),
       skipped_count=sum(x["status"].startswith(("SKIP_","INVALID_","MISSING_"))
                         for x in results),
       conservative_cost_roundtrip_pct=ROUNDTRIP_COST_PCT,
       realised_paper_win_rate_pct=round(100*len(winners)/len(closed),1) if closed else None,
       realised_paper_avg_net_pct=round(sum(outcomes)/len(outcomes),3) if closed else None,
       realised_paper_avg_net_r=round(
          sum(x["net_r"] for x in closed)/len(closed),3) if closed else None,
       enough_samples_for_research=len(closed)>=30,
       paper_edge_status=("NO_COMPLETED_TRADES" if not closed else
           "LESS_THAN_30_COMPLETED" if len(closed)<30 else
           "NON_POSITIVE_NET_EXPECTANCY" if sum(outcomes)<=0 else
           "PAPER_POSITIVE_NOT_LIVE_VALIDATED"),
       statistically_valid_profit_claim=False,
       cash_if_unverified=True,orders_enabled=False)
    return results,stats

def read_csv(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def save(out,signals,results,stats):
    out.mkdir(parents=True,exist_ok=True)
    (out/"shadow_signals.json").write_text(json.dumps(signals,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"shadow_results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"shadow_scorecard.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    txt=["# C3/K100 5거래일 전향적 모의매매 검증","",
         "**실제 주문·수익 보장 없음. 미래를 이미 아는 백테스트가 아닌 일일 신호 기록 방식.**","",
         f"- 기록된 신호: {stats['signal_count']}건",
         f"- 완료된 가상매매: {stats['closed_count']}건",
         f"- 평가 대기: {stats['pending_count']}건",
         f"- 체결조건 미충족/제외: {stats['skipped_count']}건",
         "- 왕복 비용 가정: "+str(ROUNDTRIP_COST_PCT)+"% (수수료·세금·슬리피지 포함 보수적 모형)"]
    if stats["closed_count"]:
        txt+=["- 수익 거래 비율: "+str(stats["realised_paper_win_rate_pct"])+"%",
          "- 거래당 평균 순수익률: "+str(stats["realised_paper_avg_net_pct"])+"%",
          "- 거래당 평균 R: "+str(stats["realised_paper_avg_net_r"])]
    else:txt.append("- 미완료: 실제 승률이나 수익률을 산출하지 않음")
    txt+=["","규칙: 신호 다음 거래일 시초가 진입, 갭상승 추격 금지, 구조 손절, 2R 목표, 5거래일 만기.",
      "같은 일봉에서 손절과 목표를 동시에 만졌다면 손절을 먼저 적용합니다.",
      "30건 미만 또는 표본 편향 검증 전 성과는 투자 우위가 입증됐다는 뜻이 아닙니다.",
      "**최종 신규매수: CASH — 별도의 종목 85점 검증·실제 타점 확인 필요.**",""]
    (out/"shadow_scorecard_mobile.md").write_text("\n".join(txt),encoding="utf-8")
    # Keep the two-table sector-first report intact, with one short
    # prospective performance paragraph at the end for phone readers.
    compact=out/"sector_first_compact_mobile.md"
    if compact.is_file():
        marker="\n## ④ 전향적 모의매매 성적표"
        base=compact.read_text(encoding="utf-8").split(marker)[0].rstrip()
        status=stats["paper_edge_status"]
        extra=[marker,"",
            "- 기록 / 평가완료: "+str(stats["signal_count"])+" / "+str(stats["closed_count"]),
            "- 순수익률 평균: "+(
                 str(stats["realised_paper_avg_net_pct"])+"%" if stats["closed_count"] else "표본 없음"),
            "- 연구 판정: "+status,
            "- 30건 미만 및 체결/비용 모형만으로는 수익 우위를 입증하지 못합니다.",
            "- 실제 매수 승인: 없음 (CASH)",""]
        compact.write_text(base+"\n"+"\n".join(extra),encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path,default=Path("output/sector_first_with_prices.json"))
    p.add_argument("--dynamic",type=Path,default=Path("output/dynamic/focus_daily_structure_prices.csv"))
    p.add_argument("--history",type=Path,default=Path("inputs/evidence"))
    p.add_argument("--previous",type=Path,default=Path("output/previous_shadow_signals.json"))
    p.add_argument("--previous-results",type=Path,default=Path("output/previous_shadow_results.json"))
    p.add_argument("--out",type=Path,default=Path("output"))
    p.add_argument("--run-date",default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    a=p.parse_args()
    try:report=json.loads(a.report.read_text(encoding="utf-8")) if a.report.is_file() else {}
    except (ValueError,OSError):report={}
    try:old=json.loads(a.previous.read_text(encoding="utf-8")) if a.previous.is_file() else []
    except (ValueError,OSError):old=[]
    if not isinstance(old,list):old=[]
    try:
        old_results=json.loads(a.previous_results.read_text(encoding="utf-8")) if a.previous_results.is_file() else []
    except (ValueError,OSError):
        old_results=[]
    if not isinstance(old_results,list):old_results=[]
    signals=merge_signals(old,new_signals(report,read_csv(a.dynamic),date.fromisoformat(a.run_date)))
    price=price_history(a.history,{x["ticker"] for x in signals})
    market_sessions=market_session_calendar(a.history)
    results,stats=summarise(signals,price,old_results,market_sessions)
    stats["observed_market_sessions"]=len(market_sessions)
    stats["prior_completed_outcomes_preserved"]=sum(
        r["status"]=="CLOSED" for r in results if any(
            old.get("signal_date")==r.get("signal_date") and
            old.get("ticker")==r.get("ticker") and
            old.get("status")=="CLOSED" for old in old_results if isinstance(old,dict)))
    save(a.out,signals,results,stats)
    print(json.dumps(stats,ensure_ascii=False))

if __name__=="__main__":main()
