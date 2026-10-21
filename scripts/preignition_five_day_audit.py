#!/usr/bin/env python3
"""Research-only, point-in-time five-session stop/target outcome audit.

Each input CSV row represents a decision at signal-date close. Required:
ticker,signal_date,entry,stop,target, and f1_low/f1_high ... f5_low/f5_high.
The next session's open is NOT modeled; results are conditional on a
hypothetical signal-close fill and MUST NOT be reported as realized P&L.
If both levels touch on the same daily candle, classify AMBIGUOUS.
"""
import argparse,csv,math
from collections import Counter
from pathlib import Path

def num(row,key):
    try:
        x=float(row[key])
        return x if math.isfinite(x) else None
    except (KeyError,TypeError,ValueError):
        return None

def audit(row,horizon=5):
    entry,stop,target=(num(row,k) for k in ("entry","stop","target"))
    if any(v is None for v in (entry,stop,target)) or not (0<stop<entry<target):
        return "INVALID_LEVELS"
    for day in range(1,horizon+1):
        lo,hi=num(row,f"f{day}_low"),num(row,f"f{day}_high")
        if lo is None or hi is None or not 0<lo<=hi:
            return "INCOMPLETE_FORWARD_BARS"
        risk=lo<=stop
        reward=hi>=target
        if risk and reward: return "AMBIGUOUS_SAME_DAY"
        if risk: return "STOP_FIRST"
        if reward: return "TARGET_FIRST"
    return "NEITHER_WITHIN_5D"

def summarize(rows):
    counts=Counter(audit(r) for r in rows)
    completed=counts["STOP_FIRST"]+counts["TARGET_FIRST"]+counts["NEITHER_WITHIN_5D"]
    return {"total":len(rows),**dict(sorted(counts.items())),
            "unambiguous_complete":completed,
            "target_first_rate":round(counts["TARGET_FIRST"]/completed,5) if completed else "",
            "trade_approval":"NO"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("input_csv",type=Path)
    p.add_argument("--out",type=Path,default=Path("five_day_audit.csv"))
    a=p.parse_args()
    with a.input_csv.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    results=[{**r,"outcome":audit(r)} for r in rows]
    if not results: raise SystemExit("EMPTY_INPUT")
    with a.out.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]))
        w.writeheader();w.writerows(results)
    print(summarize(rows))
    print("RESEARCH_ONLY: signal-close hypothetical fill; fees/slippage unmodeled")

if __name__=="__main__":main()
