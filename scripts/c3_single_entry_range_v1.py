"""One continuous observation range; entry count and sizing remain user discretion.

The stop and confirmed resistances are frozen BEFORE risk intersection. The
intersection can discard prices but cannot change these structural anchors.
All limits are inherited research assumptions, never a BUY authorization.
"""
import json, math, statistics
from pathlib import Path
from free_structural_v52 import atr14
from first_pullback_v55 import up, down, tick
from entry_strategy_v58 import confirmed_pivots, breakout_retest
from c3_dynamic_entry_v2 import resistance_levels, retest_structure

PROTOCOL=json.loads((Path(__file__).resolve().parent.parent/'config/c3_single_entry_range_v1.json').read_text())

def factors():
    f=PROTOCOL['fees']
    return (1+f['buy'])*(1+f['slippage_each_side']),(1-f['sell'])*(1-f['slippage_each_side'])

def endpoint(entry,stop,r1,r2,close,atr):
    b,s=factors();loss=entry*b-stop*s
    return dict(price=entry,stop_risk_pct=100*(entry-stop)/entry,
        net_loss_pct=100*loss/(entry*b),net_r1_rr=(r1*s-entry*b)/loss if r1 is not None and loss>0 else None,
        net_r2_rr=(r2*s-entry*b)/loss if r2 is not None and loss>0 else None,
        distance_pct=100*(close-entry)/close,distance_atr=(close-entry)/atr)

def legal_ticks(low,high):
    p=up(low)
    while p<=high:
        yield p
        p=up(p+tick(p))

def active_resistances(bars,above,atr):
    """Re-use confirmed pivots, but reject levels already closed above.

    A historical high below the current close is not an overhead resistance.
    This is structural correctness, not moving a target to improve reward.
    All discarded pivots remain in diagnostics with their observed break.
    """
    discarded=[]
    active=resistance_levels(bars,above,atr,active_only=True,audit=discarded)
    return active,discarded

def risk_intersection(low,high,stop,r1,r2,close,atr):
    """Risk rises and RR falls monotonically with entry. Distance falls.

    Thus intersect the structural interval with an upper risk/RR cap and a
    lower distance cap. The explicit tick sweep is an independent audit.
    """
    if not all(math.isfinite(float(v)) for v in (low,high,stop,close,atr)) or not 0<stop<low<=high<=close or atr<=0:
        return dict(valid=False,reason='INVALID_STRUCTURAL_ORDER')
    if r1 is None or r1<=high:return dict(valid=False,reason='NEAREST_OVERHEAD_RESISTANCE_UNCONFIRMED_OR_INSIDE_RANGE')
    b,s=factors();k=PROTOCOL['min_net_r1_rr'];risk=PROTOCOL['max_stop_risk_pct']/100
    upper=min(high,stop/(1-risk),s*(r1+k*stop)/(b*(1+k)))
    lower=max(low,close*(1-PROTOCOL['max_distance_pct']/100),close-PROTOCOL['max_distance_atr']*atr)
    lo,hi=up(lower),down(upper)
    if lo>hi:return dict(valid=False,reason='NO_CONTINUOUS_STRUCTURAL_RISK_DISTANCE_INTERSECTION',
        risk_limited_upper=down(upper),distance_limited_lower=up(lower))
    if lo==hi:return dict(valid=False,reason='RANGE_COLLAPSES_TO_ONE_TICK')
    points=[endpoint(v,stop,r1,r2,close,atr) for v in (lo,up((lo+hi)/2),hi)]
    checked=0
    for p in legal_ticks(lo,hi):
        e=endpoint(p,stop,r1,r2,close,atr);checked+=1
        if e['stop_risk_pct']>PROTOCOL['max_stop_risk_pct']+1e-9 or e['net_r1_rr']<k-1e-9 or e['distance_pct']>PROTOCOL['max_distance_pct']+1e-9 or e['distance_atr']>PROTOCOL['max_distance_atr']+1e-9:
            raise ValueError('RANGE_CONTAINS_UNSAFE_TICK')
    return dict(valid=True,low=lo,high=hi,endpoints=dict(zip(('lower','middle','upper'),points)),
        ticks_checked=checked,all_legal_ticks_passed=True,min_net_r1_rr=points[-1]['net_r1_rr'],
        width_atr=(hi-lo)/atr,narrower_than_support_tolerance=(hi-lo)<PROTOCOL['support_band_atr']*atr,
        anchors_modified=False,structural_range=[low,high],risk_intersection_shrank_range=(lo!=low or hi!=high))

