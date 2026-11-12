"""Typed structural evidence and intact support zones; independent V4 research.

No new indicators, tuned thresholds, trades, or mutation of V2/V3 plans.
Distance is a SETUP accessibility check, not a way to carve a fake sliver
from support. All risk/fee/RR constraints still cover every tick in the zone.
"""
import copy,statistics
from first_pullback_v55 import hma60,confirmed_turn,phase,up,down,tick
from free_structural_v52 import atr14
from c3_dynamic_entry_v2 import first_pullback_context,retest_structure
from c3_single_entry_range_v1 import PROTOCOL,factors,endpoint,legal_ticks,active_resistances
from c3_range_structure_v3 import reassess,variation,invalidation

def first_after_breakout(bars,atr):
    """First price pullback in an established trend; no new HMA turn needed.

    Reuses existing 20-session breakout, 1.2 volume, .25ATR dip and .8ATR
    extension tolerances. A previous completed reclaim disqualifies a new
    'first' signal. This covers an existing uptrend rather than loosening RS.
    """
    audits=[];found=None;n=len(bars)
    if n<80:return None,audits
    c=[b['close'] for b in bars];ma20=statistics.mean(c[-20:]);ma60=statistics.mean(c[-60:])
    if not c[-1]>ma20>ma60 or ma20<=statistics.mean(c[-25:-5]):return None,audits
    for j in range(max(20,n-20),n-2):
        level=max(b['high'] for b in bars[j-20:j]);avg=statistics.mean(b['volume'] for b in bars[j-20:j])
        if bars[j]['close']<=level or bars[j-1]['close']>level or not avg or bars[j]['volume']/avg<1.2:continue
        dip=None;peak=bars[j]['close'];reclaim=None
        for k in range(j+1,n):
            peak=max(peak,bars[k-1]['close'])
            if dip is None and bars[k]['close']<bars[k-1]['close'] and bars[k]['low']<=peak-.25*atr:dip=k
            elif dip is not None and bars[k]['close']>bars[k-1]['high']:
                reclaim=k;break
        retained=not any(b['close']<level-.25*atr for b in bars[j+1:])
        audits.append(dict(breakout_date=bars[j]['date'],level=level,first_dip=bars[dip]['date'] if dip is not None else None,
            first_reclaim=bars[reclaim]['date'] if reclaim is not None else None,support_retained=retained))
        if dip is None or reclaim!=n-1 or not retained or bars[-1]['close']>peak+.8*atr:continue
        normal=statistics.mean(b['volume'] for b in bars[-21:-1])
        if bars[dip]['volume']>1.5*normal:continue
        found=dict(breakout_index=j,breakout_level=level,dip_index=dip,breakout_volume_ratio=bars[j]['volume']/avg)
    return found,audits


