#!/usr/bin/env python3
"""C3 v6.34: diagnostic-only multiple-trials benchmark; NOT valid p-value/BUT no BUY.

Input is the PREVIOUSLY STUDIED local v6.33 research CSV with 200 random-D
candidate-selection account simulations. This module does NOT trade.
"""
import csv
import math
from pathlib import Path

EXIT="TRAIL7_TO12"
RANKS=frozenset({"V632_BASE","LOW_STRUCT_RISK","CONFIRMED_RS",
  "MONEY_FLOW","BALANCED_LEADER","MINIMIZED_OVERHEAT"})

def six_try_illustration(one_try_tail,trial_count=6):
    if not (isinstance(trial_count,int) and trial_count>=1 and
       isinstance(one_try_tail,(float,int)) and math.isfinite(one_try_tail)
       and 0<=one_try_tail<=1):
        raise ValueError("INVALID_ILLUSTRATION_INPUT")
    # INDEPENDENCE IS AN ASSUMPTION; real model ranks have correlated returns.
    return 1-(1-one_try_tail)**trial_count

def audit(rows,placebos,model="NEAR60_RISK8"):
    a=[r for r in rows if r["model"]==model and r["exit_mode"]==EXIT]
    b=[r for r in placebos if r["model"]==model and r["exit_mode"]==EXIT]
    if len(a)!=6 or {r["rank"] for r in a}!=RANKS:
        raise ValueError("MISSING_ALL_FROZEN_SIX_RANKS")
    if len(b)!=200 or len({r["seed"] for r in b})!=200:
        raise ValueError("MISSING_200_UNIQUE_FIXED_RANDOM_RUNS")
    best=max(a,key=lambda r:float(r["pct"]))
    bestval=float(best["pct"])
    ge=sum(float(r["pct"])>=bestval for r in b)
    p=ge/200
    return {"schema":"C3_V634_FAMILYWISE_EXPLORATORY_ONLY",
       "model":model,"best_rank":best["rank"],
       "best_history_paper_roi_pct":bestval,
       "retrospective_uniform_random_ge_best":ge,
       "number_placebos":200,"single_try_empirical_tail":p,
       "six_independent_draws_illustration":six_try_illustration(p),
       "true_corrected_pvalue_not_calculated":True,
       "after_20261023_independent_trades":0,
       "source_krx_regular_only_verified":False,
       "broker_fills_verified":False,
       "trade_approved":False,"orders_enabled":False}

def read_csv(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

if __name__=="__main__":
    import argparse,json
    p=argparse.ArgumentParser()
    p.add_argument("ranked_accounts_csv")
    p.add_argument("random_200_accounts_csv")
    v=p.parse_args()
    print(json.dumps(audit(read_csv(v.ranked_accounts_csv),
        read_csv(v.random_200_accounts_csv)),indent=2,ensure_ascii=False))
