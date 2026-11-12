"""Independent, causal dynamic entry research. Never imported by operation.

Reuse existing HMA/ATR/pivot/retest/VCP primitives. Only BB width and ADX are
new indicators. Research stops are separate from every registered old stop.
"""
import math,statistics,json
from pathlib import Path
from first_pullback_v55 import hma60,confirmed_turn,phase,up,down,tick
from free_structural_v52 import atr14
from entry_strategy_v58 import confirmed_pivots,breakout_retest,trend_pullback
from krx_preignition_v87 import signal as preignition

ROOT=Path(__file__).resolve().parent.parent
DEFAULT=json.loads((ROOT/'config/c3_dynamic_entry_v2_protocol.json').read_text())
METHODS=('HMA_FIRST_PULLBACK','BREAKOUT_RETEST','COMPRESSION_REBREAK')
MODELS=('C3_ORIGINAL','DYNAMIC','DYNAMIC_BB','DYNAMIC_ADX','DYNAMIC_BB_ADX')


def bandwidth(closes,n=20):
    return [None if i<n-1 else 4*statistics.pstdev(closes[i-n+1:i+1])/statistics.mean(closes[i-n+1:i+1]) for i in range(len(closes))]


def adx14(bars,n=14):
    """Wilder DM/TR sums, mean of first n DX, then Wilder ADX smoothing."""
    out=[None]*len(bars);dx=[];trsum=psum=msum=0.;adx=None
    for i in range(1,len(bars)):
        b,p=bars[i],bars[i-1];u=b['high']-p['high'];v=p['low']-b['low']
        tr=max(b['high']-b['low'],abs(b['high']-p['close']),abs(b['low']-p['close']))
        plus=u if u>v and u>0 else 0.;minus=v if v>u and v>0 else 0.
        if i<=n:trsum+=tr;psum+=plus;msum+=minus
        else:trsum=trsum-trsum/n+tr;psum=psum-psum/n+plus;msum=msum-msum/n+minus
        if i<n:continue
        pdi=100*psum/trsum if trsum else 0.;mdi=100*msum/trsum if trsum else 0.
        value=100*abs(pdi-mdi)/(pdi+mdi) if pdi+mdi else 0.;dx.append(value)
        if len(dx)==n:adx=statistics.mean(dx)
        elif len(dx)>n:adx=(adx*(n-1)+value)/n
        if adx is not None:out[i]=dict(adx=adx,plus_di=pdi,minus_di=mdi)
    return out


def indicators(bars):
    c=[b['close'] for b in bars]
    return dict(hma=hma60(c),bw=bandwidth(c),adx=adx14(bars))


def indicator_at(bars,pre=None):
    x=pre or indicators(bars);bw=x['bw'];a=x['adx'][-1]
    prior=[v for v in bw[-22:-2] if v is not None]
    return dict(hma60=x['hma'][-1],bandwidth20=bw[-1],prior_bandwidth20=bw[-2] if len(bw)>1 else None,
        bb_filter=bool(prior and bw[-2] is not None and bw[-2]<=statistics.median(prior)),
        adx14=a['adx'] if a else None,plus_di=a['plus_di'] if a else None,minus_di=a['minus_di'] if a else None,
        adx_filter=bool(a and a['adx']>=25 and a['plus_di']>a['minus_di']))


def resistance_levels(bars,above,atr,active_only=False,audit=None):
    # Confirmed high pivots: two CLOSED right-side bars, never future pivots.
    found=[]
    for i in range(max(2,len(bars)-62),len(bars)-2):
        h=bars[i]['high']
        if h>above and h>bars[i-1]['high'] and h>bars[i-2]['high'] and h>=bars[i+1]['high'] and h>=bars[i+2]['high']:
            if active_only:
                broken=[b['date'] for b in bars[i+2:] if b['close']>h]
                if broken:
                    if audit is not None:audit.append(dict(price=h,pivot_date=bars[i]['date'],known_on=bars[i+2]['date'],
                        reason='ALREADY_CLOSED_ABOVE_CONFIRMED_RESISTANCE',first_break=broken[0]))
                    continue
            found.append((h,bars[i]['date'],bars[i+2]['date']))
    clusters=[]
    for value,pivot,known in sorted(found):
        if not clusters or value-clusters[-1]['price']>DEFAULT['resistance_cluster_atr']*atr:
            clusters.append(dict(price=down(value),pivot_date=pivot,known_on=known))
    return clusters[:2]