def zone_geometry(low,high,stop,r1,r2,close,atr,structure_confirmed):
    reasons=[]
    if not 0<stop<low<=high<=close or r1 is None or r1<=low:
        return dict(valid=False,reason='RISK_REWARD_INSUFFICIENT_OR_INVALID_STRUCTURE')
    b,s=factors();k=PROTOCOL['min_net_r1_rr'];risk=PROTOCOL['max_stop_risk_pct']/100
    upper=down(min(high,stop/(1-risk),s*(r1+k*stop)/(b*(1+k))))
    lower=up(low)
    if upper<=lower:return dict(valid=False,reason='RISK_REWARD_INSUFFICIENT')
    distance_pct=100*(close-upper)/close;distance_atr=(close-upper)/atr
    if distance_pct>PROTOCOL['max_distance_pct'] or distance_atr>PROTOCOL['max_distance_atr']:
        return dict(valid=False,reason='RANGE_TOO_FAR',structural_low=lower,risk_limited_upper=upper,
            nearest_edge_distance_pct=distance_pct,nearest_edge_distance_atr=distance_atr)
    width=(upper-lower)/atr;old_floor=up(max(low,close-atr*PROTOCOL['max_distance_atr'],close*(1-PROTOCOL['max_distance_pct']/100)))
    fragment=max(0,upper-old_floor)<PROTOCOL['support_band_atr']*atr and old_floor>lower
    narrow=width<PROTOCOL['support_band_atr']
    state='NARROW_BUT_STRUCTURALLY_VALID' if narrow and structure_confirmed else 'RANGE_TOO_NARROW' if narrow else 'PRACTICAL_RANGE'
    if not structure_confirmed:reasons.append('SUPPORT_UNCONFIRMED')
    if state=='RANGE_TOO_NARROW':reasons.append(state)
    points={name:endpoint(p,stop,r1,r2,close,atr) for name,p in [('lower',lower),('middle',up((lower+upper)/2)),('upper',upper)]}
    checks=0
    for p in legal_ticks(lower,upper):
        e=endpoint(p,stop,r1,r2,close,atr);checks+=1
        if e['stop_risk_pct']>PROTOCOL['max_stop_risk_pct']+1e-9 or e['net_r1_rr']<k-1e-9:raise ValueError('V4_UNSAFE_PRICE_INSIDE_RANGE')
    return dict(valid=not reasons,reason=reasons[0] if reasons else None,status=state,low=lower,high=upper,endpoints=points,
        width_atr=width,ticks_checked=checks,all_legal_ticks_passed=True,min_net_r1_rr=points['upper']['net_r1_rr'],
        structural_range=[low,high],old_distance_clipped_low=old_floor,old_fragment_was_too_narrow=fragment,
        distance_policy='NEAREST_EDGE_ELIGIBILITY_WHOLE_STRUCTURAL_ZONE_RETAINED',
        lower_edge_exceeds_old_distance_limit=points['lower']['distance_atr']>PROTOCOL['max_distance_atr'] or points['lower']['distance_pct']>PROTOCOL['max_distance_pct'],
        research_only=True,stop_or_resistance_moved_for_reward=False)


def _plan(bars,kind,anchor,invalid,known,evidence,template=None):
    a=atr14(bars);close=bars[-1]['close'];noise=statistics.median(min(b['open'],b['close'])-b['low'] for b in bars[-20:])
    buffer=max(PROTOCOL['stop_buffer_atr']*a,noise)
    stop=down(invalid-buffer) # Frozen BEFORE entry geometry.
    low=up(max(invalid,anchor-PROTOCOL['support_band_atr']*a));high=down(min(close,anchor+PROTOCOL['support_band_atr']*a))
    levels,discarded=active_resistances(bars,low,a);r1=levels[0]['price'] if levels else None;r2=levels[1]['price'] if len(levels)>1 else None
    zone=zone_geometry(low,high,stop,r1,r2,close,a,True) if low and high else dict(valid=False,reason='SUPPORT_UNCONFIRMED')
    sr=dict(status='STRUCTURAL_STOP_CONFIRMED',research_eligible=True,structure_type=kind,original_low=invalid,original_stop=stop,
        independent_contacts=evidence.get('independent_contacts',1),two_contacts_required=False,buffer_krw=invalid-stop,buffer_atr=(invalid-stop)/a,
        active_contact_dates=evidence.get('contact_dates',[evidence.get('low_date',known)]),confirmed_on=known,
        evidence=evidence,variation=variation(bars),source_regular_only_certified=False,
        buffer_policy='MAX_EXISTING_QUARTER_ATR_AND_OBSERVED_20_SESSION_MEDIAN_LOWER_WICK',
        actual_false_stop_probability='UNAVAILABLE',gap_loss_can_exceed_stop=True)
    if zone.get('endpoints') and zone['endpoints']['upper']['stop_risk_pct']>PROTOCOL['max_stop_risk_pct']:sr['status']='STOP_RISK_EXCESSIVE';sr['research_eligible']=False
    return dict(method=kind,structure_type=kind,asof=bars[-1]['date'],reference_close=close,atr14=a,support=anchor,
        support_known_on=known,structural_low=low,structural_high=high,invalidation_low=invalid,stop=stop,r1=r1,r2=r2,
        evidence=evidence,resistance_evidence=levels,broken_resistances_excluded=discarded,range=zone,range_valid=zone['valid'],
        stop_reliability=sr,practicality=dict(status=zone.get('status',zone.get('reason')),width_krw=zone.get('high',high)-zone.get('low',low),
            research_eligible=zone['valid'],original_structure=[low,high],range_widened_from_price_structure=zone.get('low',low)<(template or {}).get('range',{}).get('low',low)),
        practical_research_eligible=zone['valid'],validity_sessions=[1,2,3],default_validity_sessions=1,
        buy_approved=False,cancel_conditions=['SUPPORT_BREAK','OPEN_BELOW_RANGE_OR_STOP','R1_ALREADY_REACHED','EXPIRED_RANGE_NOT_REACHED_PASS'])


