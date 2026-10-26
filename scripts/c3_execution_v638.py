#!/usr/bin/env python3
"""Precommitted resting-limit research; never a broker client or approval."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json,math
import c3_event_replay_v637 as book

ENTRIES=('REST_1D','REST_2D','CONFIRM_THEN_REST')
EXITS=('STRUCT_D5','STRUCT_ATR_D12','TARGET10_D12')
REGIMES=('ALL','BENCH_TREND')


@dataclass(frozen=True)
class Policy:
    entry:str='REST_2D'
    exit:str='STRUCT_ATR_D12'
    regime:str='ALL'
    initial_cash:float=1_000_000.
    risk_fraction:float=.01
    retest_atr:float=.25
    confirmation_retest_atr:float=.15
    trail_atr:float=2.
    limit_penetration_ticks:int=1
    require_rr2:bool=False
    extra_stop_slippage:float=0.
    D0_affordability_alternative:bool=False
    failure_close_exit:bool=False
    fixed_exit_sessions:int=5

    def __post_init__(self):
        if self.entry not in ENTRIES or self.exit not in EXITS or self.regime not in REGIMES:
            raise ValueError('UNDECLARED_V638_POLICY')
        for x in (self.initial_cash,self.risk_fraction,self.retest_atr,self.confirmation_retest_atr,self.trail_atr):
            if not book.finite_positive(x):raise ValueError('INVALID_POLICY_NUMBER')
        if self.risk_fraction>.03 or type(self.limit_penetration_ticks) is not int or self.limit_penetration_ticks<1:
            raise ValueError('INVALID_RISK_OR_FILL_THRESHOLD')
        if type(self.extra_stop_slippage) not in (float,int) or not 0<=self.extra_stop_slippage<=.05:
            raise ValueError('INVALID_STOP_SLIPPAGE')
        if type(self.D0_affordability_alternative) is not bool or type(self.failure_close_exit) is not bool:
            raise ValueError('INVALID_POLICY_FLAG')
        if self.D0_affordability_alternative and self.entry=='CONFIRM_THEN_REST':
            raise ValueError('CONFIRMATION_PRICE_NOT_KNOWN_AT_D0_FOR_ALTERNATIVE_BUDGET')
        if type(self.fixed_exit_sessions) is not int or not 1<=self.fixed_exit_sessions<=12:
            raise ValueError('INVALID_FIXED_EXIT_HORIZON')

    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()


def ceil_tick(price):
    if not book.finite_positive(price):raise ValueError('INVALID_PRICE')
    p=math.ceil(price/book.tick(price))*book.tick(price)
    return int(math.ceil(p/book.tick(p))*book.tick(p))


def unbroken_daily_stop(history,atr=None,max_age_sessions=20):
    """Freeze a pivot buffer at confirmation; check every subsequent low.

    A later ATR cannot rescue an invalidated pivot. No older pivot is
    substituted after the most recently confirmed pivot has failed.
    """
    if len(history)<5:return None
    pivots=[]
    for i in range(max(2,len(history)-max_age_sessions),len(history)-2):
        lo=history[i]['low']
        if lo<min(b['low'] for b in history[i-2:i]) and lo<=min(b['low'] for b in history[i+1:i+3]):
            pivots.append(i)
    if not pivots:return None
    i=pivots[-1];confirmed=i+2;a=history[confirmed].get('atr14')
    if not book.finite_positive(a):return None
    raw=history[i]['low']-.15*a
    if raw<=0:return None
    stop=book.floor_tick(raw)
    if any(b['low']<=stop for b in history[confirmed+1:]):return None
    if stop>=history[-1]['close']:return None
    previous=pivots[-2] if len(pivots)>1 else None
    return dict(stop=stop,pivot_date=history[i]['date'],pivot_low=history[i]['low'],
                confirmation_date=history[confirmed]['date'],atr_at_confirmation=a,
                known_through=history[-1]['date'],unbroken_through_D=True,
                higher_low_vs_previous_confirmed=bool(previous is not None and
                    history[i]['low']>history[previous]['low']))


def _sized_order(p,policy,costs,equity,cash,cap):
    if not book.finite_positive(cap) or cap<=p['stop']:return None,'LIMIT_BELOW_DAILY_STRUCTURE'
    cap=book.floor_tick(cap)
    if policy.require_rr2:
        rr_cap=book.maximum_entry_rr2(p['stop'],p['signal'].get('resistance'),costs)
        if rr_cap is None:return None,'MISSING_DATED_RESISTANCE'
        cap=min(cap,book.floor_tick(rr_cap))
    if cap<=p['stop']:return None,'NO_COST_ADJUSTED_ENTRY_GEOMETRY'
    qty=book.share_qty(equity,cash,cap,p['stop'],costs,policy.risk_fraction)
    if qty<1:return None,'LESS_THAN_ONE_PRECOMMITTED_SHARE'
    p=dict(p,cap=cap,qty=qty,planned_risk_krw=qty*(cap*(1+costs.buy)-p['stop']*(1-costs.sell)),
           target=ceil_tick(cap*1.10))
    return p,None


class Handlers:
    @staticmethod
    def make_pending(signal,policy,costs,equity,cash,idx):
        if policy.D0_affordability_alternative:
            options=signal.get('D_ranked_candidates',[signal])
            if any(c['asof']!=signal['asof'] for c in options):
                raise ValueError('D0_ALTERNATIVE_CONTAINS_DIFFERENT_DATE')
            for priority,candidate in enumerate(options):
                p,why=Handlers._make_one(candidate,policy,costs,equity,cash,idx)
                if p is not None:
                    p['D0_priority']=priority+1
                    return p,('D0_KNOWN_CASH_ALTERNATIVE_FROZEN' if priority else None)
                if why!='LESS_THAN_ONE_PRECOMMITTED_SHARE':return None,why
            return None,'NO_AFFORDABLE_D0_CANDIDATE'
        return Handlers._make_one(signal,policy,costs,equity,cash,idx)

    @staticmethod
    def _make_one(signal,policy,costs,equity,cash,idx):
        if signal.get('requires_confirmed_pivot') is True and not signal.get('confirmed_pivot_evidence'):
            return None,'NO_UNBROKEN_CONFIRMED_PIVOT'
        c,s,a=(float(signal[k]) for k in ('signal_close','stopD','atr14'))
        if not book.finite_positive(c,s,a) or s>=c:return None,'BAD_D_GEOMETRY'
        if policy.failure_close_exit and not book.finite_positive(signal.get('signal_low')):
            return None,'NO_DATED_REBOUND_LOW_FOR_CLOSE_FAILURE_RULE'
        p=dict(signal=dict(signal),stop=book.floor_tick(s),submitted_idx=idx,
               expires_idx=idx+(1 if policy.entry=='REST_1D' else 2),
               order_decision_date=signal['asof'],confirmed=False,
               simulated_fill_allowed=signal.get('simulated_fill_allowed',True))
        if policy.entry=='CONFIRM_THEN_REST':
            return p,None
        return _sized_order(p,policy,costs,equity,cash,c-policy.retest_atr*a)

    @staticmethod
    def pending_step(pending,bar,idx,policy,costs,equity,cash):
        p=dict(pending);age=idx-p['submitted_idx'];s=p['signal']
        if age<1:raise ValueError('SAME_DAY_ENTRY_FORBIDDEN')
        if idx>p['expires_idx']:return None,None,'ORDER_EXPIRED_BEFORE_SESSION'
        if policy.entry=='CONFIRM_THEN_REST' and age==1:
            span=bar['high']-bar['low']
            valid=(bar['low']>p['stop'] and bar['low']<=s['signal_close']+.15*s['atr14']
                   and span>0 and bar['close']>=max(bar['open'],s['signal_close'])
                   and (bar['close']-bar['low'])/span>=.65)
            if not valid:return None,None,'NO_COMPLETED_D1_CONFIRMATION'
            atr=bar.get('atr14') or s['atr14']
            new,reason=_sized_order(p,policy,costs,equity,cash,
                                   bar['close']-policy.confirmation_retest_atr*atr)
            if reason:return None,None,reason
            new.update(confirmed=True,order_decision_date=bar['date'],last_seen_close=bar['close'])
            return None,new,'D1_CLOSE_CREATED_D2_RESTING_ORDER'
        if policy.entry=='CONFIRM_THEN_REST' and not p['confirmed']:
            raise ValueError('D2_ORDER_WITHOUT_D1_CONFIRMATION')
        prior=p.get('last_seen_close',s['signal_close'])
        if not .65<=bar['open']/prior<=1.35:
            return None,None,'HALT_UNVERIFIED_ACTION_OR_PRICE_GAP_WHILE_PENDING'
        p['last_seen_close']=bar['close']
        at_open=bar['open']<=p['cap']
        touched=(at_open or bar['low']<=p['cap']-policy.limit_penetration_ticks*book.tick(p['cap']))
        if touched and p['simulated_fill_allowed'] is True:
            px=bar['open'] if at_open else p['cap']
            fill=dict(price=px,qty=p['qty'],stop=p['stop'],cap=p['cap'],
                precommitted_risk_krw=p['planned_risk_krw'],target=p['target'],at_open=at_open,signal=s,
                order_decision_date=p['order_decision_date'],entry_idx=idx,entry_date=bar['date'])
            return fill,None,('RESTING_OPEN_BELOW_STOP_FILL_PROXY' if px<=p['stop']
                               else 'RESTING_LIMIT_FILL_PROXY')
        if bar['close']<=p['stop']:return None,None,'D_CLOSE_STRUCTURE_BROKEN_CANCEL_REMAINDER'
        if idx>=p['expires_idx']:
            return None,None,('SIMULATED_MISSED_ORDER_EXPIRED' if not p['simulated_fill_allowed']
                              else 'LIMIT_EXPIRED_UNFILLED')
        return None,p,'RESTING_ORDER_STILL_UNFILLED'

    @staticmethod
    def exit_step(position,bar,idx,policy):
        p=dict(position);age=idx-p['entry_idx']+1;stop=p['active_stop']
        def stop_fill(px):return px*(1-policy.extra_stop_slippage),'PRIOR_DAILY_STOP_GAP_AWARE',p
        if bar['open']<=stop:return stop_fill(bar['open'])
        if p.get('exit_next_open'):return bar['open'],p.get('next_open_reason','WEAK_D5_EXIT_D6_OPEN'),p
        if policy.exit=='TARGET10_D12' and bar['open']>=p['target']:
            return bar['open'],'PRECOMMITTED_TARGET_OPEN_PROXY',p
        if bar['low']<=stop:return stop_fill(stop)
        if policy.exit=='TARGET10_D12' and (idx>p['entry_idx'] or p['at_open']):
            if bar['high']>=p['target']+book.tick(p['target']):
                return p['target'],'TARGET_TRADED_THROUGH_PROXY',p
        maxdays=policy.fixed_exit_sessions if policy.exit=='STRUCT_D5' else 12
        if age>=maxdays:return bar['close'],'PREPLANNED_HORIZON_CLOSE_PROXY',p
        if policy.failure_close_exit:
            failed_level=p['signal']['signal_low']-.1*p['signal']['atr14']
            if bar['close']<failed_level and bar['close']<p['price']:
                p['exit_next_open']=True
                p['next_open_reason']='FAILED_REBOUND_CLOSE_EXIT_NEXT_OPEN'
        p['peak_close']=max(p['peak_close'],bar['close'])
        if policy.exit=='STRUCT_ATR_D12':
            price_r=p['price']-p['stop']
            if bar['close']>=p['price']+price_r:p['trail_active']=True
            atr=bar.get('atr14')
            if p['trail_active'] and book.finite_positive(atr):
                candidate=p['peak_close']-policy.trail_atr*atr
                if candidate>0:p['active_stop']=max(stop,book.floor_tick(candidate))
            if age==5 and bar.get('ma5') is not None:
                p['exit_next_open']=bool(bar['close']<p['price']+price_r and bar['close']<bar['ma5'])
        return None,None,p


def replay(sessions,prices,signals,policy=Policy(),costs=book.BASE_COST):
    r=book.replay(sessions,prices,signals,policy,costs,handlers=Handlers)
    r['summary']['schema']='C3_V638_PRECOMMITTED_RESTING_LIMIT_PAPER_ONLY'
    r['summary']['post_open_gap_cancellation_used']=False
    r['summary']['intraday_queue_or_fill_verified']=False
    for t in r['trades']:
        t['unwanted_open_fill_through_structure']=t['entry']<=t['stop']
        s=next(s for s in signals if s['asof']==t['asof'])
        options=s.get('D_ranked_candidates',[s])
        t['D0_affordability_rank']=next((i+1 for i,c in enumerate(options) if c['ticker']==t['ticker']),None)
    return r