def rr(entry,stop,target):
    if target is None or not 0<stop<entry:return None
    f=DEFAULT['fees'];paid=entry*(1+f['buy'])*(1+f['slippage_each_side'])
    loss=paid-stop*(1-f['sell'])*(1-f['slippage_each_side'])
    return (target*(1-f['sell'])*(1-f['slippage_each_side'])-paid)/loss if loss>0 else None


def geometry(bars,method,anchor,invalidation,support_date,known_on,setup=True,evidence=None):
    close=bars[-1]['close'];a=atr14(bars)
    stop=down(invalidation-DEFAULT['stop_buffer_atr']*a)
    lo=up(anchor);hi=down(min(close,anchor+DEFAULT['support_zone_atr']*a))
    r=resistance_levels(bars,max(close,hi or close),a)
    r1=r[0]['price'] if r else None;r2=r[1]['price'] if len(r)>1 else None
    ordered=bool(stop and lo and hi and 0<stop<lo<=hi<=close)
    risk=100*(hi-stop)/hi if ordered else None
    gap=100*(close-hi)/close if hi else None;gap_atr=(close-hi)/a if hi and a>0 else None
    reward=rr(hi,stop,r1) if ordered else None
    reasons=[]
    if not setup:reasons.append('SETUP_CONFIRMATION_REQUIRED')
    if not ordered:reasons.append('INVALID_SUPPORT_STOP_OR_RANGE_ORDER')
    if r1 is None:reasons.append('NO_CONFIRMED_OVERHEAD_R1')
    if gap_atr is not None and gap_atr>DEFAULT['max_entry_distance_atr']:reasons.append('ENTRY_MORE_THAN_ONE_ATR_AWAY')
    if gap is not None and gap>DEFAULT['max_entry_distance_pct']:reasons.append('ENTRY_MORE_THAN_EIGHT_PCT_AWAY')
    if risk is not None and risk>DEFAULT['max_stop_risk_pct']:reasons.append('STRUCTURAL_RISK_OVER_EIGHT_PCT')
    if reward is not None and reward<DEFAULT['min_net_r1_rr']:reasons.append('NET_R1_REWARD_TOO_SMALL')
    second=None
    if ordered:
        for i,v in reversed(confirmed_pivots(bars)):
            if stop+.3*a<v<lo-.5*a:
                second=dict(low=up(v),high=down(min(v+.2*a,lo-.5*a)),support_date=bars[i]['date'],known_on=bars[i+2]['date'],
                    stop=stop,policy='ALTERNATIVE_INDEPENDENT_SUPPORT_NOT_AUTOMATIC_AVERAGING_DOWN')
                if second['low']>second['high']:second=None;continue
                second['risk_pct']=100*(second['high']-stop)/second['high']
                second['net_r1_rr']=rr(second['high'],stop,r1);second['net_r2_rr']=rr(second['high'],stop,r2)
                break
    return dict(method=method,asof=bars[-1]['date'],reference_close=close,low=lo,high=hi,stop=stop,resistance=r1,resistance2=r2,
        support=anchor,invalidation_low=invalidation,support_date=support_date,support_known_on=known_on,resistance_evidence=r,
        atr14=a,entry_distance_pct=gap,entry_distance_atr=gap_atr,risk_pct=risk,net_r1_rr=reward,net_r2_rr=rr(hi,stop,r2) if ordered else None,
        entry2=second,entry2_is_required=False,geometry_pass=not reasons,reasons=reasons,setup_confirmed=setup,
        evidence=evidence or {},validity_sessions=[1,2,3],cancel_conditions=['GAP_BELOW_STOP_OR_RANGE','OPEN_AT_OR_ABOVE_R1','SUPPORT_BREAK','EXPIRED_RANGE_NOT_REACHED_PASS'],
        original_registered_stop_modified=False,research_only=True,buy_approved=False)


