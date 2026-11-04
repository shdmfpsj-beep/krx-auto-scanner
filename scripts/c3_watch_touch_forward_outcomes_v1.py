"""Research-only watch-touch forward outcome, never an executed-trade return."""
import argparse,csv,json
from pathlib import Path
from c3_price_concordance_v1 import read_rows

HORIZONS=(5,10,20)

def analyze(plan,prices):
    ticker=plan["ticker"]
    registered=plan["registered_day"]
    low,high,stop,target=(float(plan[k]) for k in ("watch_low","watch_high","structure_stop","target1"))
    if not 0<stop<low<=high<target:
        raise ValueError("INVALID_PLAN_GEOMETRY")
    series=sorted((day,bar) for (code,day),bar in prices.items() if code==ticker and day>registered)
    watch_window=int(plan["expires_after_sessions"])
    if watch_window<1:
        raise ValueError("INVALID_WATCH_WINDOW")
    events=[]
    for i,(day,bar) in enumerate(series[:watch_window]):
        if not (bar["low"]<=high and bar["high"]>=low):
            continue
        status=("GAP_BELOW_STOP" if bar["open"]<=stop else
                "SAME_BAR_STOP_AMBIGUOUS" if bar["low"]<=stop else "WATCH_TOUCH_ONLY")
        outcomes=[]
        for horizon in HORIZONS:
            future=series[i+1:i+1+horizon]
            complete=len(future)==horizon
            # Descriptive post-touch excursion, anchored to touch-day close.
            # Never call these executable entry returns or completed horizon
            # metrics when fewer than horizon future sessions are observed.
            future_max_high=max((x["high"] for _,x in future),default=None)
            future_min_low=min((x["low"] for _,x in future),default=None)
            mfe=round(100*(future_max_high/bar["close"]-1),3) if future_max_high is not None else None
            mae=round(100*(future_min_low/bar["close"]-1),3) if future_min_low is not None else None
            outcomes.append(dict(horizon_sessions=horizon,observed_future_sessions=len(future),
                                 observation_window_complete=complete,
                                 reference_is_touch_day_close=True,
                                 observed_max_favorable_excursion_pct=mfe,
                                 observed_max_adverse_excursion_pct=mae,
                                 complete=complete,
                                 next_session_to_horizon_close_pct=(
                                     round(100*(future[-1][1]["close"]/bar["close"]-1),3)
                                     if complete else None),
                                 future_stop_touch_days=sum(x["low"]<=stop for _,x in future),
                                 future_target_touch_days=sum(x["high"]>=target for _,x in future),
                                 strategy_return_pct=None,verified_fill=False))
        events.append(dict(date=day,status=status,entry_reference_close=bar["close"],
                           actual_entry_price=None,verified_fill=False,outcomes=outcomes))
    return dict(ticker=ticker,plan_id=plan["plan_id"],events=events,
                watch_events=len(events),verified_fills=0,
                trade_approved=False,orders_enabled=False)

def build(plans,prices):
    results=[analyze(p,prices) for p in plans]
    if len(results)!=2 or len({r["ticker"] for r in results})!=2:
        raise ValueError("EXPECTED_UNIQUE_TOP2")
    return dict(schema="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1",
                price_certified=False,strategy_profitability_verified=False,
                trade_approved=False,orders_enabled=False,results=results)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True);p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True);p.add_argument("--markdown",required=True)
    a=p.parse_args()
    with open(a.plans,encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    report=build(plans,read_rows(a.prices))
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["### 매수구간 접촉 후 5·10·20거래일 관찰 (실제 매매 성과 아님)",
           "| 종목 | 접촉일 | 분류 | 5일 | 10일 | 20일 |",
           "|---|---|---|---|---|---|"]
    for r in report["results"]:
        if not r["events"]:
            lines.append(f"| {r['ticker']} | - | 접촉 없음 | - | - | - |")
        for e in r["events"]:
            outcomes=["대기" if not h["complete"] else f"{h['next_session_to_horizon_close_pct']:+.2f}%" for h in e["outcomes"]]
            lines.append(f"| {r['ticker']} | {e['date']} | {e['status']} | "+" | ".join(outcomes)+" |")
    lines.extend(["","> 접촉일 종가 대비 이후 종가 변화율이며 실제 진입가·체결·손익률이 아닙니다."])
    Path(a.markdown).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"schema":report["schema"],
        "watch_events":sum(x["watch_events"] for x in report["results"]),
        "outcomes":[{"ticker":r["ticker"],"date":e["date"],"status":e["status"],
                     "horizons":[{"sessions":h["horizon_sessions"],
                                  "observed":h["observed_future_sessions"],
                                  "complete":h["complete"],
                                  "mfe_pct":h["observed_max_favorable_excursion_pct"],
                                  "mae_pct":h["observed_max_adverse_excursion_pct"]}
                                 for h in e["outcomes"]]}
                    for r in report["results"] for e in r["events"]],
        "trade_approved":False},ensure_ascii=False))
if __name__=="__main__":main()
