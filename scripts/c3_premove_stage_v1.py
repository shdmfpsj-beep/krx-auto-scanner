"""Frozen Work price-stage definitions; observation only, never trade approval."""
from collections import Counter
import numpy as np
import pandas as pd

def indicator_frame(bars):
    """Wilder RSI14; slow stochastic 14/3/3, both explicitly defined."""
    b = bars.copy().reset_index(drop=True)
    required = ['Date', 'Open', 'High', 'Low', 'Close']
    if not set(required).issubset(b):
        raise ValueError('OHLC_COLUMNS_MISSING')
    if b.Date.duplicated().any() or not b.Date.is_monotonic_increasing:
        raise ValueError('DATES_NOT_UNIQUE_AND_ORDERED')
    a = b[['Open', 'High', 'Low', 'Close']].to_numpy(float)
    if (not np.isfinite(a).all() or (a <= 0).any()
            or (b.Low > b[['Open', 'Close']].min(axis=1)).any()
            or (b.High < b[['Open', 'Close']].max(axis=1)).any()):
        raise ValueError('INVALID_OHLC')
    values = b.Close.to_numpy(float)
    rsi = np.full(len(b), np.nan)
    if len(b) >= 15:
        delta = np.diff(values)
        gains, losses = np.maximum(delta, 0), np.maximum(-delta, 0)
        gain, loss = float(gains[:14].mean()), float(losses[:14].mean())
        for i in range(14, len(b)):
            if i > 14:
                gain = (13 * gain + gains[i-1]) / 14
                loss = (13 * loss + losses[i-1]) / 14
            rsi[i] = 50 if gain == loss == 0 else 100 if loss == 0 else 100-100/(1+gain/loss)
    b['rsi14'] = rsi
    low = b.Low.rolling(14, min_periods=14).min()
    high = b.High.rolling(14, min_periods=14).max()
    width = high-low
    # An exactly flat fourteen-session range is undefined, not an invented 0/50.
    b['fast_k'] = 100*(b.Close-low)/width.where(width > 0)
    b['slow_k'] = b.fast_k.rolling(3, min_periods=3).mean()
    b['slow_d'] = b.slow_k.rolling(3, min_periods=3).mean()
    prev = b.Close.shift(1)
    tr = pd.concat([b.High-b.Low, (b.High-prev).abs(), (b.Low-prev).abs()], axis=1).max(axis=1)
    # Same simple fourteen-session TR average as the existing structural model.
    b['atr14'] = tr.rolling(14, min_periods=14).mean()
    for n in [5, 20, 60]:
        b[f'ma{n}'] = b.Close.rolling(n, min_periods=n).mean()
    for n in [5, 20]:
        b[f'ret{n}'] = 100*b.Close.pct_change(n, fill_method=None)
    return b

def confirmed_floor(b):
    """A pivot only exists after both following sessions have completed."""
    n = len(b)
    for i in range(n-3, max(1, n-16)-1, -1):
        window = b.Low.iloc[i-2:i+3]
        low = float(b.Low.iloc[i])
        # One strict neighbour avoids declaring every flat day a new pivot.
        if len(window) == 5 and low == float(window.min()) and (window > low).any():
            if float(b.Low.iloc[i+1:].min()) < low:
                continue
            return dict(pivot_date=b.Date.iloc[i], confirmed_date=b.Date.iloc[i+2],
                        low=low, age_sessions=n-1-i)
    return None

def classify_contextual(bars,asof):
    b=indicator_frame(bars)
    if len(b)<120 or b.Date.iloc[-1]!=asof or (b.Date>asof).any():raise ValueError('CONTEXTUAL_PRICE_PREFIX_INVALID')
    x=b.iloc[-1];old=b.iloc[-4];atr=float(x.atr14)
    if not np.isfinite(atr) or atr<=0:raise ValueError('UNKNOWN_ATR')
    m={k:float(x[k]) if np.isfinite(x[k]) else None for k in ['Close','atr14','ma5','ma20','ma60','ret5','ret20','rsi14','slow_k','slow_d']}
    m.update(rsi_change3=float(x.rsi14-old.rsi14),k_change3=float(x.slow_k-old.slow_k),
        above_ma20_atr=(float(x.Close)-float(x.ma20))/atr,
        rebound_low20_pct=100*(float(x.Close)/float(b.Low.tail(20).min())-1),
        drawdown_high60_pct=100*(float(x.Close)/float(b.High.tail(60).max())-1))
    for n in [60,120,252]:m['ret'+str(n)]=100*(float(x.Close)/float(b.Close.iloc[-1-n])-1) if len(b)>n else None
    width=float(b.High.tail(10).max()-b.Low.tail(10).min())
    prior=float(b.High.iloc[-30:-10].max()-b.Low.iloc[-30:-10].min())
    m['range10_previous20']=width/prior if prior>0 else None
    m['low5_holds_previous5']=bool(b.Low.tail(5).min()>=b.Low.iloc[-10:-5].min())
    floor=confirmed_floor(b);m['from_floor_atr']=(float(x.Close)-floor['low'])/atr if floor else None
    known=all(m[k] is not None and np.isfinite(m[k]) for k in ['rsi14','slow_k','slow_d','rsi_change3','k_change3'])
    weakening=known and m['rsi_change3']<0 and m['k_change3']<0 and m['slow_k']<m['slow_d']
    up=known and m['rsi_change3']>0 and m['k_change3']>0 and m['slow_k']>=m['slow_d'] and m['Close']>=m['ma5']
    compressed=(m['range10_previous20'] is not None and m['range10_previous20']<=.85
        and abs(m['ret5'])<=6 and m['low5_holds_previous5'])
    mature=(m['ret60'] is not None and m['ret60']>35 and m['drawdown_high60_pct']>=-10 and m['Close']>m['ma60'])
    stretched=m['above_ma20_atr']>2 or m['rebound_low20_pct']>25
    progressed=m['from_floor_atr'] is not None and m['from_floor_atr']>3
    newlow=bool(float(x.Low)<float(b.Low.iloc[-20:-1].min()))
    if not known:track='INDICATOR_UNCONFIRMED'
    elif mature:track='MATURE_RISE_NEAR_HIGHS'
    elif stretched or progressed:track='LOCAL_MOVE_PROGRESSING'
    elif floor is None or newlow:track='FLOOR_UNCONFIRMED'
    elif weakening:track='WEAKENING_PULLBACK'
    elif up:track='EARLY_LAUNCH'
    elif compressed:track='PRE_BREAKOUT_BASE'
    else:track='STABILIZING_WATCH'
    return dict(track=track,research_stage_pass=track in ['PRE_BREAKOUT_BASE','EARLY_LAUNCH'],metrics=m,floor=floor,
        momentum_up=bool(up),momentum_down=bool(weakening),base_compression=bool(compressed),
        single_short_return_not_a_veto=True,profitability_proven=False)

