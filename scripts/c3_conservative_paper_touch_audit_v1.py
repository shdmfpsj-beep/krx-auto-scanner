"""Research-only conservative bar-based virtual entry/stop audit.

A same-day entry and stop touch has unknown intraday order. Do not call it
a verified fill or a strategy return.
"""
import argparse,csv,json
from pathlib import Path

def audit(plan,prices):
    low,high,stop=(float(plan[k]) for k in ("watch_low","watch_high","structure_stop"))
    if not 0<stop<low<=high:
        raise ValueError("INVALID_PLAN_GEOMETRY")
    rows=sorted((day,bar) for (ticker,day),bar in prices.items()
                if ticker==plan["ticker"] and day>plan["registered_day"])
    horizon=int(plan["expires_after_sessions"])
    if horizon<1:
        raise ValueError("INVALID_HORIZON")
    observations=[]
    for day,b in rows[:horizon]:
        touched=b["low"]<=high and b["high"]>=low
        stop_touched=b["low"]<=stop
        observations.append(dict(date=day,watch_touched=touched,
                                 stop_touched=stop_touched,
                                 same_bar_order_ambiguous=touched and stop_touched,
                                 verified_fill=False))
    return dict(ticker=plan["ticker"],plan_id=plan["plan_id"],
                observed_sessions=len(observations),expected_sessions=horizon,
                watch_touch_days=sum(r["watch_touched"] for r in observations),
                same_bar_entry_stop_ambiguities=sum(r["same_bar_order_ambiguous"] for r in observations),
                observations=observations,verified_fills=0,
                strategy_return_pct=None,trade_approved=False,orders_enabled=False,
                note="OHLC_TOUCH_IS_NOT_EXECUTED_FILL")

def read_prices(path):
    with open(path,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    out={}
    for row in rows:
        key=(row["ticker"],row["date"])
        if key in out: raise ValueError("DUPLICATE_TICKER_DATE")
        b={k:float(row[k]) for k in ("open","high","low","close")}
        if min(b.values())<=0 or b["low"]>min(b["open"],b["close"]) or b["high"]<max(b["open"],b["close"]):
            raise ValueError("INVALID_PRICE_BAR")
        out[key]=b
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True);p.add_argument("--prices",required=True)
    p.add_argument("--output",required=True);p.add_argument("--markdown",required=True)
    a=p.parse_args()
    with open(a.plans,encoding="utf-8-sig",newline="") as f:
        plans=list(csv.DictReader(f))
    if len(plans)!=2 or len({p["ticker"] for p in plans})!=2:
        raise ValueError("EXPECTED_UNIQUE_TOP2")
    prices=read_prices(a.prices)
    results=[audit(plan,prices) for plan in plans]
    report=dict(schema="C3_CONSERVATIVE_PAPER_TOUCH_AUDIT_V1",results=results,
                price_certified=False,trade_approved=False,orders_enabled=False)
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["### 가상매매 진입·손절 충돌 검사 (체결 아님)",
           "| 종목 | 관찰일 | 매수구간 접촉 | 동일 일봉 매수·손절 충돌 |",
           "|---|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['ticker']} | {r['observed_sessions']}/{r['expected_sessions']} | {r['watch_touch_days']} | {r['same_bar_entry_stop_ambiguities']} |")
    lines.extend(["","> 일봉의 고가·저가만으로 매수·손절의 선후 관계를 알 수 없음. 실제 체결·수익률 주장 금지."])
    Path(a.markdown).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="results"},ensure_ascii=False))
if __name__=="__main__":main()
