"""One support zone; its upper/lower limits are a 50:50 position plan.

This is NOT two independent supports and never changes an original stop.
"""
import json,math,statistics
from pathlib import Path
from entry_strategy_v58 import confirmed_pivots
from free_structural_v52 import atr14
from first_pullback_v55 import up,down,tick
from c3_dynamic_entry_v2 import resistance_levels

PROTOCOL_PATH=Path(__file__).resolve().parent.parent/'config/c3_zone_entry_v1_protocol.json'
P=json.loads(PROTOCOL_PATH.read_text())
MODELS=tuple(P['models'])+(P['diagnostic_control'],)


def buy_unit(price):
    f=P['fees'];return price*(1+f['buy'])*(1+f['slippage_each_side'])


def sale_unit(price):
    f=P['fees'];return price*(1-f['sell'])*(1-f['slippage_each_side'])


def allocation(plan,split=(.5,.5),capital=None):
    capital=capital or P['planned_capital_krw']
    if min(split)<0 or sum(split)>1+1e-12:raise ValueError('INVALID_PLANNED_ALLOCATION')
    limits=[plan['high'],plan['low']]
    q=[math.floor(capital*w/buy_unit(p)) for w,p in zip(split,limits)]
    legs=[dict(leg=i+1,limit=price,budget_krw=capital*split[i],quantity=q[i],gross_krw=q[i]*price,costed_krw=q[i]*buy_unit(price)) for i,price in enumerate(limits)]
    spent=sum(x['costed_krw'] for x in legs);qty=sum(q);gross=sum(x['gross_krw'] for x in legs)
    risk=spent-qty*sale_unit(plan['stop'])
    r1=plan.get('resistance');r2=plan.get('resistance2')
    rr=lambda r:(qty*sale_unit(r)-spent)/risk if r is not None and risk>0 and qty else None
    first=legs[0];rfirst=first['costed_krw']-first['quantity']*sale_unit(plan['stop'])
    return dict(capital_krw=capital,legs=legs,quantity=qty,costed_krw=spent,gross_krw=gross,cash_unspent_krw=capital-spent,
        weighted_average_price=gross/qty if qty else None,full_stop_loss_krw=risk,full_plan_risk_pct=100*risk/capital,
        first_only_stop_loss_krw=rfirst,first_only_plan_risk_pct=100*rfirst/capital,
        first_only_net_r1_rr=(first['quantity']*sale_unit(r1)-first['costed_krw'])/rfirst if r1 is not None and rfirst>0 and first['quantity'] else None,
        full_fill_net_r1_rr=rr(r1),full_fill_net_r2_rr=rr(r2),actual_fill_verified=False)


def zone_plan(bars,ticker='SYNTHETIC'):
    if len(bars)<65:return None,['INSUFFICIENT_CONTIGUOUS_HISTORY']
    pivots=confirmed_pivots(bars,lookback=P['pivot_lookback'])
    if not pivots:return None,['NO_UNBROKEN_CONFIRMED_PIVOT']
    i,support=pivots[-1];known=i+2;a=atr14(bars);confirmation_atr=atr14(bars[:known+1]);close=bars[-1]['close']
    if not a or not confirmation_atr:return None,['ATR_UNAVAILABLE']
    low=up(support+P['zone_lower_atr']*a);high=down(min(close,support+P['zone_upper_atr']*a))
    stop=down(support-P['stop_buffer_confirmation_atr']*confirmation_atr)
    if not stop or not low or not high or not 0<stop<low<high<=close:return None,['NO_TWO_DISTINCT_LIMITS_ABOVE_STRUCTURAL_STOP']
    res=resistance_levels(bars,max(close,high),a)
    p=dict(ticker=ticker,decision_date=bars[-1]['date'],method='ONE_SUPPORT_ZONE_UPPER_LOWER',reference_close=close,
        low=low,high=high,stop=stop,resistance=res[0]['price'] if res else None,resistance2=res[1]['price'] if len(res)>1 else None,
        support=support,support_date=bars[i]['date'],known_on=bars[known]['date'],atr=a,confirmation_atr=confirmation_atr,
        segment=bars[-1].get('segment',0),zone_width_pct=100*(high-low)/close,zone_width_atr=(high-low)/a,
        zone_width_ticks=(high-low)/tick(high),entry_distance_pct=100*(close-high)/close,entry_distance_atr=(close-high)/a,
        ma20=statistics.mean(b['close'] for b in bars[-20:]),resistance_evidence=res,original_stop_modified=False,
        lower_is_same_zone_not_independent_support=True,validity_sessions=[1,2,3],orders_enabled=False,buy_approved=False)
    p['ma20_in_zone']=low<=p['ma20']<=high;p['allocation']=allocation(p)
    reasons=[];alloc=p['allocation']
    if p['entry_distance_pct']>P['max_entry_distance_pct']:reasons.append('ZONE_TOO_FAR_PERCENT')
    if p['entry_distance_atr']>P['max_entry_distance_atr']:reasons.append('ZONE_TOO_FAR_ATR')
    if alloc['full_plan_risk_pct']>P['max_total_plan_risk_pct']:reasons.append('TOTAL_PLANNED_CAPITAL_RISK_TOO_HIGH')
    if alloc['full_fill_net_r1_rr'] is None:reasons.append('R1_NOT_CONFIRMED')
    elif alloc['full_fill_net_r1_rr']<P['min_full_fill_net_r1_rr']:reasons.append('INTEGRATED_NET_R1_RR_TOO_LOW')
    if alloc['first_only_net_r1_rr'] is not None and alloc['first_only_net_r1_rr']<=0:reasons.append('FIRST_ONLY_R1_NOT_NET_PROFITABLE')
    p['geometry_pass']=not reasons;p['reasons']=reasons
    return p,reasons
