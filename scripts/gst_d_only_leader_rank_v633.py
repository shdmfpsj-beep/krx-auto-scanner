"""C3 v6.33 frozen D-only GST-like leader rank. RESEARCH; NEVER orders.

D fields must come from a separately verified D completed KRX regular-only bar.
Weights chosen exploratorily after viewing 2026 data; NOT validated forecasts.
"""
import numpy as np
import pandas as pd

SCHEMA="C3_V633_D_ONLY_GST_RANK_READ_ONLY"
RANKS=("V632_BASE","LOW_STRUCT_RISK","CONFIRMED_RS","MONEY_FLOW",
       "BALANCED_LEADER","MINIMIZED_OVERHEAT")
REQ=("asof","ticker","model","signal_score","riskD_pct","ret5","rv20",
     "breakout_pct","rs5","rs20","turnover_accel","raw_turnover_bil")

def score_D(candidates):
    """Only REQ columns affect score; D+1 onward changes cannot alter rank."""
    missing=set(REQ)-set(candidates.columns)
    if missing:raise ValueError("MISSING_D_FEATURES:"+",".join(sorted(missing)))
    if candidates.empty:raise ValueError("EMPTY_UNIVERSE")
    x=candidates.copy()
    for n in REQ[3:]:x[n]=pd.to_numeric(x[n],errors="coerce")
    if not np.isfinite(x[list(REQ[3:])].to_numpy(float)).all():
        raise ValueError("NONFINITE_D_FEATURE")
    if (x.riskD_pct<=0).any() or (x.raw_turnover_bil<=0).any() or (x.turnover_accel<0).any():
        raise ValueError("INVALID_D_FEATURE")
    if x.duplicated(["model","asof","ticker"]).any():raise ValueError("DUPLICATE_STOCK_D_SIGNAL")
    x["V632_BASE"]=x.signal_score
    x["LOW_STRUCT_RISK"]=-x.riskD_pct
    x["CONFIRMED_RS"]=x.rs5+.35*x.rs20+.3*x.breakout_pct-.65*x.riskD_pct
    x["MONEY_FLOW"]=3*x.turnover_accel.clip(0,5)+1.3*x.rv20.clip(0,4)+.8*np.log1p(x.raw_turnover_bil)-.45*x.riskD_pct
    x["BALANCED_LEADER"]=.5*x.rs5+.2*x.rs20+1.8*x.turnover_accel.clip(0,4)+.5*np.log1p(x.raw_turnover_bil)+.3*x.breakout_pct-.9*x.riskD_pct
    x["MINIMIZED_OVERHEAT"]=.15*x.rs5+.4*x.rv20.clip(0,3)+.65*x.breakout_pct-1.2*x.riskD_pct-.25*np.maximum(0,x.ret5-8)**2
    return x

def select_D_once(scored,rank):
    if rank not in RANKS:raise ValueError("UNDECLARED_RANK_MODEL")
    if rank not in scored:raise ValueError("NO_FROZEN_RANK")
    return scored.sort_values(["model","asof",rank,"ticker"],
           ascending=[True,True,False,True]).drop_duplicates(["model","asof"]).copy()

def research_output_gate():
    return dict(schema=SCHEMA,regular_only_source_verified=False,
       point_in_time_issuer_and_corporate_actions_verified=False,
       broker_c3_cash_and_order_fill_verified=False,
       verified_overhead_net_2R=False,final_stock_score_80_verified=False,
       trade_approved=False,orders_enabled=False)
