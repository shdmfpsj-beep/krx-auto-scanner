"""Research-only risk/reward geometry for frozen TOP2 watch ranges.

No execution simulation, no price provenance certification, no recommendation.
"""
import argparse,csv,json,math
from pathlib import Path

def evaluate(plan):
    stop=float(plan["structure_stop"])
    low=float(plan["watch_low"])
    high=float(plan["watch_high"])
    first=float(plan["target1"])
    second=float(plan["target2"])
    if not all(math.isfinite(x) and x>0 for x in (stop,low,high,first,second)):
        raise ValueError("INVALID_NONFINITE_OR_NONPOSITIVE_PRICE")
    if not stop<low<=high<first<=second:
        raise ValueError("INVALID_STOP_WATCH_TARGET_ORDER")
    def geometry(entry,target):
        risk=entry-stop
        reward=target-entry
        return dict(risk_pct=round(100*risk/entry,3),
                    reward_pct=round(100*reward/entry,3),
                    reward_to_risk=round(reward/risk,3))
    conservative=geometry(high,first)
    favorable=geometry(low,first)
    return dict(plan_id=plan["plan_id"],ticker=plan["ticker"],
                watch_low=low,watch_high=high,structure_stop=stop,
                first_resistance=first,second_target=second,
                conservative_at_watch_high=conservative,
                favorable_at_watch_low=favorable,
                second_target_at_watch_high=geometry(high,second),
                first_resistance_is_unverified_target=True,
                price_certified=False,trade_approved=False,orders_enabled=False)

def build(plans):
    if len(plans)!=2 or len({p["ticker"] for p in plans})!=2:
        raise ValueError("EXPECTED_UNIQUE_TOP2")
    return dict(schema="C3_TOP2_WATCH_RISK_REWARD_V1",
                data_basis="FROZEN_RESEARCH_PLAN_NOT_LIVE_PRICE",
                price_certified=False,trade_approved=False,orders_enabled=False,
                results=[evaluate(p) for p in plans])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--markdown",required=True)
    a=p.parse_args()
    with open(a.plans,encoding="utf-8-sig",newline="") as f:
        report=build(list(csv.DictReader(f)))
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["### TOP2 구조손절 대비 첫 저항 손익비 (연구 계획값)",
           "| 종목 | 관찰 매수가 | 구조손절 | 첫 저항(미검증) | 최악 진입 손절폭 | 첫 저항 손익비 |",
           "|---|---|---:|---:|---:|---:|"]
    for r in report["results"]:
        v=r["conservative_at_watch_high"]
        lines.append("| {} | {:,.0f}~{:,.0f} | {:,.0f} | {:,.0f} | {:.2f}% | {:.2f}배 |".format(
            r["ticker"],r["watch_low"],r["watch_high"],r["structure_stop"],r["first_resistance"],
            v["risk_pct"],v["reward_to_risk"]))
    lines.extend(["","> 첫 저항은 과거 연구 계획의 목표값이며 실제 차트 저항 검증 전입니다. 상단 매수가 기준 보수적 손익비로, 체결·수익·매수 승인을 뜻하지 않습니다."])
    Path(a.markdown).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"schema":report["schema"],"plans":len(report["results"]),"trade_approved":False}))
if __name__=="__main__":main()
