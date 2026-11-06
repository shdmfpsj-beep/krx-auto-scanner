"""Research-only impact of observed close-provider disagreement on frozen TOP2 levels."""
import argparse,csv,json
from pathlib import Path

def assess(plans,diagnostic):
    with open(plans,encoding="utf-8-sig",newline="") as f:
        items=list(csv.DictReader(f))
    groups=diagnostic["gap_summary"]
    output=[]
    for plan in items:
        ticker=plan["ticker"]
        if ticker not in groups: raise ValueError("MISSING_PROVIDER_GAP:"+ticker)
        close=float(plan["source_close"])
        stop=float(plan["structure_stop"])
        watch_low=float(plan["watch_low"])
        watch_high=float(plan["watch_high"])
        if not (0<stop<watch_low<=watch_high and close>0):raise ValueError("INVALID_FROZEN_LEVELS:"+ticker)
        gap=groups[ticker]
        max_gap=gap["max_abs_gap_pct"]
        mean_gap=gap["mean_abs_gap_pct"]
        stop_distance=(close-stop)/close*100
        watch_width=(watch_high-watch_low)/close*100
        output.append({"ticker":ticker,"name":plan["name"],
                       "source_close":close,"structure_stop":stop,
                       "close_to_stop_pct":round(stop_distance,4),
                       "watch_band_width_pct":round(watch_width,4),
                       "mean_provider_close_gap_pct":mean_gap,
                       "max_provider_close_gap_pct":max_gap,
                       "gap_exceeds_watch_band":max_gap>=watch_width,
                       "gap_exceeds_10pct_of_stop_distance":max_gap>=0.1*stop_distance,
                       "entry_price_certified":False,"stop_price_certified":False,
                       "trade_approved":False})
    return {"schema":"C3_TOP2_PROVIDER_GAP_ENTRY_IMPACT_V1",
            "method":"PROVISIONAL_RELATIVE_SCALE_ONLY_NOT_CAUSAL",
            "regular_only_certified":False,"trade_approved":False,"orders_enabled":False,
            "results":output}
def markdown_table(report):
    lines=["### TOP2 가격 공급원 차이와 매수·손절 구조 (연구용)",
           "| 종목 | 손절 거리 | 관찰구간 폭 | 최대 종가 차이 | 손절 거리 10% 초과 |",
           "|---|---:|---:|---:|---|"]
    for row in report["results"]:
        lines.append("| {} | {:.3f}% | {:.3f}% | {:.3f}% | {} |".format(
            row["name"],row["close_to_stop_pct"],row["watch_band_width_pct"],
            row["max_provider_close_gap_pct"],"예" if row["gap_exceeds_10pct_of_stop_distance"] else "아니오"))
    lines.append("")
    lines.append("> 비교는 가격 기준의 민감도 분석이며 체결·손익 검증이 아닙니다. CASH / 주문 비활성.")
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True);p.add_argument("--diagnostic",required=True);p.add_argument("--output",required=True);p.add_argument("--markdown")
    a=p.parse_args()
    result=assess(a.plans,json.loads(Path(a.diagnostic).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if a.markdown: Path(a.markdown).write_text(markdown_table(result),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
