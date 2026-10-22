#!/usr/bin/env python3
"""Experimental alternative entry A/B on *prospectively recorded* sector signals.

Compare next-session open vs first-2-session pullback limit using identical
date-locked signals. No hindsight-picking the winning strategy, no BUY approval.
Daily OHLC cannot prove intrabar sequencing: for limit fills, simultaneous
stop/target is resolved against the trade, as in primary audit.
"""
import argparse,json
from datetime import date
from pathlib import Path
from shadow_trade_audit import (
    HORIZON,ROUNDTRIP_COST_PCT,VERSION,datestr,finite,evaluate,
    market_session_calendar,price_history)

EXPERIMENT="PULLBACK_LIMIT_035ATR_TWO_SESSIONS_V1"

def assess_limit(signal,bars,market_sessions,cost_pct=ROUNDTRIP_COST_PCT):
    signal_date=datestr(signal.get("signal_date"))
    if not signal_date or signal.get("plan_version")!=VERSION:
        return {"status":"INVALID_SIGNAL"}
    if not market_sessions:
        return {"status":"NO_MARKET_CALENDAR"}
    future_dates=[d for d in market_sessions if d>signal_date]
    if not future_dates:
        return {"status":"PENDING_NEXT_MARKET_SESSION"}
    rows={r["date"]:r for r in bars if r["date"]>signal_date}
    close=finite(signal.get("signal_close"))
    atr=finite(signal.get("signal_atr14"))
    stop=finite(signal.get("stop_reference"))
    cap=finite(signal.get("no_chase_reference"))
    resistance=finite(signal.get("prior_high"))
    if not all((close,atr,stop,cap,resistance)) or not stop<close<=cap:
        return {"status":"INVALID_SIGNAL"}
    limit=close-0.35*atr
    if limit<=stop:
        return {"status":"SKIP_LIMIT_BELOW_STOP"}
    # The order expires after the first two trading sessions following signal.
    for index,day in enumerate(future_dates[:2]):
        bar=rows.get(day)
        if bar is None:
            return {"status":"MISSING_LIMIT_WINDOW_SESSION_PRICE"}
        if bar["open"]<=stop:
            return {"status":"SKIP_BROKEN_SUPPORT_AT_OPEN"}
        at_open=bar["open"]<=limit
        if at_open:
            # Limit order opens in-the-money; conservative opening fill.
            entry=bar["open"]
        elif bar["low"]<=limit:
            # OHLC only establishes a touch, not that a queue order filled.
            # Count as a possible paper fill and apply adverse same-bar ordering.
            entry=limit
        else:
            continue
        if entry<=stop or entry>=cap:
            return {"status":"SKIP_INVALID_LIMIT_FILL"}
        risk=entry-stop
        if not 0.015<=risk/entry<=0.15:
            return {"status":"SKIP_LIMIT_RISK"}
        target=entry+2*risk
        if resistance<target:
            return {"status":"SKIP_LIMIT_PRIOR_RESISTANCE"}
        # Entry starts the five-session holding clock, not signal-date +5.
        subsequent=future_dates[index:index+HORIZON]
        for held,session in enumerate(subsequent,1):
            day_bar=rows.get(session)
            if day_bar is None:
                return {"status":"MISSING_HOLDING_SESSION_PRICE"}
            # On the first day low<=stop may have happened before or after
            # hypothetical limit fill; pessimistically charge stop first.
            if held>1 and day_bar["open"]<=stop:
                sell=day_bar["open"];reason="STOP_GAP"
            elif day_bar["low"]<=stop:
                sell=stop;reason="STOP_FIRST_AMBIGUOUS_INTRABAR"
            elif day_bar["high"]>=target:
                if held==1 and not at_open:
                    # Intraday limit touch may have occurred AFTER the high;
                    # OHLC cannot prove that 2R was attainable after entry.
                    # Never book same-bar target profits for a touch-only fill.
                    continue
                sell=target;reason="TARGET_2R"
            else:
                continue
            net=100*(sell/entry-1)-cost_pct
            return {"status":"CLOSED","exit_reason":reason,
              "limit_reference":round(limit,2),
              "fill_session":index+1,"hold_sessions":held,
              "next_entry_reference":round(entry,2),
              "entry_fill_assumed":True,
              "net_return_pct":round(net,3),
              "net_r":round(net/(100*risk/entry),3)}
        if len(subsequent)<HORIZON:
            return {"status":"OPEN_NEEDS_FUTURE_DAILY_BARS","fill_session":index+1}
        sell=rows[subsequent[-1]]["close"]
        net=100*(sell/entry-1)-cost_pct
        return {"status":"CLOSED","exit_reason":"HORIZON_5D_CLOSE",
          "limit_reference":round(limit,2),
          "fill_session":index+1,"hold_sessions":HORIZON,
          "next_entry_reference":round(entry,2),
          "entry_fill_assumed":True,
          "net_return_pct":round(net,3),
          "net_r":round(net/(100*risk/entry),3)}
    if len(future_dates)<2:
        return {"status":"PENDING_LIMIT_WINDOW"}
    return {"status":"SKIP_LIMIT_NOT_TOUCHED"}