def _candidate(bars,method,anchor,invalid,known,evidence):
    close=bars[-1]['close'];a=atr14(bars)
    lo=up(anchor-PROTOCOL['support_band_atr']*a)
    hi=down(min(close,anchor+PROTOCOL['support_band_atr']*a))
    stop=down(invalid-PROTOCOL['stop_buffer_atr']*a)
    # Crucially search ABOVE the structural range, not above today's close:
    # an intervening resistance must not be silently skipped to inflate RR.
    levels,broken=active_resistances(bars,lo,a)
    r1=levels[0]['price'] if levels else None;r2=levels[1]['price'] if len(levels)>1 else None
    result=risk_intersection(lo,hi,stop,r1,r2,close,a)
    deep=hi<close-min(a,close*PROTOCOL['max_distance_pct']/100)
    state='ENTRY RANGE' if result['valid'] else 'WAIT_DEEP_PULLBACK' if deep else 'WATCH'
    return dict(method=method,asof=bars[-1]['date'],reference_close=close,atr14=a,support=anchor,
        structural_low=lo,structural_high=hi,stop=stop,r1=r1,r2=r2,resistance_evidence=levels,broken_resistances_excluded=broken,support_known_on=known,
        evidence=evidence,range=result,status=state,range_valid=result['valid'],
        validity_sessions=PROTOCOL['validity_sessions'],default_validity_sessions=1,
        cancel_conditions=['OPEN_BELOW_RANGE_OR_STOP','OPEN_AT_OR_ABOVE_R1','CLOSE_BREAKS_SUPPORT','TREND_LOST','RANGE_NOT_REACHED_BY_EXPIRY_PASS'],
        buy_approved=False)

def generate_ranges(bars):
    if len(bars)<80:return dict(plans=[],best=None,reason='INSUFFICIENT_CAUSAL_HISTORY')
    c=[b['close'] for b in bars];a=atr14(bars)
    ma=lambda n,j=0:statistics.mean(c[-n-j:len(c)-j if j else None])
    trend=c[-1]>ma(20)>ma(60) and ma(20)>ma(20,5)
    if not trend:return dict(plans=[],best=None,reason='TREND_NOT_CONFIRMED')
    plans=[]
    for i,p in reversed(confirmed_pivots(bars)):
        if i<len(bars)-PROTOCOL['pivot_lookback_sessions'] or p>c[-1]:continue
        after=bars[i+2:]
        if any(b['close']<p-.25*a for b in after):continue
        plans.append(_candidate(bars,'TREND_CONFIRMED_PIVOT',p,p,bars[i+2]['date'],dict(pivot_date=bars[i]['date'],confirmation_bars=2)))
        break
    # MA is used as a support only after an observed touch AND reclaim. A
    # moving average alone must never manufacture a structural invalidation.
    for n in (10,20,60):
        level=ma(n)
        if level>=c[-1] or level<=ma(n,5):continue
        touches=[]
        for i in range(len(bars)-10,len(bars)-1):
            local=statistics.mean(c[i-n+1:i+1]);b=bars[i]
            if b['low']<=local+.2*a and b['close']>=local-.25*a:touches.append(i)
        if not touches:continue
        i=touches[-1];recent=bars[i:]
        if c[-1]<=bars[i]['high'] or any(b['close']<level-.25*a for b in recent):continue
        invalid=min(b['low'] for b in recent)
        plans.append(_candidate(bars,'TREND_CONFIRMED_MA'+str(n),level,invalid,bars[-1]['date'],
            dict(touch_date=bars[i]['date'],reclaim_date=bars[-1]['date'],ma_period=n,observed_low=invalid)))
    legacy=breakout_retest(bars,a)
    if legacy:
        level=legacy['support_hint']
        for j in range(len(bars)-3,max(22,len(bars)-13)-1,-1):
            if max(b['high'] for b in bars[j-20:j])!=level or bars[j]['close']<=level:continue
            structure=retest_structure(bars,j,level,a)
            vol=bars[j]['volume']/statistics.mean(b['volume'] for b in bars[j-20:j])
            if structure['support_retained_on_closes'] and vol>=1.2:
                plans.append(_candidate(bars,'FIRST_PULLBACK_RETEST',level,structure['invalidation_low'],bars[-1]['date'],
                    dict(breakout_date=bars[j]['date'],breakout_volume_ratio=vol,post_breakout_structure=structure)))
            break
    valid=[p for p in plans if p['range_valid']]
    best=min(valid,key=lambda p:(p['range']['endpoints']['upper']['distance_atr'],-p['range']['min_net_r1_rr'],p['method'])) if valid else None
    return dict(plans=plans,best=best,reason=None if plans else 'NO_CONFIRMED_CURRENT_SUPPORT')

def single_scenario(plan,choice):
    if choice not in ('upper','middle','lower') or not plan['range_valid']:raise ValueError('VALID_INDEPENDENT_PRICE_SCENARIO_REQUIRED')
    price=plan['range']['endpoints'][choice]['price']
    # This function evaluates one hypothetical price choice independently.
    # It is not a user trade-count policy or an instruction to split orders.
    return dict(low=plan['range']['low'],high=price,stop=plan['stop'],resistance=plan['r1'],resistance2=plan['r2'],
        range_floor=plan['range']['low'],range_ceiling=plan['range']['high'],choice=choice)