def valid_price_tail(frame,asof,calendar,min_sessions=120):
    """Retain the most recent unbroken *valid* prefix suffix through asof.

    A bad recent row cannot disappear from the middle of the indicator input:
    its entire prefix is quarantined, and the suffix must still have120 sessions.
    """
    b=frame.copy().reset_index(drop=True)
    if not set(['Date','Open','High','Low','Close']).issubset(b):raise ValueError('MISSING_OHLC_COLUMNS')
    dates=b.Date.astype(str).tolist()
    if not dates or dates!=sorted(dates) or len(set(dates))!=len(dates):raise ValueError('DATES_NOT_ORDERED_UNIQUE')
    if dates[-1]!=asof or any(d>asof for d in dates):raise ValueError('WRONG_ASOF_OR_FUTURE_PRICE')
    cal=list(calendar)
    if not cal or cal!=sorted(set(cal)) or asof not in cal:raise ValueError('INVALID_SESSION_CALENDAR')
    available=[d for d in cal if dates[0]<=d<=asof]
    if any(d not in cal for d in dates):raise ValueError('PRICE_DATE_OUTSIDE_CALENDAR')
    arr=b[['Open','High','Low','Close']].to_numpy(float)
    reasons={}
    for i,row in enumerate(arr):
        why=[]
        if not np.isfinite(row).all():why.append('NONFINITE_OHLC')
        elif (row<=0).any():why.append('NONPOSITIVE_OHLC')
        else:
            o,h,l,c=row
            if l>min(o,c) or h<max(o,c) or l>h:why.append('OHLC_INCONSISTENCY')
        if 'Volume' in b:
            v=float(b.Volume.iloc[i])
            if not np.isfinite(v) or v<0:why.append('INVALID_VOLUME')
        if why:reasons[dates[i]]=why
    missing=[d for d in available if d not in set(dates)]
    cut=max(list(reasons)+missing) if reasons or missing else None
    kept=b[b.Date>cut].copy().reset_index(drop=True) if cut else b.copy()
    expected=[d for d in available if cut is None or d>cut]
    audit=dict(price_asof=asof,original_rows=len(b),invalid_rows=len(reasons),
               invalid_reason_counts=dict(Counter(x for v in reasons.values() for x in v)),
               missing_calendar_sessions=missing,last_quarantined_date=cut,
               quarantined_prefix_rows=len(b)-len(kept),retained_contiguous_rows=len(kept),
               retained_start=kept.Date.iloc[0] if len(kept) else None,
               prices_repaired=False,interior_rows_dropped=False)
    if kept.Date.tolist()!=expected:raise ValueError('CONTIGUOUS_SUFFIX_CALENDAR_MISMATCH')
    if len(kept)<min_sessions:
        return None,dict(audit,status='INSUFFICIENT_VALID_CONTIGUOUS_HISTORY')
    return kept,dict(audit,status='VALID_CONTIGUOUS_TAIL')

STAGE_POLICY={'schema': 'C3_CONTEXTUAL_PREMOVE_V2', 'minimum_contiguous_history': 120, 'maximum_above_ma20_atr': 2.0, 'maximum_low20_rebound_pct': 25.0, 'maximum_from_confirmed_floor_atr': 3.0, 'base_range10_previous20_max': 0.85, 'base_abs_ret5_pct_max': 6.0, 'mature_return60_pct': 35.0, 'mature_drawdown60_pct': -10.0}

WORK_ORIGIN_SHA256={'early_phase.py': 'f5eb92da768a80cd69a4e5d6ae0cfb9c7e513ac8d750adf5f149eabf417415c3', 'contextual_phase.py': '51d220f4eb93315fc3517d0e93ec2c15d4ca233d2343a12664c4a976823a8375', 'price_tail_and_flow.py': 'aaa45b0ebc476ca3af7dc8ce7203ab10876436845900696c3b995d4d025c244e'}
