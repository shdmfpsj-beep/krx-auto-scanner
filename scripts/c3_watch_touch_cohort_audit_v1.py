"""Aggregate watch touch events by safety class and forward observation completeness.

No inferential edge, simulated fill, or profit claim is permitted.
"""
import argparse,json
from pathlib import Path

def summarize(report):
    if report.get("schema")!="C3_WATCH_TOUCH_FORWARD_OUTCOMES_V1":
        raise ValueError("UNEXPECTED_SOURCE_SCHEMA")
    counts={}
    horizons={}
    clustered_plans=0
    clustered_events=0
    for plan in report["results"]:
        dates=[event["date"] for event in plan["events"]]
        if len(dates)!=len(set(dates)):
            raise ValueError("DUPLICATE_TOUCH_DATE")
        if len(dates)>1:
            clustered_plans+=1
            clustered_events+=len(dates)
        for event in plan["events"]:
            status=event["status"]
            counts[status]=counts.get(status,0)+1
            if event.get("verified_fill") is not False:
                raise ValueError("UNEXPECTED_VERIFIED_FILL")
            for item in event["outcomes"]:
                n=item["horizon_sessions"]
                s=horizons.setdefault(str(n),dict(complete=0,pending=0,stop_touch_events=0,target_touch_events=0))
                if item["complete"]:
                    s["complete"]+=1
                    s["stop_touch_events"]+=item["future_stop_touch_days"]>0
                    s["target_touch_events"]+=item["future_target_touch_days"]>0
                else:
                    s["pending"]+=1
    return dict(schema="C3_WATCH_TOUCH_COHORT_AUDIT_V1",events=sum(counts.values()),
                status_counts=counts,horizons=horizons,
                clustered_plans=clustered_plans,clustered_events=clustered_events,
                independent_event_sample_size_verified=False,
                causal_edge_established=False,verified_fills=0,
                strategy_profitability_verified=False,trade_approved=False,orders_enabled=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True);p.add_argument("--output",required=True);p.add_argument("--markdown",required=True)
    a=p.parse_args()
    result=summarize(json.loads(Path(a.source).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["### 매수구간 접촉 표본 요약 (가상 체결 아님)",
           f"- 전체 접촉 관찰: {result['events']}건"]
    lines.append("- 동일 계획의 반복 접촉: {}건 / {}개 계획 (독립 표본 아님)".format(result["clustered_events"],result["clustered_plans"]))
    for status,n in sorted(result["status_counts"].items()):
        lines.append(f"- {status}: {n}건")
    lines.extend(["","| 후속 관찰 | 완료 표본 | 미완료 | 완료 표본 내 손절 접촉 | 완료 표본 내 목표 접촉 |",
                  "|---|---:|---:|---:|---:|"])
    for horizon,item in sorted(result["horizons"].items(),key=lambda x:int(x[0])):
        lines.append(f"| {horizon}거래일 | {item['complete']} | {item['pending']} | {item['stop_touch_events']} | {item['target_touch_events']} |")
    lines.extend(["","> 후속 기간이 미완료인 표본은 성과 계산에서 제외. 접촉 사례는 실제 체결이 아니며, 표본이 작아 우위·수익성을 주장하지 않음."])
    Path(a.markdown).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