def compare(signals,prices,calendar,old_baseline_results=()):
    # Use recorded baseline results if already CLOSED/SKIP; otherwise evaluate
    # the same signals and archive snapshot with no future signals fabricated.
    old_map={}
    for r in old_baseline_results:
        if not isinstance(r,dict):continue
        if r.get("plan_version")!=VERSION:continue
        if r.get("status")=="CLOSED" or str(r.get("status","")).startswith("SKIP_"):
            old_map.setdefault((r.get("signal_date"),r.get("ticker")),r)
    comparisons=[]
    for r in signals:
        if r.get("plan_version")!=VERSION:continue
        ticker=r.get("ticker")
        if not (isinstance(ticker,str) and len(ticker)==6 and ticker.isdigit()):
            continue
        bars=prices.get(ticker,[])
        old=old_map.get((r.get("signal_date"),ticker))
        if old:
            base={k:v for k,v in old.items()
                  if k in ("status","exit_reason","net_return_pct","net_r")}
        else:
            base=evaluate(r,bars,market_sessions=calendar)
        limit=assess_limit(r,bars,calendar)
        comparisons.append(dict(signal_date=r.get("signal_date"),ticker=ticker,
            sector_id=r.get("sector_id"),next_open=base,pullback_limit=limit))
    return comparisons

def aggregate(comparisons,mode):
    cells=[r[mode] for r in comparisons]
    closed=[x for x in cells if x.get("status")=="CLOSED"]
    nonfills=[x for x in cells if str(x.get("status","")).startswith("SKIP_")]
    pending=[x for x in cells if str(x.get("status","")).startswith(("PENDING_","OPEN_"))]
    missing=[x for x in cells if str(x.get("status","")).startswith(("MISSING_","NO_MARKET_","INVALID_"))]
    determined=len(closed)+len(nonfills)
    avg=round(sum(x["net_return_pct"] for x in closed)/len(closed),3) if closed else None
    avg_per_decided=(round(sum(x["net_return_pct"] for x in closed)/determined,3)
                     if determined else None)
    return dict(signal_count=len(cells),closed=len(closed),unfilled_or_skipped=len(nonfills),
       incomplete=len(pending),missing_data_or_invalid=len(missing),
       win_rate_filled_pct=round(100*sum(x["net_return_pct"]>0 for x in closed)/len(closed),1)
           if closed else None,
       mean_net_pct_filled=avg,
       mean_net_pct_per_decided_signal=avg_per_decided,
       mean_net_r_filled=round(sum(x["net_r"] for x in closed)/len(closed),3) if closed else None,
       mode_not_validated_as_profitable=True)

