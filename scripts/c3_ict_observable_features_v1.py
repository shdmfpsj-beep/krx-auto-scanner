"""ICT-inspired *observable* daily-bar features, research only.

No assertion about institutional orders or hidden liquidity. All signals use
bars available on or before the signal date; no future pivot confirmation.
"""
def features(bars, lookback=10):
    if lookback<3:
        raise ValueError("LOOKBACK_TOO_SHORT")
    out=[]
    for i,b in enumerate(bars):
        if i<lookback:
            out.append(dict(date=b["date"],sweep_reclaim=False,
                            bullish_structure_break=False,bullish_fvg=False))
            continue
        prior=bars[i-lookback:i]
        prior_low=min(x["low"] for x in prior)
        prior_high=max(x["high"] for x in prior)
        # Prior lows breached intraday and reclaimed by the close.
        sweep=b["low"]<prior_low and b["close"]>prior_low
        # Current close breaks previous known high.
        break_up=b["close"]>prior_high
        # Three-candle gap: current low exceeds high two sessions ago.
        fvg=b["low"]>bars[i-2]["high"]
        out.append(dict(date=b["date"],sweep_reclaim=sweep,
                        bullish_structure_break=break_up,bullish_fvg=fvg,
                        prior_low=prior_low,prior_high=prior_high))
    return out
