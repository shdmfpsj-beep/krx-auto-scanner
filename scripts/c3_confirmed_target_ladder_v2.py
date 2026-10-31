"""As-of verified C3 1st/2nd overhead target levels, never synthetic profit targets.

For each requested 5-bar swing high, both later bars must already exist on
signal date and NO more recent high may have exceeded that price. Second
obstacle may require older history beyond the 120-bar display window.
"""
import math
from c3_stock_first_v4 import net_r

SCHEMA='C3_CONFIRMED_TARGET_LADDER_V2_RESEARCH_NO_ORDERS'

def historic_overhead(highs,dates,asof):
    if len(highs)!=len(dates) or len(highs)<7:raise ValueError('INVALID_DATED_HISTORY')
    if list(dates)!=sorted(dates) or len(set(dates))!=len(dates):
        raise ValueError('UNSORTED_OR_DUPLICATE_DATES')
    valid=[j for j,d in enumerate(dates) if str(d)<=str(asof)]
    if not valid:return []
    n=valid[-1]+1
    out=[]
    for j in range(2,n-2):
        v=float(highs[j]);w=[float(h) for h in highs[j-2:j+3]]
        if not math.isfinite(v) or v<=0:continue
        if (v==max(w) and any(q<v for q in w) and
                max(float(q) for q in highs[j+1:n])<=v):
            out.append(dict(level=int(v),pivot_date=str(dates[j]),
                            confirmed_at=str(dates[j+2])))
    return sorted(out,key=lambda x:(x['level'],x['pivot_date']))

def target_ladder(history,*,asof,close,entry_low,entry_high,stop,first_observed):
    b=history[history.date<=asof].sort_values('date').reset_index(drop=True)
    if b.empty or str(b.date.iloc[-1])!=str(asof):raise ValueError('MISSING_ASOF')
    if b.date.duplicated().any():raise ValueError('DUPLICATED_SOURCE_SESSION')
    close=float(close);low=float(entry_low);high=float(entry_high)
    stop=float(stop);first=float(first_observed)
    if not all(math.isfinite(x) for x in (close,low,high,stop,first)):
        raise ValueError('NONFINITE_PRICE')
    if not (0<stop<low<=high<close<first):
        raise ValueError('INVALID_STOP_ENTRY_TARGET1_ORDER')
    if close!=float(b.close.iloc[-1]):
        raise ValueError('SOURCE_CLOSE_MISMATCH')
    pivots=historic_overhead(b.high.to_list(),b.date.to_list(),asof)
    t1=next((x for x in pivots if x['level']==first),None)
    if not t1:raise ValueError('FIRST_OBSTACLE_NOT_CONFIRMED_UNBROKEN')
    t2=next((x for x in pivots if x['level']>first),None)
    calc=lambda t:dict(price_krw=int(t['level']),pivot_date=t['pivot_date'],
            confirmed_at=t['confirmed_at'],
            gross_upside_pct=round(100*(t['level']/high-1),2),
            modeled_net_r=round(net_r(high,stop,t['level']),2))
    return dict(schema=SCHEMA,asof=asof,
        stop_krw=int(stop),entry_low_krw=int(low),entry_high_krw=int(high),
        first_target=calc(t1),second_target=calc(t2) if t2 else None,
        second_target_status=('CONFIRMED_HISTORICAL_PIVOT' if t2 else 'NO_OBSERVED_TARGET2'),
        nominal_stop_distance_pct=round(100*(high-stop)/high,2),
        targets_are_historical_resistance_not_guaranteed=True,
        source_regular_only_certified=False,
        buy_approved=False,orders_enabled=False)