def review_v4(bars,legacy):
    v3=reassess(bars,legacy);out=[];audit={};a=atr14(bars) if len(bars)>=20 else 0
    # Confirmed pivots or retained repeated support were already exempt from
    # an extra two-touch requirement in V3. Preserve that real evidence.
    for p in v3['plans']:
        sr=p['stop_reliability']
        if sr.get('confirmed_pivots') or (sr.get('independent_contacts',0)>=2 and sr.get('rebound_observed')):
            invalid=invalidation(p)
            if invalid is None:continue
            ev=dict(low_date=(sr.get('confirmed_pivots') or [{}])[0].get('date',p['support_known_on']),
                confirmed_pivots=sr.get('confirmed_pivots',[]),independent_contacts=sr.get('independent_contacts',0),
                contact_dates=sr.get('active_contact_dates',[]),source_method=p['method'])
            if sr.get('last_support_break_date')==bars[-1]['date']:continue
            out.append(_plan(bars,'CONFIRMED_PIVOT' if sr.get('confirmed_pivots') else 'CONFIRMED_REPEATED_SUPPORT',p['support'],invalid,p['support_known_on'],ev,p))
    if len(bars)>=80:
        h=hma60([b['close'] for b in bars]);turn=confirmed_turn(h);label=phase(bars,h,a,turn)
        dip=first_pullback_context(bars,turn,a) if turn is not None else None
        audit.update(hma_turn_known_on=bars[turn]['date'] if turn is not None else None,hma_phase=label,
            first_pullback_context=bars[dip]['date'] if dip is not None else None)
        # A confirmed first reclaim is evidence in its own right. It does not
        # need to wait for a SECOND independent future support contact.
        if label=='FIRST_PULLBACK_RECLAIM' and dip is not None:
            leg=bars[dip:];lowbar=min(leg,key=lambda b:b['low']);invalid=lowbar['low']
            choices=[p for p in legacy['plans'] if p['method'].startswith('TREND_CONFIRMED_MA') and p['evidence']['touch_date']>=bars[dip]['date']]
            anchor=min(choices,key=lambda p:abs(p['support']-bars[-1]['close']))['support'] if choices else invalid
            out.append(_plan(bars,'FIRST_PULLBACK',anchor,invalid,bars[-1]['date'],dict(turn_known_on=bars[turn]['date'],
                pullback_start=bars[dip]['date'],low_date=lowbar['date'],reclaim_date=bars[-1]['date'],
                previous_high=bars[-2]['high'],reclaim_close=bars[-1]['close'],
                pullback_mean_volume=statistics.mean(b['volume'] for b in leg[:-1]) if len(leg)>1 else None,
                reclaim_volume=bars[-1]['volume'],earlier_completed_reclaim=False,phase_rule='REUSED_V55_PLUS_PR104_FIRST_PULLBACK_CONTEXT')))
        price_first,breakout_audits=first_after_breakout(bars,a)
        audit['price_breakout_first_pullback_audit']=breakout_audits
        if price_first:
            j=price_first['breakout_index'];dip=price_first['dip_index'];leg=bars[dip:];lowbar=min(leg,key=lambda b:b['low'])
            choices=[p for p in legacy['plans'] if p['method'].startswith('TREND_CONFIRMED_MA') and p['evidence']['touch_date']>=bars[dip]['date']]
            anchor=min(choices,key=lambda p:abs(p['support']-bars[-1]['close']))['support'] if choices else lowbar['low']
            out.append(_plan(bars,'FIRST_PULLBACK',anchor,lowbar['low'],bars[-1]['date'],dict(
                breakout_date=bars[j]['date'],breakout_level=price_first['breakout_level'],breakout_volume_ratio=price_first['breakout_volume_ratio'],
                pullback_start=bars[dip]['date'],low_date=lowbar['date'],reclaim_date=bars[-1]['date'],
                previous_high=bars[-2]['high'],reclaim_close=bars[-1]['close'],earlier_completed_reclaim=False,
                phase_rule='ESTABLISHED_TREND_FIRST_PULLBACK_AFTER_OBSERVED_BREAKOUT')))
        # Completed breakout/retest is also its own evidence path. Inspect all
        # post-breakout lows and closes, including the confirmation candle.
        for p in legacy['plans']:
            if p['method']!='FIRST_PULLBACK_RETEST':continue
            ev=p['evidence'];j=next(i for i,b in enumerate(bars) if b['date']==ev['breakout_date']);s=retest_structure(bars,j,p['support'],a)
            if not s['support_retained_on_closes'] or ev['breakout_volume_ratio']<1.2:continue
            out.append(_plan(bars,'BREAKOUT_RETEST',p['support'],s['invalidation_low'],p['support_known_on'],dict(ev,
                post_breakout_structure=s,low_date=s['low_date'],independent_contacts=1),p))
    # Deduplicate identical structure/anchors, without seeing future returns.
    unique={}
    for p in out:unique[(p['method'],p['support'],p['stop'])]=p
    out=list(unique.values());good=[p for p in out if p['range_valid']]
    best=min(good,key=lambda p:(p['range']['endpoints']['upper']['distance_atr'],-p['range']['min_net_r1_rr'],p['method'])) if good else None
    return dict(plans=out,best=best,legacy_best=legacy['best'],v3_review=v3,structure_audit=audit,
        reason=None if out else 'SUPPORT_UNCONFIRMED',practical_research_pass=bool(best),
        original_numeric_plans_unchanged=True,policy='STRUCTURE_FIRST_STOP_THEN_WHOLE_ZONE_RISK')


def reasons(row,version='v4'):
    result=[];q=row.get('financial',{})
    if not q.get('observed_positive'):result.append('COMPANY_UNKNOWN' if q.get('company_observation_state')=='UNKNOWN_NOT_COMPANY_FAILURE' or q.get('status') in ('UNAVAILABLE_OR_FUTURE_REPORT','HISTORICAL_PIT_UNAVAILABLE') else 'COMPANY_OBSERVED_METRICS_FAIL')
    if not row['momentum_pass']:result.append('RS_NOT_POSITIVE_AND_IMPROVING')
    if not row['liquidity_pass']:result.append('TURNOVER_BELOW_EXISTING_FLOOR')
    review=row['range_review'] if version=='v4' else row['range_review']['v3_review']
    if not review['plans']:result.append('SUPPORT_UNCONFIRMED')
    if not any(p['range_valid'] for p in review['plans']):result.append('NO_RISK_VALID_RANGE')
    if not any(p.get('stop_reliability',{}).get('research_eligible') for p in review['plans']):result.append('NO_CONFIRMED_STRUCTURAL_STOP')
    if any(p['range_valid'] for p in review['plans']) and not review['best']:result.append('RANGE_PRACTICALITY_OR_STOP_REJECTED')
    return sorted(set(result))