def save(out,rows):
    out.mkdir(parents=True,exist_ok=True)
    stats=dict(version="next_open_vs_pullback_035atr_v1",
      setup="Same locked sector top5 close signal. Entry A next open, entry B day1/2 pullback limit = signal close -0.35 ATR.",
      execution_warning="Intrabar order/queue not verifiable; stop-first conservative; differing fill rates and time exposure.",
      experimental_only=True,trade_approved=False,decision="CASH",
      next_open=aggregate(rows,"next_open"),
      pullback_limit=aggregate(rows,"pullback_limit"))
    (out/"entry_ab_results.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"entry_ab_scorecard.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# C3·K100 진입방식 A/B 실전형 연구","",
      "**실제 신규매수: CASH — 모의성과와 최종 종목 80점은 별개**","",
      "| 지표 | 다음 날 시초가 | D+1~D+2 눌림 지정가 |",
      "|---|---:|---:|"]
    for k,label in (("closed","완료된 모의매매"),
                    ("unfilled_or_skipped","미진입·조건 미충족"),
                    ("incomplete","미완료"),
                    ("missing_data_or_invalid","자료 누락·유효성 실패"),
                    ("win_rate_filled_pct","체결 가정 후 승률(%)"),
                    ("mean_net_pct_filled","체결 가정 후 평균 순수익(%)"),
                    ("mean_net_pct_per_decided_signal","평가 가능한 신호당 평균 순수익(%)")):
        values=[stats[mode][k] for mode in ("next_open","pullback_limit")]
        lines.append(f"| {label} | {values[0] if values[0] is not None else '—'} | "+
                     f"{values[1] if values[1] is not None else '—'} |")
    lines+=["","**검증 방법**: 사전에 기록한 동일 종목만 비교하고 다음 거래일 이후 일봉만 사용.",
       "눌림 지정가는 전일 확정 종가 - 0.35×ATR14로 정한 고정 연구안이며 최적화된 수익전략이 아닙니다.",
       "지정가에 닿았다고 항상 실제 주문이 체결되는 것은 아닙니다.",
       "당일 저점이 손절을 침범했는지 순서를 알 수 없으면 손절을 먼저 가정했습니다.",
       "체결 가정된 거래의 승률만 비교하지 말고 미체결까지 포함한 신호당 수익을 함께 보십시오.",
       "적은 표본과 결측 데이터로 우월한 매매법을 선언하지 않습니다.",""]
    (out/"entry_ab_mobile.md").write_text("\n".join(lines),encoding="utf-8")
    # Compact phone report: one short experiment section, not another giant table.
    compact=out/"sector_first_compact_mobile.md"
    if compact.is_file():
        marker="## ⑤ 진입방식 A/B 실험 (실제 체결 아님)"
        old_text=compact.read_text(encoding="utf-8").split("\n"+marker)[0].rstrip()
        def result(mode):
            s=stats[mode]
            avg=s["mean_net_pct_per_decided_signal"]
            return (str(s["closed"])+"건 평가완료, 신호당 평균 "+
                    (str(avg)+"%" if avg is not None else "계산불가")+
                    ", 미진입·스킵 "+str(s["unfilled_or_skipped"])+"건")
        addition=["",marker,"",
            "- 시초가: "+result("next_open"),
            "- 2일 눌림 지정가: "+result("pullback_limit"),
            "- 두 방식 모두 모의가정, 실제 수익 우위 미입증. 최종 신규매수: CASH.",""]
        compact.write_text(old_text+"\n"+"\n".join(addition),encoding="utf-8")
    return stats

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--signals",type=Path,default=Path("output/shadow_signals.json"))
    p.add_argument("--baseline-results",type=Path,default=Path("output/shadow_results.json"))
    p.add_argument("--evidence",type=Path,default=Path("inputs/evidence"))
    p.add_argument("--out",type=Path,default=Path("output"))
    a=p.parse_args()
    def read(path):
        if not path.is_file():return []
        try:r=json.loads(path.read_text(encoding="utf-8"))
        except (ValueError,OSError):return []
        return r if isinstance(r,list) else []
    signals=read(a.signals)
    basis=read(a.baseline_results)
    prices=price_history(a.evidence,{r["ticker"] for r in signals
                                  if isinstance(r,dict) and isinstance(r.get("ticker"),str)})
    calendar=market_session_calendar(a.evidence)
    rows=compare(signals,prices,calendar,basis)
    stats=save(a.out,rows)
    print(json.dumps({"signals":len(rows),"next_open":stats["next_open"],
      "pullback_limit":stats["pullback_limit"],"decision":"CASH"},ensure_ascii=False))

if __name__=="__main__":
    main()
