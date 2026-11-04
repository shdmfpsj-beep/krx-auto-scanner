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
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plans",required=True);p.add_argument("--diagnostic",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    result=assess(a.plans,json.loads(Path(a.diagnostic).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
