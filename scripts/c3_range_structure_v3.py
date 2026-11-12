"""Evidence-based range practicality and stop review, without moving anchors.

This layer annotates PR106 plans. The original range/stop/targets and risk
limits stay frozen. Confirmed below means confirmed in completed daily price
structure, NOT certified regular-session data or a live BUY permission.
"""
import copy,statistics
from collections import Counter
from entry_strategy_v58 import confirmed_pivots
from first_pullback_v55 import down,tick
from c3_single_entry_range_v1 import PROTOCOL,endpoint,legal_ticks

def variation(bars):
    result={}
    for n in (5,10,20):
        tail=bars[-n:];start=len(bars)-n
        tr=[max(b['high']-b['low'],abs(b['high']-bars[start+i-1]['close']),abs(b['low']-bars[start+i-1]['close'])) for i,b in enumerate(tail)]
        wick=[min(b['open'],b['close'])-b['low'] for b in tail]
        pull=[max(0,bars[start+i-1]['high']-b['low']) for i,b in enumerate(tail)]
        result[str(n)]=dict(median_true_range=statistics.median(tr),median_lower_wick=statistics.median(wick),
            lower_wick_75pct=sorted(wick)[int(.75*(n-1))],median_one_session_pullback=statistics.median(pull),
            maximum_down_gap=max(max(0,bars[start+i-1]['close']-b['open']) for i,b in enumerate(tail)))
    return result

