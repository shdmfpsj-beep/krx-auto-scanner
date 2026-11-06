"""Research-only ICT-style sequence: sweep -> displaced close above frozen level -> later FVG retest.

Only completed daily OHLC bars. No fill assumptions or future pivot labels.
The break level is frozen on the sweep date, never recomputed using later bars.
"""
from c3_ict_observable_features_v1 import features

def detect(bars,lookback=10,max_wait=10,min_body_fraction=0.55,max_fvg_age=10):
    if max_wait<1 or max_fvg_age<1 or not 0<min_body_fraction<=1:
        raise ValueError("INVALID_PARAMETERS")
    base=features(bars,lookback)
    out=[]
    pending=None
    fvg=None
    for i,(b,x) in enumerate(zip(bars,base)):
        if pending and i-pending["index"]>max_wait:
            pending=None
        # Old unfilled gaps are not perpetual valid entry signals.
        if fvg and i-fvg["index"]>max_fvg_age:
            fvg=None
        # Invalidate the bullish setup when a completed close loses the
        # original sweep low. Do not revive a stale FVG after invalidation.
        if fvg and b["close"]<fvg["sweep_low"]:
            fvg=None
        if pending and b["close"]<pending["sweep_low"]:
            pending=None
        if fvg and i>fvg["index"]:
            if b["low"]<=fvg["upper"] and b["high"]>=fvg["lower"]:
                out.append(dict(date=b["date"],event="FVG_RETEST_WATCH",
                                sweep_date=fvg["sweep_date"],
                                break_date=fvg["break_date"],
                                fvg_lower=fvg["lower"],fvg_upper=fvg["upper"],
                                sweep_invalidation_low=fvg["sweep_low"],
                                entry_verified=False,trade_approved=False))
                fvg=None
        if pending and i>pending["index"]:
            spread=b["high"]-b["low"]
            body=(b["close"]-b["open"])/spread if spread>0 else 0
            if b["close"]>pending["break_level"] and body>=min_body_fraction:
                out.append(dict(date=b["date"],event="DISPLACED_STRUCTURE_BREAK",
                                sweep_date=pending["date"],
                                frozen_break_level=pending["break_level"],
                                entry_verified=False,trade_approved=False))
                # A gap exists only when all 3 bars are completed.
                if i>=2 and b["low"]>bars[i-2]["high"]:
                    fvg=dict(index=i,lower=bars[i-2]["high"],upper=b["low"],
                             sweep_date=pending["date"],break_date=b["date"],
                             sweep_low=pending["sweep_low"])
                pending=None
        if x["sweep_reclaim"]:
            pending=dict(index=i,date=b["date"],break_level=x["prior_high"],sweep_low=b["low"])
    return out
