"""Cash-aware two queued limits; enumerate daily OHLC order, not fake fills.

Bounds refer to OHLC-consistent research paths, not exchange execution proof.
All share quantities are fixed at the signal close from LIMIT prices.
"""
import copy,json,math
from c3_zone_entry_v1 import P,allocation,buy_unit,sale_unit


def nav(s,price):return s['cash']+sum(f['quantity'] for f in s['fills'])*sale_unit(price) if s['exit'] is None else s['cash']


def mark(s,price):
    n=nav(s,price);s['nav_min']=min(s['nav_min'],n);s['nav_max']=max(s['nav_max'],n)
    s['nav_peak']=max(s['nav_peak'],n);s['intraday_dd']=min(s['intraday_dd'],100*(n/s['nav_peak']-1))
    if s['exit'] is None and s['fills']:
        if s['targets'][0] is not None and price>=s['targets'][0]:s['r1_hit']=True
        if s['targets'][1] is not None and price>=s['targets'][1]:s['r2_hit']=True


def close_mark(s,close,day):
    n=nav(s,close);s['last_close']=close;s['close_peak']=max(s['close_peak'],n)
    s['close_dd']=min(s['close_dd'],100*(n/s['close_peak']-1));s['close_marks'].append((day,n));return s


def buy(s,leg,price,day,g):
    q=s['sizes'][leg]
    if q<=0 or leg in s['done']:return
    cost=q*buy_unit(price)
    if cost>s['cash']+1e-6:raise ValueError('PLANNED_CAPITAL_OVERRUN')
    s['cash']-=cost;s['spent']+=cost;s['gross']+=q*price;s['done'].append(leg)
    s['fills'].append(dict(leg=leg+1,quantity=q,price=price,date=day,buy_cost_krw=cost))
    if s['first_g'] is None:s['first_g']=g
    mark(s,price)


def sell(s,price,day,reason):
    if s['exit'] is not None or not s['fills']:return
    q=sum(f['quantity'] for f in s['fills']);s['cash']+=q*sale_unit(price)
    s['exit']=dict(price=price,date=day,reason=reason);mark(s,price)


def path_day(state,b,day,g,plan,valid_until,horizon,order,touch_fills,exit_policy):
    s=copy.deepcopy(state);o,h,l,c=[b[k] for k in ('open','high','low','close')];stop=plan['stop'];r1=plan.get('resistance')
    if s['pending_close_stop']:
        sell(s,o,day,'FROZEN_CLOSE_STOP_NEXT_OPEN');return close_mark(s,c,day)
    primary=exit_policy=='R1_OR_INTRADAY_STOP'
    if s['fills'] and primary and r1 is not None and o>=r1:
        sell(s,r1,day,'R1_TARGET_GAP_CONSERVATIVE');s['r1_hit']=True;return close_mark(s,c,day)
    # Both orders were already queued: seeing the opening gap does NOT grant
    # a retrospective right to cancel a marketable lower buy limit.
    for leg in (0,1):
        if g<=valid_until and leg not in s['done'] and o<=s['limits'][leg]:buy(s,leg,o,day,g)
    if s['fills']:
        mark(s,o)
        if primary and o<=stop:
            s['flags'].add('AUCTION_BUYS_BELOW_STOP_EXECUTION_UNCERTAIN')
            # Same-day low is a deliberately adverse manual-exit stress bound.
            sell(s,l if order=='LOW_STRESS' else o,day,'OPEN_BELOW_STOP_QUEUED_LIMITS');return close_mark(s,c,day)
    points=[o,h,l,c] if order=='HIGH_FIRST' else [o,l,h,c]
    for start,end in zip(points,points[1:]):
        if s['exit'] is not None:break
        if end<start:
            levels=[]
            for leg,limit in enumerate(s['limits']):
                if g<=valid_until and leg not in s['done'] and s['sizes'][leg]>0 and end<=limit<start:
                    if l==limit:
                        s['flags'].add('EXACT_LIMIT_TOUCH_FILL_UNCERTAIN')
                        if not touch_fills:continue
                    levels.append((limit,'BUY',leg))
            if primary and end<=stop<start:levels.append((stop,'STOP',None))
            for price,what,leg in sorted(levels,reverse=True):
                if s['exit'] is not None:break
                mark(s,price)
                if what=='BUY':buy(s,leg,price,day,g)
                elif s['fills']:sell(s,stop,day,'STRUCTURAL_STOP_INTRADAY')
        elif end>start and primary and s['fills'] and r1 is not None and start<r1<=end:
            mark(s,r1);sell(s,r1,day,'R1_TARGET')
        if s['exit'] is None:mark(s,end)
    if s['fills'] and primary and b['low']<=stop and len(s['fills'])==2:
        s['flags'].add('SAME_DAY_TWO_LIMITS_AND_STOP')
    if s['exit'] is None and s['first_g'] is not None and g>=s['first_g']+horizon:
        sell(s,c,day,'HORIZON_CLOSE')
    if s['exit'] is None and s['fills'] and not primary and c<stop:s['pending_close_stop']=True
    return close_mark(s,c,day)