def first_pullback_context(bars,turn,atr):
    """Reject a second completed reclaim that the legacy phase label permits."""
    first_dip=None;peak=bars[turn]['close']
    for i in range(turn+1,len(bars)-1):
        peak=max(peak,bars[i-1]['close'])
        if first_dip is None and peak>=bars[turn]['close']+1.1*atr and bars[i]['close']<bars[i-1]['close'] and bars[i]['low']<=peak-.25*atr:
            first_dip=i
        elif first_dip is not None and bars[i]['close']>bars[i-1]['high']:
            return None
    return first_dip


def retest_structure(bars,breakout_index,level,atr):
    """Inspect EVERY completed post-breakout bar, including failed retests.

    A bar closing below the existing v58 tolerance invalidates that breakout.
    Its low must never be omitted to manufacture a tighter structural stop.
    """
    after=bars[breakout_index+1:]
    lowbar=min(after,key=lambda b:b['low'])
    broken=[b['date'] for b in after if b['close']<level-.25*atr]
    return dict(invalidation_low=lowbar['low'],low_date=lowbar['date'],support_retained_on_closes=not broken,
                support_break_dates=broken,observed_through=bars[-1]['date'])


def plans(bars,pre=None,ticker='SYNTHETIC'):
    if len(bars)<DEFAULT['min_history']:return [],None,'INSUFFICIENT_80_BAR_CONTIGUOUS_HISTORY'
    a=atr14(bars);x=pre or indicators(bars);h=x['hma'];turn=confirmed_turn(h);piv=confirmed_pivots(bars)
    watch=None;out=[]
    if piv:
        i,v=piv[-1];watch=geometry(bars,'STRUCTURAL_WATCH',v,v,bars[i]['date'],bars[i+2]['date'],False)
    if turn is not None and phase(bars,h,a,turn)=='FIRST_PULLBACK_RECLAIM':
        dip=first_pullback_context(bars,turn,a)
        choices=[(i,v) for i,v in piv if dip is not None and i>=dip]
        if choices:
            i,v=choices[-1];out.append(geometry(bars,METHODS[0],v,v,bars[i]['date'],bars[i+2]['date'],evidence={'turn_known_on':bars[turn]['date'],'hma60':h[-1]}))
    retest=breakout_retest(bars,a)
    if retest:
        level=retest['support_hint']
        for j in range(len(bars)-3,max(22,len(bars)-13)-1,-1):
            if max(b['high'] for b in bars[j-20:j])!=level or bars[j]['close']<=level:continue
            touch=[k for k in range(j+1,len(bars)-1) if bars[k]['low']<=level+.2*a and bars[k]['close']>=level-.25*a]
            if not touch:continue
            structure=retest_structure(bars,j,level,a);v=structure['invalidation_low']
            volume_ratio=bars[j]['volume']/statistics.mean(b['volume'] for b in bars[j-20:j])
            p=geometry(bars,METHODS[1],level,v,structure['low_date'],bars[-1]['date'],setup=volume_ratio>=1.2 and structure['support_retained_on_closes'],evidence={
                'breakout_date':bars[j]['date'],'breakout_volume_ratio':volume_ratio,
                'retest_date':structure['low_date'],'confirmation':'LEGACY_V58_RECLAIM_WITH_ALL_POST_BREAKOUT_BARS',
                'post_breakout_structure':structure})
            if not structure['support_retained_on_closes']:p['reasons'].append('RETEST_SUPPORT_INVALIDATED_AFTER_BREAKOUT')
            out.append(p);break
    # Reuse v8.7 pre-breakout contraction/higher-low/dry-volume detector on t-1;
    # add today's completed breakout. Its arbitrary legacy score is NOT used.
    compact=[dict(date=b['date'],o=b['open'],h=b['high'],l=b['low'],c=b['close'],v=b['volume']) for b in bars]
    base=preignition(ticker,compact,len(compact)-2)
    if base and base['volume_dryup']<=1 and bars[-1]['close']>base['resistance'] and bars[-1]['close']>bars[-2]['high']:
        recent=bars[-10:-1];low=min(b['low'] for b in recent)
        touches=[i for i,b in enumerate(recent) if b['low']<=low+.3*a]
        if touches and touches[-1]-touches[0]>=2:
            observed=min(bars[-10:],key=lambda b:b['low'])
            out.append(geometry(bars,METHODS[2],base['resistance'],observed['low'],observed['date'],bars[-1]['date'],setup=bars[-1]['volume']>=1.2*statistics.mean(b['volume'] for b in bars[-21:-1]),evidence={
                'base_known_on':bars[-2]['date'],'compression_ratio':base['compression_ratio'],'volume_dryup':base['volume_dryup'],
                'legacy_arbitrary_score_used':False,'support_touches':len(touches)}))
    return out,watch,None