def volume_proxy(bars,atr):
    """Daily typical-price buckets; explicitly NOT traded volume-at-price."""
    bins=Counter();step=atr if atr>0 else 1
    for b in bars[-20:]:bins[int(((b['high']+b['low']+b['close'])/3)//step)]+=b['volume']
    return dict(basis='DAILY_TYPICAL_PRICE_VOLUME_PROXY_NOT_INTRADAY_VOLUME_AT_PRICE',
        top_buckets=[dict(low=k*step,high=(k+1)*step,assigned_daily_volume=v) for k,v in bins.most_common(3)],
        genuine_volume_at_price_verified=False,used_to_invent_support=False)

def invalidation(plan):
    ev=plan.get('evidence') or {}
    if 'observed_low' in ev:return ev['observed_low']
    if 'post_breakout_structure' in ev:return ev['post_breakout_structure']['invalidation_low']
    if plan['method']=='TREND_CONFIRMED_PIVOT':return plan['support']
    return None

def stop_review(bars,plan):
    a=plan['atr14'];invalid=invalidation(plan);v=variation(bars)
    if invalid is None:return dict(status='STOP_UNVERIFIED',research_eligible=False,reason='ORIGINAL_INVALIDATION_LOW_NOT_PROVEN')
    expected=down(invalid-PROTOCOL['stop_buffer_atr']*a)
    if expected!=plan['stop']:raise ValueError('STRUCTURAL_STOP_DIFFERS_FROM_ORIGINAL_CALCULATION')
    tolerance=PROTOCOL['stop_buffer_atr']*a
    # Earlier tests invalidated by a later completed close cannot be counted
    # as independent confirmations of the current support.
    last_break=max((i for i,b in enumerate(bars[:-1]) if b['close']<invalid-tolerance),default=-1)
    active_start=max(len(bars)-20,last_break+1)
    contacts=[]
    for i in range(active_start,len(bars)):
        b=bars[i]
        if abs(b['low']-invalid)<=tolerance and b['close']>=invalid:
            if not contacts or i-contacts[-1]>=2:contacts.append(i)
    pivots=[];deeper=[]
    for i,p in confirmed_pivots(bars):
        if i<len(bars)-35:continue
        if any(b['close']<p-tolerance for b in bars[i+2:]):continue
        evidence=dict(price=p,date=bars[i]['date'],known_on=bars[i+2]['date'])
        if abs(p-invalid)<=tick(invalid):pivots.append(evidence)
        if p<invalid-tick(invalid):deeper.append(evidence)
    last_contact=contacts[-1] if contacts else None
    rebound=bool(last_contact is not None and last_contact<len(bars)-1 and bars[-1]['close']>bars[last_contact]['high'])
    pivot_rebound=bool(pivots and bars[-1]['close']>invalid)
    confirmed=(bool(pivots) and pivot_rebound) or (len(contacts)>=2 and rebound)
    broken=any(b['close']<invalid-tolerance for b in bars[active_start:])
    buffer=invalid-plan['stop'];noise=max(r['median_lower_wick'] for r in v.values())
    tight=buffer<noise
    risk=endpoint(plan['range']['high'] if plan['range_valid'] else plan['structural_high'],plan['stop'],plan['r1'],plan['r2'],bars[-1]['close'],a)
    status='STRUCTURAL_STOP_CONFIRMED' if confirmed and not broken else 'STRUCTURAL_STOP_WEAK'
    if broken:status='STOP_UNVERIFIED'
    if tight:status='STOP_TOO_TIGHT_FOR_VOLATILITY'
    if risk['stop_risk_pct']>PROTOCOL['max_stop_risk_pct']:status='STOP_RISK_EXCESSIVE'
    alternative=None
    if deeper:
        p=max(deeper,key=lambda x:x['price']);s=down(p['price']-tolerance)
        alternative=dict(p,stop=s,upper_endpoint=endpoint(plan['range']['high'] if plan['range_valid'] else plan['structural_high'],s,plan['r1'],plan['r2'],bars[-1]['close'],a),
            adopted=False,reason='STRONGER_DEEPER_PIVOT_IS_COMPARISON_ONLY_NOT_A_STOP_CHANGE')
    return dict(status=status,research_eligible=status=='STRUCTURAL_STOP_CONFIRMED',
        certification_scope='COMPLETED_DAILY_PRICE_STRUCTURE_ONLY_NOT_SOURCE_OR_PROFIT_CERTIFICATION',
        original_low=invalid,original_stop=plan['stop'],formula_matches_original=True,stop_modified=False,
        buffer_krw=buffer,buffer_atr=buffer/a,active_contact_dates=[bars[i]['date'] for i in contacts],
        independent_contacts=len(contacts),confirmed_pivots=pivots,rebound_observed=rebound or pivot_rebound,
        last_support_break_date=bars[last_break]['date'] if last_break>=0 else None,
        latest_contact_volume_ratio=(bars[-1]['volume']/bars[last_contact]['volume']) if last_contact is not None and bars[last_contact]['volume'] else None,
        variation=v,normal_wick_comparator_krw=noise,
        past20_wick_exceeds_buffer_count=sum(min(b['open'],b['close'])-b['low']>buffer for b in bars[-20:]),
        false_stop_probability='UNAVAILABLE_NO_INDEPENDENT_INTRADAY_STOP_SEQUENCE',
        deeper_confirmed_support=alternative,gap_loss_can_exceed_stop=True)

def practicality(plan):
    r=plan['range'];a=plan['atr14'];close=plan['reference_close'];low=plan['structural_low'];high=plan['structural_high']
    cutoff=close-a*PROTOCOL['max_distance_atr'];pct_cutoff=close*(1-PROTOCOL['max_distance_pct']/100)
    valid=r['valid'];width=r['high']-r['low'] if valid else 0
    if valid:state='RANGE_TOO_NARROW' if width/a<PROTOCOL['support_band_atr'] else 'RANGE_VALID'
    elif high<max(cutoff,pct_cutoff):state='RANGE_TOO_FAR'
    elif r.get('reason')=='NEAREST_OVERHEAD_RESISTANCE_UNCONFIRMED_OR_INSIDE_RANGE':state='STRUCTURAL_SUPPORT_UNCONFIRMED'
    else:state='RISK_REWARD_INSUFFICIENT'
    return dict(status=state,research_eligible=state=='RANGE_VALID',
        width_krw=width,width_pct=100*width/((r['low']+r['high'])/2) if valid else None,width_atr=width/a,
        original_structure=[low,high],original_structure_width=high-low,original_structure_width_atr=(high-low)/a,
        distance_floor= max(cutoff,pct_cutoff),distance_clip_removed_krw=r['low']-low if valid else None,
        narrow_alert_basis='EXISTING_0_2_ATR_SUPPORT_TOLERANCE_RESEARCH_DIAGNOSTIC_NOT_VALIDATED_LIVE_MINIMUM',
        sensitivity={str(t):bool(valid and width/a>=t) for t in (0,.1,.2,.3,.4)},
        risk_limits_changed=False,range_widened=False,execution_probability='UNAVAILABLE_FOR_NOV11_FUTURE_PATH',
        intraday_volume_at_price='UNAVAILABLE')

def reassess(bars,legacy):
    out=copy.deepcopy(legacy);out['legacy_best']=copy.deepcopy(legacy['best'])
    for p in out['plans']:
        p['stop_reliability']=stop_review(bars,p);p['practicality']=practicality(p)
        p['volume_profile_context']=volume_proxy(bars,p['atr14'])
        p['practical_research_eligible']=p['range_valid'] and p['stop_reliability']['research_eligible'] and p['practicality']['research_eligible']
    good=[p for p in out['plans'] if p['practical_research_eligible']]
    out['best']=min(good,key=lambda p:(p['range']['endpoints']['upper']['distance_atr'],-p['range']['min_net_r1_rr'],p['method'])) if good else None
    out['practical_research_pass']=bool(good)
    out['original_numeric_plans_unchanged']=True
    return out

def audit_no_anchor_change(old,new):
    fields=('method','support','stop','r1','r2','structural_low','structural_high')
    if len(old['plans'])!=len(new['plans']):raise ValueError('STRUCTURAL_PLAN_COUNT_CHANGED')
    for a,b in zip(old['plans'],new['plans']):
        if any(a.get(k)!=b.get(k) for k in fields) or a['range']!=b['range']:raise ValueError('REVIEW_MOVED_ORIGINAL_RANGE_STOP_OR_RESISTANCE')
    return True
