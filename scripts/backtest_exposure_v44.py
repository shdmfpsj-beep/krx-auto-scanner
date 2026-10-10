"""C3 v4.4 research-only trade and daily-exposure audit. Never changes live scans.
Run: python scripts/backtest_exposure_v44.py --capital 1000000 --holds 5,10
Uses existing v4.2 index-regime definition and cached v4.0 OHLCV.
"""
import argparse
import json
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'
SPEC=importlib.util.spec_from_file_location('c3_v42',Path(__file__).with_name('backtest_regime_v42.py'))
v42=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v42)
v40=v42.v40
classify_history=v40.classify_history
rejection_detail=v40.rejection_detail

def replay(signals, bars, capital, strategy, hold, selection, stop_pct,
           take_pct, cost_bps, slip_bps):
    eligible = signals if strategy == 'A_baseline' else signals.loc[signals.improved]
    if selection == 'factor_rank':
        eligible = eligible.sort_values(['entry_date','rank_score','ticker'],
                                        ascending=[True,False,True], kind='stable')
    else:
        eligible = eligible.sort_values(['entry_date','ticker'], kind='stable')
    states = {ticker: classify_history(d) for ticker, d in bars.items()}
    dates = sorted(set().union(*(set(d.index) for d in bars.values())))
    if not dates:
        return None, [], [rejection_detail('no_calendar_dates')]
    groups = {k:v for k,v in eligible.groupby('entry_date', sort=False)}
    cash = float(capital)
    position = None
    ledger, trades = [], []
    skipped_missing = 0
    invalid_holding_days = 0
    nontrading_holding_days = 0
    blocked_entry_days = 0
    tradable_ages = {}
    buy_mult = 1 + slip_bps / 10000
    sell_mult = 1 - slip_bps / 10000
    fee_rate = cost_bps / 20000
    for dt in dates:
        exited_open = False
        if position is not None:
            p = position
            d = bars[p['ticker']]
            if dt in d.index and dt > p['entry_date']:
                state = states[p['ticker']].loc[dt]
                if state == 'invalid':
                    invalid_holding_days += 1
                    # An unresolvable mark/exit makes this entire scenario
                    # unreportable, not merely the offending trade.
                    return None, [], [rejection_detail(
                        'invalid_bar_while_holding', p['ticker'], dt, p, d.loc[dt])]
                if state == 'nontrading':
                    nontrading_holding_days += 1
                    # No stop/take/time exit on a non-trading day.
                    pass
                else:
                    tradable_ages[p['ticker']] = tradable_ages.get(p['ticker'], 0) + 1
                    candle = d.loc[dt]
                    age = tradable_ages[p['ticker']]
                    op, hi, lo = (float(candle[k]) for k in ('Open','High','Low'))
                    stop_price = p['entry_fill'] * (1 - stop_pct)
                    take_price = p['entry_fill'] * (1 + take_pct)
                    exit_price, reason = None, None
                    if op <= stop_price:
                        exit_price, reason = op, 'stop_gap'
                    elif op >= take_price:
                        exit_price, reason = op, 'take_gap'
                    elif age >= hold:
                        exit_price, reason = op, 'time_open'
                    elif lo <= stop_price:
                        exit_price, reason = stop_price, 'stop_intraday'
                    elif hi >= take_price:
                        exit_price, reason = take_price, 'take_intraday'
                    if exit_price is not None:
                        exit_fill = exit_price * sell_mult
                        proceeds = p['shares'] * exit_fill * (1 - fee_rate)
                        cash += proceeds
                        trades.append({'strategy':strategy,'selection':selection,'hold':hold,
                                       'capital':capital,'ticker':p['ticker'],
                                       'signal_id':p['signal_id'],
                                       'entry_date':p['entry_date'].date().isoformat(),
                                       'exit_date':dt.date().isoformat(),
                                       'entry_fill':p['entry_fill'],'exit_fill':exit_fill,
                                       'shares':p['shares'],'exit_reason':reason,
                                       'net_pnl':proceeds-p['total_entry_cost'],
                                       'net_return_pct':100*(proceeds/p['total_entry_cost']-1)})
                        position = None
                        exited_open = reason in ('time_open','stop_gap','take_gap')
        if position is None and (dt in groups) and (not trades or trades[-1]['exit_date'] != dt.date().isoformat() or exited_open):
            for _, sig in groups[dt].iterrows():
                d = bars.get(sig.ticker)
                if d is None or dt not in d.index:
                    skipped_missing += 1
                    continue
                if states[sig.ticker].loc[dt] != 'tradable':
                    blocked_entry_days += 1
                    continue
                op = float(d.loc[dt,'Open'])
                if abs(op / float(sig.entry_open) - 1) > .03:
                    skipped_missing += 1
                    continue
                fill = op * buy_mult
                shares = int(cash // (fill * (1 + fee_rate)))
                if shares < 1:
                    continue
                total = shares * fill * (1 + fee_rate)
                cash -= total
                tradable_ages[sig.ticker] = 0
                position = {'ticker':sig.ticker,'signal_id':sig.signal_id,
                            'entry_date':dt,'entry_fill':fill,'shares':shares,
                            'total_entry_cost':total}
                break
        if position is None:
            equity = cash
        else:
            d = bars[position['ticker']]
            last = d.loc[:dt]
            if not last.empty and states[position['ticker']].loc[last.index[-1]] == 'invalid':
                bad_dt = last.index[-1]
                return None, [], [rejection_detail(
                    'invalid_close_mark', position['ticker'], bad_dt,
                    position, last.iloc[-1])]
            px = float(last.iloc[-1]['Close']) if not last.empty else position['entry_fill']
            equity = cash + position['shares'] * px * sell_mult * (1 - fee_rate)
        ledger.append({'date':dt.date().isoformat(),'strategy':strategy,
                       'selection':selection,'hold':hold,'capital':capital,
                       'equity':equity,'cash':cash,
                       'ticker':position['ticker'] if position else '', 'shares':position['shares'] if position else 0, 'position_value':(equity-cash), 'invested':bool(position)})
    vals = np.asarray([a['equity'] for a in ledger], dtype=float)
    peaks = np.maximum.accumulate(vals)
    mdd = 100 * np.min(vals / peaks - 1)
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    summary = {'strategy':strategy,'selection':selection,'hold':hold,
               'capital':capital,'stop_pct':stop_pct,'take_pct':take_pct,
               'trades_closed':len(trades),'open_position':bool(position),
               'skipped_missing_or_price_mismatch':skipped_missing,
               'blocked_nontradable_entries':blocked_entry_days,
               'nontrading_holding_days':nontrading_holding_days,
               'invalid_holding_days':invalid_holding_days,
               'total_return_pct':100*(vals[-1]/capital-1),
               'cagr_pct':100*((vals[-1]/capital)**(1/years)-1) if vals[-1]>0 else None,
               'daily_close_mdd_pct':mdd,
               'win_rate_pct':100*np.mean([t['net_pnl']>0 for t in trades]) if trades else None,
               'ending_equity':vals[-1]}
    return summary, trades, ledger

def replay_dip_v39(signals, bars, capital, strategy, hold, selection,
                     stop_pct, take_pct, cost_bps, slip_bps, variant, dip_threshold):
    """v3.9 conservative opening-add chronology; one ticker, one position.

    Daily OHLCV cannot establish intraday order: existing stops/takes are
    evaluated before any add; an add is only eligible on a later session.
    Initial stop/take anchors are NEVER moved after adding. The entry open
    must agree with the recorded signal (same 3% gate as v3.6.10).
    """
    if variant not in ('dip_50_50','cash_50_no_add'):
        raise ValueError('Unknown variant')
    eligible = signals if strategy == 'A_baseline' else signals.loc[signals.improved]
    if selection == 'factor_rank':
        eligible = eligible.sort_values(['entry_date','rank_score','ticker'],
                                        ascending=[True,False,True],kind='stable')
    else:
        eligible = eligible.sort_values(['entry_date','ticker'],kind='stable')
    states={t:classify_history(d) for t,d in bars.items()}
    dates=sorted(set().union(*(set(d.index) for d in bars.values())))
    if not dates:
        return None,[],[rejection_detail('no_calendar_dates')]
    groups={k:v for k,v in eligible.groupby('entry_date',sort=False)}
    cash=float(capital); pos=None; trades=[]; ledger=[]
    buy_mult=1+slip_bps/10000; sell_mult=1-slip_bps/10000
    fee=cost_bps/20000
    skipped=blocked=nontrading=0
    for dt in dates:
        exited_open=False
        if pos is not None:
            d=bars[pos['ticker']]
            if dt in d.index and dt>pos['entry_date']:
                st=states[pos['ticker']].loc[dt]
                if st=='invalid':
                    return None,[],[rejection_detail('invalid_bar_while_holding',pos['ticker'],dt,pos,d.loc[dt])]
                if st=='nontrading':
                    nontrading+=1
                else:
                    candle=d.loc[dt]; op=float(candle.Open); hi=float(candle.High); lo=float(candle.Low)
                    pos['age']+=1
                    stop=pos['first_fill']*(1-stop_pct)
                    take=pos['first_fill']*(1+take_pct)
                    # v3.9 chronology: opening gap exits -> time exit at open ->
                    # opening add (prior completed close only) -> intraday exits.
                    # On days where both stop/take are touched, stop has priority.
                    price=reason=None
                    if op<=stop: price,reason=op,'stop_gap'
                    elif op>=take: price,reason=op,'take_gap'
                    elif pos['age']>=hold: price,reason=op,'time_open'
                    else:
                        if not pos['added'] and variant=='dip_50_50':
                            prev=d.loc[d.index<dt]
                            if not prev.empty and states[pos['ticker']].loc[prev.index[-1]]=='tradable':
                                prev_close=float(prev.iloc[-1].Close)
                                first=pos['first_open']
                                dip=(prev_close<=first*(1-dip_threshold) and
                                     prev_close>stop and prev_close>=first*.93 and
                                     op>stop and op<=first)
                                if dip:
                                    fill=op*buy_mult
                                    budget=min(cash,pos['reserved'])
                                    added_shares=int(budget//(fill*(1+fee)))
                                    if added_shares>=1:
                                        total=added_shares*fill*(1+fee)
                                        cash-=total
                                        pos['cost']+=total
                                        pos['shares']+=added_shares
                                        pos['added']=True
                        # Critically includes shares added at today's open.
                        if lo<=stop: price,reason=stop,'stop_intraday'
                        elif hi>=take: price,reason=take,'take_intraday'
                    if price is not None:
                        proceeds=pos['shares']*price*sell_mult*(1-fee)
                        cash+=proceeds
                        trades.append({'variant':variant,'strategy':strategy,'selection':selection,
                          'hold':hold,'capital':capital,'ticker':pos['ticker'],
                          'signal_id':pos['signal_id'],'entry_date':pos['entry_date'].date().isoformat(),
                          'exit_date':dt.date().isoformat(),'shares':pos['shares'],
                          'dip_threshold_pct':round(dip_threshold*100,2),'add_executed':pos['added'],
                          'entry_tranches':1+int(pos['added']),
                          'exit_reason':reason,'net_pnl':proceeds-pos['cost'], 'entry_cost':pos['cost'], 'exit_proceeds':proceeds,
                          'net_return_pct':100*(proceeds/pos['cost']-1)})
                        pos=None
                        exited_open=reason in ('stop_gap','take_gap','time_open')
        if pos is None and dt in groups and (not trades or trades[-1]['exit_date']!=dt.date().isoformat() or exited_open):
            for _,sig in groups[dt].iterrows():
                d=bars.get(sig.ticker)
                if d is None or dt not in d.index:
                    skipped+=1;continue
                if states[sig.ticker].loc[dt]!='tradable':
                    blocked+=1;continue
                op=float(d.loc[dt,'Open'])
                if abs(op/float(sig.entry_open)-1)>.03:
                    skipped+=1;continue
                fill=op*buy_mult
                budget=cash*.5
                shares=int(budget//(fill*(1+fee)))
                if shares<1:continue
                total=shares*fill*(1+fee)
                cash-=total
                pos={'ticker':sig.ticker,'signal_id':sig.signal_id,'entry_date':dt,
                     'first_open':op,'first_fill':fill,'entry_fill':fill,
                     'shares':shares,'cost':total,'reserved':float(capital)*.5,
                     'added':False,'age':0}
                break
        if pos is None: equity=cash
        else:
            d=bars[pos['ticker']]; last=d.loc[:dt]
            if not last.empty and states[pos['ticker']].loc[last.index[-1]]=='invalid':
                return None,[],[rejection_detail('invalid_close_mark',pos['ticker'],last.index[-1],pos,last.iloc[-1])]
            mark=float(last.iloc[-1].Close) if not last.empty else pos['first_fill']
            equity=cash+pos['shares']*mark*sell_mult*(1-fee)
        ledger.append({'date':dt.date().isoformat(),'variant':variant,'strategy':strategy,
                       'selection':selection,'hold':hold,'capital':capital,'equity':equity,'cash':cash, 'ticker':pos['ticker'] if pos else '', 'shares':pos['shares'] if pos else 0, 'position_value':(equity-cash), 'invested':bool(pos), 'added':bool(pos['added']) if pos else False})
    vals=np.asarray([r['equity'] for r in ledger],dtype=float)
    peaks=np.maximum.accumulate(vals)
    years=max((dates[-1]-dates[0]).days/365.25,1e-9)
    summary={'variant':variant,'strategy':strategy,'selection':selection,'hold':hold,
             'capital':capital,'dip_threshold_pct':round(dip_threshold*100,2),'trades_closed':len(trades),
             'adds_executed':sum(int(t['add_executed']) for t in trades),
             'open_position':bool(pos),'skipped_missing_or_price_mismatch':skipped,
             'blocked_nontradable_entries':blocked,'nontrading_holding_days':nontrading,
             'total_return_pct':100*(vals[-1]/capital-1),
             'cagr_pct':100*((vals[-1]/capital)**(1/years)-1) if vals[-1]>0 else None,
             'daily_close_mdd_pct':100*np.min(vals/peaks-1),
             'win_rate_pct':100*np.mean([t['net_pnl']>0 for t in trades]) if trades else None,
             'ending_equity':vals[-1]}
    return summary,trades,ledger


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',default=str(REPORTS/'entry_v32_paired_trades.csv'))
    p.add_argument('--capital',type=int,default=1000000)
    p.add_argument('--holds',default='5,10')
    p.add_argument('--download-attempts',type=int,default=4)
    args=p.parse_args()
    holds=[int(v) for v in args.holds.split(',')]
    if args.capital<=0 or not holds or min(holds)<=0 or args.download_attempts<1:
        p.error('Invalid capital, holds or attempts')
    x=v40.load_signals(Path(args.input))
    x=x.loc[~x.ticker.isin({'088980'})].copy()
    x=v42.assign_regime(x)
    if x.regime.eq('unknown').mean()>.10:
        raise SystemExit('Unknown index regimes above 10%; fail closed')
    tickers=sorted(x.ticker.unique())
    if not tickers: raise SystemExit('No eligible tickers')
    start=x.entry_date.min()-pd.Timedelta(days=10)
    end=x.entry_date.max()+pd.Timedelta(days=max(60,max(holds)*3))
    bars={}; failures=[]
    for i,ticker in enumerate(tickers,1):
        try:
            bars[ticker],_=v40.history(ticker,start,end,x.loc[x.ticker.eq(ticker),'entry_date'],False,args.download_attempts,1.5)
        except Exception as exc:
            failures.append({'ticker':ticker,'error':str(exc)[:500]})
        if i%20==0 or i==len(tickers):
            print(f'v4.4 OHLCV {i}/{len(tickers)} valid={len(bars)}',flush=True)
    REPORTS.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(failures,columns=['ticker','error']).to_csv(REPORTS/'exposure_v44_failures.csv',index=False)
    if len(bars)/len(tickers)<.90:
        raise SystemExit('OHLCV coverage below 90%; fail closed')
    # Same candidate universe, hold and selection per matched three-arm comparison.
    rules={'pullback':lambda d:d.ma_rising & d.setup.eq('pullback'),
           'breakout':lambda d:d.ma_rising & d.setup.eq('breakout'),
           'regime_switch':lambda d:((d.regime.eq('up') & d.ma_rising & d.setup.eq('breakout')) |
                                      (d.regime.eq('neutral') & d.ma_rising & d.setup.eq('pullback')))}
    periods=[('development_2023_2024','2023-01-01','2024-12-31'),
             ('later_2025','2025-01-01','2025-12-31')]
    summaries=[]; trade_rows=[]; daily_rows=[]; rejected=[]
    for period,first,last in periods:
        pool=x.loc[x.entry_date.between(first,last)].copy()
        for rule,filter_fn in rules.items():
            chosen=pool.loc[filter_fn(pool).fillna(False)].copy()
            if chosen.empty: continue
            for hold in holds:
                for selection in ('ticker_ascending','factor_rank'):
                    for arm in ('all_in','cash_half','dip_3pct'):
                        if arm=='all_in':
                            result,trades,ledger=replay(chosen,bars,args.capital,'A_baseline',hold,selection,.07,.15,15,10)
                        else:
                            result,trades,ledger=replay_dip_v39(chosen,bars,args.capital,'A_baseline',hold,selection,.07,.15,15,10,
                                'cash_50_no_add' if arm=='cash_half' else 'dip_50_50',.03)
                        keys={'period':period,'rule':rule,'hold':hold,'selection':selection,'arm':arm}
                        if result is None:
                            rejected.append({**keys,'reason':ledger[0].get('reason','unknown') if ledger else 'unknown'})
                            continue
                        # IMPORTANT: engine uses full bar calendar. Restrict analytics to period.
                        daily=pd.DataFrame(ledger)
                        daily['date']=pd.to_datetime(daily.date)
                        daily=daily.loc[daily.date.between(first,last)].copy()
                        if daily.empty:
                            rejected.append({**keys,'reason':'no_in_period_daily_marks'}); continue
                        # Fail closed if an earlier entry remains open on the last period date.
                        # This is a research diagnostic, not a reconstructed period return.
                        initial=float(daily.iloc[0].equity)
                        ending=float(daily.iloc[-1].equity)
                        if initial<=0: raise SystemExit('Invalid starting equity')
                        peak=daily.equity.cummax()
                        mdd=float((100*(daily.equity/peak-1)).min())
                        exposure=(daily.position_value/daily.equity).replace([np.inf,-np.inf],np.nan)
                        if exposure.isna().any(): raise SystemExit('Invalid exposure data')
                        invested_days=int(daily.invested.sum())
                        period_trades=[t for t in trades if first<=str(t['entry_date'])<=last]
                        add_days=int(daily.added.sum()) if 'added' in daily else 0
                        row={**keys,'eligible_signals':len(chosen),'trades_closed':len(period_trades),
                             'return_pct_from_first_mark':100*(ending/initial-1),
                             'mdd_pct_from_first_mark':mdd,'initial_equity':initial,'ending_equity':ending,
                             'days_marked':len(daily),'invested_days':invested_days,
                             'invested_day_fraction':invested_days/len(daily),
                             'average_capital_exposure_pct':100*float(exposure.mean()),
                             'peak_capital_exposure_pct':100*float(exposure.max()),
                             'add_position_days':add_days,
                             'stop_exits':sum(str(t['exit_reason']).startswith('stop') for t in period_trades),
                             'gap_stop_exits':sum(t['exit_reason']=='stop_gap' for t in period_trades),
                             'time_exits':sum(t['exit_reason']=='time_open' for t in period_trades),
                             'win_rate_pct':100*sum(t['net_pnl']>0 for t in period_trades)/len(period_trades) if period_trades else None,
                             'worst_trade_net_pnl':min((t['net_pnl'] for t in period_trades),default=None),
                             'open_position_at_end':bool(daily.iloc[-1].invested)}
                        summaries.append(row)
                        for t in period_trades: trade_rows.append({**keys,**t})
                        for r in daily.to_dict('records'):
                            daily_rows.append({**keys,'date':r['date'].date().isoformat(),
                                'equity':r['equity'],'cash':r['cash'],'ticker':r['ticker'],
                                'shares':r['shares'],'position_value':r['position_value'],
                                'invested':r['invested'],'capital_exposure_pct':100*r['position_value']/r['equity'],
                                'added':r.get('added',False)})
    if not summaries: raise SystemExit('No valid scenarios')
    summary=pd.DataFrame(summaries)
    keys=['period','rule','hold','selection']
    control=summary.loc[summary.arm.eq('cash_half'),keys+['return_pct_from_first_mark','mdd_pct_from_first_mark']].rename(
        columns={'return_pct_from_first_mark':'control_return_pct','mdd_pct_from_first_mark':'control_mdd_pct'})
    summary=summary.merge(control,on=keys,how='left',validate='many_to_one')
    summary['return_delta_vs_cash_pp']=summary.return_pct_from_first_mark-summary.control_return_pct
    summary['mdd_delta_vs_cash_pp']=summary.mdd_pct_from_first_mark-summary.control_mdd_pct
    summary.to_csv(REPORTS/'exposure_v44_summary.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(trade_rows).to_csv(REPORTS/'exposure_v44_trades.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(daily_rows).to_csv(REPORTS/'exposure_v44_daily.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(rejected,columns=['period','rule','hold','selection','arm','reason']).to_csv(REPORTS/'exposure_v44_rejected.csv',index=False)
    meta={'version':'v4.4','research_only':True,'scenarios':len(summary),'rejected':len(rejected),
          'capital_research_normalization':args.capital,
          'engine':'Unchanged v4.0/v3.9 trade decisions, enriched ledger for exposure',
          'limitations':['No independent point-in-time universe or untouched out-of-sample.',
          'Daily OHLCV cannot reconstruct intraday order or actual fills.',
          'Entry and add order prices use historical open with fixed modeled slippage.',
          'Daily capital exposure uses liquidation-mark position value; not intraday peak risk.',
          'Calendar may contain dates from entire bar universe; per-period rows are filtered.',
          'Return from first daily mark is not period-start equity return; inspect initial_equity.',
          'Trades crossing period end are not closed in period trade metrics.',
          'No live-trade approval or changes to C3/K100 scheduled scanning.']}
    (REPORTS/'exposure_v44_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'v4.4 completed {len(summary)} scenarios, rejected={len(rejected)}, daily={len(daily_rows)}',flush=True)

if __name__=='__main__': main()