def best_plan(items):
    valid=[p for p in items if p['geometry_pass']]
    return min(valid,key=lambda p:(p['entry_distance_atr'],-p['net_r1_rr'],p['method'])) if valid else None


def pick_unique(rows,last,session_index,limit=2):
    """Choose once per ticker across methods before observing any outcome."""
    picked=[];suppressed=0
    for row in rows:
        if len(picked)>=limit:break
        t=row['ticker']
        if session_index-last.get(t,-10000)<=DEFAULT['same_ticker_signal_lockout']:
            suppressed+=1;continue
        last[t]=session_index;picked.append(row)
    return picked,suppressed


def company_gate(facts,asof):
    if not facts or facts.get('original_document_pit_verified') is not True:return 'UNKNOWN_PIT_NOT_RANKED'
    if facts.get('published_on','9999')>asof:return 'FUTURE_FINANCIAL_REPORT_REJECTED'
    return 'CONFIRMED_FACTS_ONLY' if facts.get('financial_stability_verified') is True else 'FINANCIAL_STABILITY_NOT_CONFIRMED'


def evaluate_trade(plan,bars,signal_index,sessions,validity=1,horizon=20,cutoff=None):
    """Conservative range limit; no retrospective fill and no same-bar target guess."""
    end=cutoff or sessions[-1];grid={d:i for i,d in enumerate(sessions)};g=grid[bars[signal_index]['date']]
    # Common clock for 1/2/3-day validity and all compared methods.
    if g+3+horizon>=len(sessions) or sessions[g+3+horizon]>end:return {'status':'CENSORED_COMMON_CLOCK','return_pct':None}
    by={b['date']:b for b in bars};entry=None;entry_bar=None;entry_g=None;at_open=False
    for k in range(1,validity+1):
        d=sessions[g+k];b=by.get(d)
        if not b or not b.get('tradable',True) or b.get('action_boundary') or b['segment']!=bars[signal_index]['segment']:
            return {'status':'CENSORED_PRICE_ACTION_OR_GAP','return_pct':None}
        if b['open']<plan['low'] or b['open']<=plan['stop']:return {'status':'CANCEL_GAP_BELOW_RANGE','return_pct':0.,'filled':False}
        if plan.get('resistance') is not None and b['open']>=plan['resistance']:return {'status':'CANCEL_R1_ALREADY_REACHED','return_pct':0.,'filled':False}
        if b['low']<=plan['high']:
            entry=min(b['open'],plan['high']);entry_bar=b;entry_g=g+k;at_open=b['open']<=plan['high'];break
        if b['close']<plan['stop']:return {'status':'CANCEL_SUPPORT_BROKEN','return_pct':0.,'filled':False}
    if entry is None:
        path=[by.get(d) for d in sessions[g+1:g+3+horizon+1]]
        if any(not b or not b.get('tradable',True) or b.get('action_boundary') or b['segment']!=bars[signal_index]['segment'] for b in path):
            return {'status':'CENSORED_PRICE_ACTION_OR_GAP','return_pct':None,'filled':False}
        missed=max((b['high']/bars[signal_index]['close']-1 for b in path),default=0)*100
        return {'status':'PASS_UNFILLED','return_pct':0.,'filled':False,'missed_rally_mfe_pct':missed}
    stop=plan['stop'];r1=plan.get('resistance');r2=plan.get('resistance2');exit_price=None;reason=None;exit_date=None
    highs=[];lows=[];trade_highs=[entry];trade_lows=[entry];r1hit=r2hit=False;ambiguous=False;target_path_alive=True
    for z in range(entry_g,entry_g+horizon+1):
        b=by.get(sessions[z])
        if not b or not b.get('tradable',True) or b.get('action_boundary') or b['segment']!=entry_bar['segment']:
            return {'status':'CENSORED_PRICE_ACTION_OR_GAP','return_pct':None,'filled':True}
        highs.append(b['high']);lows.append(b['low'])
        if exit_price is None:
            if z>entry_g and b['open']<=stop:exit_price=b['open'];reason='STOP_GAP'
            elif b['low']<=stop:exit_price=stop;reason='STOP_INTRADAY_CONSERVATIVE'
            elif z==entry_g and not at_open:
                if r1 is not None and b['high']>=r1:ambiguous=True
            elif r1 is not None and (b['open']>=r1 or b['high']>=r1):
                exit_price=r1;reason='R1_TARGET';r1hit=True
            if reason and reason.startswith('STOP'):
                trade_highs.append(max(entry,b['open'] if z>entry_g or at_open else entry));trade_lows.append(exit_price)
            elif reason=='R1_TARGET':
                trade_highs.append(r1);trade_lows.append(b['low'])
            elif z==entry_g and not at_open:
                trade_highs.append(max(entry,b['close']));trade_lows.append(b['low'])
            else:trade_highs.append(b['high']);trade_lows.append(b['low'])
            if exit_price is not None:exit_date=b['date']
        # Opportunity paths are distinct from realized R1 exit. They stop at a
        # protective stop and cannot treat entry-day pre-fill highs as targets.
        if b['low']<=stop:target_path_alive=False
        if target_path_alive:
            if not(z==entry_g and not at_open):
                r1hit=r1hit or (r1 is not None and b['high']>=r1)
                r2hit=r2hit or (r2 is not None and b['high']>=r2)
    if exit_price is None:exit_price=by[sessions[entry_g+horizon]]['close'];reason='HORIZON_CLOSE';exit_date=sessions[entry_g+horizon]
    f=DEFAULT['fees'];net=100*(exit_price*(1-f['sell'])*(1-f['slippage_each_side'])/(entry*(1+f['buy'])*(1+f['slippage_each_side']))-1)
    return dict(status=reason,return_pct=net,filled=True,entry_date=entry_bar['date'],entry_price=entry,exit_date=exit_date,exit_price=exit_price,
        entry_wait_sessions=entry_g-g,mfe_pct=100*(max(trade_highs)/entry-1),mae_pct=100*(min(trade_lows)/entry-1),
        full_horizon_path_mfe_pct=100*(max(highs)/entry-1),full_horizon_path_mae_pct=100*(min(lows)/entry-1),
        r1_hit_before_stop=r1hit,r2_path_hit=r2hit,entry_day_target_sequence_unknown=ambiguous,
        fixed_horizon_close_net_pct=100*(by[sessions[entry_g+horizon]]['close']*(1-f['sell'])*(1-f['slippage_each_side'])/(entry*(1+f['buy'])*(1+f['slippage_each_side']))-1))