def state_key(s):
    return json.dumps(dict(fills=s['fills'],cash=round(s['cash'],7),done=s['done'],exit=s['exit'],pending=s['pending_close_stop'],r1=s['r1_hit'],r2=s['r2_hit']),sort_keys=True)


def merge(states):
    unique={}
    for s in states:
        key=state_key(s)
        if key not in unique:unique[key]=s;continue
        a=unique[key];a['flags']|=s['flags']
        for k in ('nav_min','intraday_dd','close_dd'):a[k]=min(a[k],s[k])
        for k in ('nav_max','nav_peak','close_peak'):a[k]=max(a[k],s[k])
    return list(unique.values())


def terminal(s,plan,capital,asof):
    q=sum(f['quantity'] for f in s['fills']);last=s['last_close'];n=nav(s,last);a=s['gross']/q if q else None
    risk=s['spent']-q*sale_unit(plan['stop']) if q else 0.
    rr=lambda r:(q*sale_unit(r)-s['spent'])/risk if r is not None and risk>0 else None
    return dict(plan_return_pct=100*(n/capital-1),pnl_krw=n-capital,invested_cost_krw=s['spent'],gross_entry_krw=s['gross'],quantity=q,
        weighted_average_price=a,cash_uninvested_krw=capital-s['spent'],fills=s['fills'],first_filled=any(f['leg']==1 for f in s['fills']),second_filled=any(f['leg']==2 for f in s['fills']),
        scenario='B_BOTH_FILLED' if len(s['fills'])==2 else 'A_FIRST_ONLY' if s['fills'] else 'C_UNFILLED',
        stop_occurred=bool(s['exit'] and 'STOP' in s['exit']['reason']),exit=s['exit'],open_position=s['exit'] is None and bool(q),marked_asof=asof,
        frozen_stop_loss_krw=risk,plan_stop_risk_pct=100*risk/capital,net_r1_rr_at_filled_size=rr(plan.get('resistance')),net_r2_rr_at_filled_size=rr(plan.get('resistance2')),
        plan_nav_mfe_pct=100*(s['nav_max']/capital-1),plan_nav_mae_pct=100*(s['nav_min']/capital-1),max_drawdown_close_pct=s['close_dd'],intraday_path_stress_drawdown_pct=s['intraday_dd'],
        r1_reached=s['r1_hit'],r2_reached=s['r2_hit'],flags=sorted(s['flags']),actual_fill_verified=False)


def simulate(plan,bars,signal_index,sessions,split=(.5,.5),validity=1,horizon=20,cutoff=None,allow_partial=False,exit_policy='R1_OR_INTRADAY_STOP',capital=None):
    capital=capital or P['planned_capital_krw'];cutoff=cutoff or sessions[-1];grid={d:i for i,d in enumerate(sessions)};g0=grid[bars[signal_index]['date']]
    end_i=max(i for i,d in enumerate(sessions) if d<=cutoff);mature=g0+3+horizon<=end_i
    if not mature and not allow_partial:return dict(status='CENSORED_COMMON_MATURITY',conservative_plan_return_pct=None)
    if plan is None:
        by={b['date']:b for b in bars};future=[by.get(d) for d in sessions[g0+1:min(end_i,g0+3+horizon)+1]]
        good=bool(future) and all(b and b.get('tradable',True) and not b.get('action_boundary') and b.get('segment',0)==bars[signal_index].get('segment',0) for b in future)
        missed=100*(max(b['high'] for b in future)/bars[signal_index]['close']-1) if good else None
        return dict(status='NO_VALID_PLAN_CASH',conservative_plan_return_pct=0.,optimistic_plan_return_pct=0.,first_filled=False,second_filled=False,ambiguous=False,pnl_krw=0.,quantity=0,actual_fill_verified=False,missed_rally_mfe_pct=missed)
    if not 0<plan['stop']<plan['low']<=plan['high']:raise ValueError('INVALID_STOP_AND_ZONE_ORDER')
    a=allocation(plan,split,capital);sizes=[x['quantity'] for x in a['legs']];by={b['date']:b for b in bars};valid_until=g0+validity
    base=dict(cash=float(capital),spent=0.,gross=0.,fills=[],done=[],sizes=sizes,limits=[plan['high'],plan['low']],first_g=None,exit=None,pending_close_stop=False,
        nav_min=float(capital),nav_max=float(capital),nav_peak=float(capital),intraday_dd=0.,close_peak=float(capital),close_dd=0.,close_marks=[],flags=set(),r1_hit=False,r2_hit=False,targets=[plan.get('resistance'),plan.get('resistance2')],last_close=bars[signal_index]['close'])
    states=[base];finished=[];upper_end=min(end_i,g0+3+horizon)
    for g in range(g0+1,upper_end+1):
        if not states:break
        day=sessions[g];b=by.get(day)
        if not b or not b.get('tradable',True) or b.get('invalid_data') or b.get('action_boundary') or b.get('segment',0)!=bars[signal_index].get('segment',0):
            return dict(status='CENSORED_ACTION_HALT_OR_PRICE_GAP',conservative_plan_return_pct=None)
        next_states=[]
        for s in states:
            if s['exit'] is not None:finished.append(s);continue
            if not s['fills'] and g>valid_until:finished.append(s);continue
            modes=[True,False] if any(q>0 and limit==b['low'] for q,limit in zip(sizes,s['limits'])) else [True]
            orders=['HIGH_FIRST','LOW_FIRST']
            if b['open']<=plan['stop'] and (s['fills'] or g<=valid_until):orders.append('LOW_STRESS')
            for order in orders:
                for touch in modes:
                    x=path_day(s,b,day,g,plan,valid_until,horizon,order,touch,exit_policy);x['last_close']=b['close']
                    (finished if x['exit'] is not None or (not x['fills'] and g>=valid_until) else next_states).append(x)
        states=merge(next_states)
        if len(states)>128:raise ValueError('UNRESOLVED_PATH_STATE_EXPLOSION')
    finished=merge(finished+states);out=[terminal(s,plan,capital,sessions[min(end_i,upper_end)]) for s in finished]
    if not out:raise ValueError('NO_EVALUABLE_EXECUTION_PATH')
    worst=min(out,key=lambda x:(x['plan_return_pct'],-x['quantity'],x['r1_reached']));best=max(out,key=lambda x:x['plan_return_pct'])
    distinct={(round(x['plan_return_pct'],9),x['first_filled'],x['second_filled'],(x['exit'] or {}).get('date'),(x['exit'] or {}).get('reason'),x['r1_reached'],x['r2_reached']) for x in out}
    ambiguous=len(distinct)>1 or any('UNCERTAIN' in flag for x in out for flag in x['flags'])
    future=[by.get(d) for d in sessions[g0+1:upper_end+1]]
    missing=any(b is None or not b.get('tradable',True) or b.get('action_boundary') or b.get('segment',0)!=bars[signal_index].get('segment',0) for b in future)
    missed=None if missing else 100*(max((b['high'] for b in future),default=bars[signal_index]['close'])/bars[signal_index]['close']-1)
    return dict(status='COMPLETE' if mature else 'PARTIAL_ASOF_NOT_MATURE',conservative_plan_return_pct=worst['plan_return_pct'],optimistic_plan_return_pct=best['plan_return_pct'],
        first_filled=worst['first_filled'],second_filled=worst['second_filled'],first_fill_possible=any(x['first_filled'] for x in out),second_fill_possible=any(x['second_filled'] for x in out),
        first_fill_certain_across_simulated_paths=all(x['first_filled'] for x in out),second_fill_certain_across_simulated_paths=all(x['second_filled'] for x in out),
        ambiguous=ambiguous,path_count=len(out),worst=worst,best=best,missed_rally_mfe_pct=missed if not any(x['first_filled'] for x in out) else None,
        actual_fill_verified=False,capital_krw=capital,exit_policy=exit_policy,allocation=a)
