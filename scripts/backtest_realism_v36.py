"""C3 v3.6.6 research-only daily OHLCV one-position replay.
Usage: python scripts/backtest_realism_v36.py
Requires reports/entry_v32_paired_trades.csv and FinanceDataReader.
NOT point-in-time universe; never use for live trade approval.
"""
import argparse
import json
import random
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
CACHE = REPORTS / 'v36_ohlcv_cache'


def load_signals(path):
    raw = pd.read_csv(path, dtype={'ticker': str, 'signal_id': str})
    needed = {'signal_id','ticker','signal_date','entry_date','entry_open','hold',
              'setup','ma_rising','ret60','distance_ma20','rvol20','ret20'}
    if missing := needed - set(raw.columns):
        raise ValueError(f'Missing columns: {sorted(missing)}')
    x = raw.loc[raw.hold.eq(1)].copy()
    if x.empty:
        raise ValueError('No hold=1 signal rows')
    if x.signal_id.duplicated().any():
        raise ValueError('Duplicate signal ids')
    for col in ('signal_date','entry_date'):
        x[col] = pd.to_datetime(x[col], errors='raise').dt.normalize()
    for col in ('entry_open','ret60','distance_ma20','rvol20','ret20'):
        x[col] = pd.to_numeric(x[col], errors='coerce')
    x['ma_rising'] = x.ma_rising.astype(str).str.lower().eq('true')
    x['improved'] = (x.setup.eq('breakout') & x.ma_rising &
                     x.ret60.lt(.60) & x.distance_ma20.lt(.15))
    x = x.loc[(x.entry_open > 0) & (x.signal_date < x.entry_date)].copy()
    x['rank_score'] = (np.clip(x.rvol20.fillna(0), 0, 5) * 2 +
                       np.clip(x.ret20.fillna(0), -.5, .5) * 4 -
                       np.clip(x.distance_ma20.fillna(0), -.5, .5) * 2)
    return x.sort_values(['entry_date','signal_id'], kind='stable')


def _normalize_bars(d):
    if d is None or d.empty:
        raise ValueError('No OHLCV')
    d = d.copy()
    d.index = pd.to_datetime(d.index, errors='raise').normalize()
    d.index.name = 'Date'
    d = d.sort_index()
    for col in ('Open','High','Low','Close','Volume'):
        if col not in d:
            raise ValueError(f'Missing {col}')
        d[col] = pd.to_numeric(d[col], errors='coerce')
    return d


def classify_history(d):
    """Retain raw dates. Never repair a quoted price or fabricate an execution."""
    if d.empty or d.index.has_duplicates:
        raise ValueError('empty_or_duplicate_history')
    v = d[['Open','High','Low','Close']]
    finite = v.notna().all(axis=1) & np.isfinite(v).all(axis=1)
    valid = (finite & (v > 0).all(axis=1) &
             (d.High >= d[['Open','Close','Low']].max(axis=1)) &
             (d.Low <= d[['Open','Close','High']].min(axis=1)))
    # Non-trading candidate, NOT an asserted exchange suspension.
    # Positive close is usable only as a stale mark; never for execution.
    inactive = (finite & d.Open.eq(0) & d.High.eq(0) & d.Low.eq(0) &
                d.Close.gt(0) & d.Volume.eq(0))
    state = pd.Series('invalid', index=d.index, dtype='object')
    state.loc[inactive] = 'nontrading'
    state.loc[valid] = 'tradable'
    return state


def _covers_required_signals(d, entries, end):
    if d.empty:
        return False, 'empty_history'
    needed = set(pd.DatetimeIndex(pd.to_datetime(entries, errors='raise')).normalize())
    missing = sorted(needed - set(d.index))
    if missing:
        return False, f'missing_entry_bars:{len(missing)} first={missing[0].date()}'
    # A nontradable entry does not invalidate the entire ticker, but must be
    # separately counted and prohibited from opening a position.
    return True, ''


def assess_history(d, entries, end):
    states = classify_history(d)
    ok, reason = _covers_required_signals(d, entries, end)
    if not ok:
        raise ValueError(reason)
    if not states.eq('tradable').any():
        raise ValueError('no_tradable_bars')
    return states


def history(ticker, start, end, entries, refresh=False, attempts=4, delay=1.5):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f'{ticker}.csv'
    issues = []
    if path.exists() and not refresh:
        try:
            cached = _normalize_bars(pd.read_csv(path, parse_dates=['Date']).set_index('Date'))
            cached = cached.loc[(cached.index >= start) & (cached.index <= end)]
            assess_history(cached, entries, end)
            return cached, 'cache'
        except Exception as exc:
            issues.append(f'cache_read_error:{type(exc).__name__}:{exc}')
    for attempt in range(1, attempts + 1):
        try:
            # FDR's end date is exclusive for some providers; add one day.
            end_query = (end + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            d = _normalize_bars(fdr.DataReader(ticker, start.strftime('%Y-%m-%d'), end_query))
            d = d.loc[(d.index >= start) & (d.index <= end)]
            assess_history(d, entries, end)
            # Atomic cache replacement avoids corrupting a usable file.
            temp = path.with_suffix('.tmp')
            d.to_csv(temp)
            temp.replace(path)
            time.sleep(delay)
            return d, f'download_attempt_{attempt}'
        except Exception as exc:
            issues.append(f'attempt_{attempt}:{type(exc).__name__}:{str(exc)[:150]}')
            if attempt < attempts:
                wait = min(30, delay * (2 ** (attempt - 1))) + random.uniform(0, .5)
                print(f'RETRY {ticker} {attempt}/{attempts} wait={wait:.1f}s: {str(exc)[:100]}', flush=True)
                time.sleep(wait)
    raise RuntimeError(' | '.join(issues)[-900:])


def rejection_detail(reason, ticker='', dt=None, position=None, candle=None):
    """Audit a rejected scenario without altering the execution or acceptance rules."""
    p = position or {}
    row = {'reason': reason, 'ticker': str(ticker),
           'failure_date': dt.date().isoformat() if dt is not None else '',
           'signal_id': str(p.get('signal_id', '')),
           'position_entry_date': p['entry_date'].date().isoformat()
           if p.get('entry_date') is not None else '',
           'shares': p.get('shares', ''), 'entry_fill': p.get('entry_fill', '')}
    for col in ('Open', 'High', 'Low', 'Close', 'Volume'):
        row[col] = candle.get(col, '') if candle is not None else ''
    return row


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
                       'ticker':position['ticker'] if position else ''})
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



def apply_verified_bars(bars, verified_path):
    """Use independently verified prices only; never infer or round corrections.

    Optional CSV columns: ticker,date,Open,High,Low,Close,Volume,source,source_url.
    All supplied rows must match an existing invalid source bar. The original
    OHLCV is retained in the audit file. Source provenance is mandatory.
    """
    columns = ['ticker','date','source','source_url','original_Open','original_High',
               'original_Low','original_Close','original_Volume','verified_Open',
               'verified_High','verified_Low','verified_Close','verified_Volume','status']
    audit = []
    if not verified_path:
        return audit
    path = Path(verified_path)
    if not path.is_file():
        raise ValueError(f'Verified source file not found: {path}')
    frame = pd.read_csv(path, dtype={'ticker':str})
    required = {'ticker','date','Open','High','Low','Close','Volume','source','source_url'}
    if missing := required - set(frame.columns):
        raise ValueError(f'Verified CSV missing columns: {sorted(missing)}')
    frame['ticker'] = frame.ticker.str.zfill(6)
    frame['date'] = pd.to_datetime(frame.date, errors='raise').dt.normalize()
    if frame.duplicated(['ticker','date']).any():
        raise ValueError('Duplicate verified ticker/date rows')
    for _, rec in frame.iterrows():
        ticker, dt = rec.ticker, rec.date
        if ticker not in bars or dt not in bars[ticker].index:
            raise ValueError(f'Verified row not in downloaded history: {ticker} {dt.date()}')
        if not str(rec.source).strip() or not str(rec.source_url).startswith(('http://','https://')):
            raise ValueError(f'Missing verifiable source provenance: {ticker} {dt.date()}')
        original = bars[ticker].loc[dt]
        if classify_history(bars[ticker]).loc[dt] != 'invalid':
            raise ValueError(f'Original row is not invalid: {ticker} {dt.date()}')
        vals = pd.to_numeric(rec[['Open','High','Low','Close','Volume']], errors='coerce')
        o,h,l,c,v = [float(vals[k]) for k in ('Open','High','Low','Close','Volume')]
        if not all(np.isfinite([o,h,l,c,v])) or min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):
            raise ValueError(f'Verified row fails OHLCV integrity: {ticker} {dt.date()}')
        # Guard against accidental different price basis or wrong stock.
        if abs(c / float(original.Close)-1) > .03:
            raise ValueError(f'Verified close differs >3%: {ticker} {dt.date()}')
        row={'ticker':ticker,'date':dt.date().isoformat(),
             'source':str(rec.source),'source_url':str(rec.source_url),'status':'applied_external_verified'}
        for k in ('Open','High','Low','Close','Volume'):
            row['original_'+k]=float(original[k])
            row['verified_'+k]=float(vals[k])
        audit.append(row)
    # Commit only after ALL rows pass validation.
    for row in audit:
        ticker,dt=row['ticker'],pd.Timestamp(row['date'])
        for k in ('Open','High','Low','Close','Volume'):
            bars[ticker].loc[dt,k]=row['verified_'+k]
    return audit


def write_verification_candidates(bars):
    """Export exact unresolved rows; blank provenance is NOT an approval."""
    rows=[]
    for ticker,d in bars.items():
        st=classify_history(d)
        for dt in d.index[st.eq('invalid')]:
            r=d.loc[dt]
            rows.append({'ticker':ticker,'date':dt.date().isoformat(),
                         **{k:float(r[k]) for k in ('Open','High','Low','Close','Volume')},
                         'source':'','source_url':''})
    pd.DataFrame(rows,columns=['ticker','date','Open','High','Low','Close','Volume',
                               'source','source_url']).to_csv(
        REPORTS/'realism_v366_verification_candidates.csv',index=False,encoding='utf-8-sig')
    return len(rows)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input',default=str(REPORTS/'entry_v32_paired_trades.csv'))
    p.add_argument('--capitals',default='300000,500000,1000000,3000000,10000000')
    p.add_argument('--holds',default='5,10,15,20')
    p.add_argument('--stop-pct',type=float,default=.07)
    p.add_argument('--take-pct',type=float,default=.15)
    p.add_argument('--cost-bps',type=float,default=15)
    p.add_argument('--slip-bps',type=float,default=10)
    p.add_argument('--refresh-cache',action='store_true')
    p.add_argument('--verified-bars',default='',help='Optional independently verified OHLCV CSV with source URLs')
    p.add_argument('--max-tickers',type=int,default=0,help='Research smoke-test only; 0=all')
    p.add_argument('--download-attempts',type=int,default=4)
    p.add_argument('--download-delay',type=float,default=1.5)
    args=p.parse_args()
    if not (0 < args.stop_pct < 1 and 0 < args.take_pct < 5 and
            0 <= args.cost_bps < 1000 and 0 <= args.slip_bps < 1000):
        p.error('Invalid stop/take/cost/slippage')
    if args.download_attempts < 1 or args.download_delay < 0:
        p.error('Invalid retry settings')
    capitals=[int(i) for i in args.capitals.split(',')]
    holds=[int(i) for i in args.holds.split(',')]
    if not capitals or min(capitals)<=0 or not holds or min(holds)<=0:
        p.error('Invalid capital/hold')
    x=load_signals(Path(args.input))
    tickers=sorted(x.ticker.unique())
    if args.max_tickers:
        tickers=tickers[:args.max_tickers]
        x=x.loc[x.ticker.isin(tickers)].copy()
    start=x.entry_date.min()-pd.Timedelta(days=10)
    end=x.entry_date.max()+pd.Timedelta(days=max(60,max(holds)*3))
    bars, errors, sources={},[],{}
    quality=[]
    for i,ticker in enumerate(tickers,1):
        entries=x.loc[x.ticker.eq(ticker),'entry_date']
        try:
            d, source=history(ticker,start,end,entries,args.refresh_cache,
                              args.download_attempts,args.download_delay)
            bars[ticker]=d
            sources[ticker]=source
            st=classify_history(d)
            counts=st.value_counts()
            quality.append({'ticker':ticker,'source':source,
                            'tradable_days':int(counts.get('tradable',0)),
                            'nontrading_days':int(counts.get('nontrading',0)),
                            'invalid_days':int(counts.get('invalid',0)),
                            'entry_days_nontradable':int(sum(st.get(dt,'missing')!='tradable' for dt in entries))})
        except Exception as e:
            errors.append({'ticker':ticker,'error':str(e)[:900]})
            print(f'FAILED {ticker}: {str(e)[-250:]}',flush=True)
        if i%20==0 or i==len(tickers):
            print(f'OHLCV {i}/{len(tickers)} valid={len(bars)} failed={len(errors)}',flush=True)
    REPORTS.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(errors,columns=['ticker','error']).to_csv(REPORTS/'realism_v36_failures.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(quality,columns=['ticker','source','tradable_days','nontrading_days',
                                  'invalid_days','entry_days_nontradable']).to_csv(
        REPORTS/'realism_v364_data_quality.csv',index=False,encoding='utf-8-sig')
    verification_candidates = write_verification_candidates(bars)
    verified_audit = apply_verified_bars(bars, args.verified_bars)
    pd.DataFrame(verified_audit, columns=['ticker','date','source','source_url',
        'original_Open','original_High','original_Low','original_Close','original_Volume',
        'verified_Open','verified_High','verified_Low','verified_Close','verified_Volume',
        'status']).to_csv(REPORTS/'realism_v366_verified_audit.csv',index=False,encoding='utf-8-sig')
    coverage=len(bars)/len(tickers) if tickers else 0
    meta={'version':'C3 v3.6.6 daily OHLCV research','run_kst':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
          'verification_candidates':verification_candidates,
          'externally_verified_bars_applied':len(verified_audit),
          'verification_file':args.verified_bars or None,
          'signals':len(x),'tickers_requested':len(tickers),'tickers_valid':len(bars),
          'tickers_failed':len(errors),'ohlcv_coverage_pct':round(100*coverage,2),
          'cache_hits':sum(v=='cache' for v in sources.values()),
          'download_successes':sum(v!='cache' for v in sources.values()),
          'download_attempts':args.download_attempts,'download_delay':args.download_delay,
          'coverage_gate_pct':90,'coverage_gate_passed':coverage>=.90,
          'ticker_coverage_definition':'history present and at least one tradable bar; NOT all signal entries usable',
          'signal_entry_coverage_pct':round(100*(1-(sum(q['entry_days_nontradable'] for q in quality) + int(x.ticker.isin(set(tickers)-set(bars)).sum()))/len(x)),2) if len(x) else 0,
          'stop_pct':args.stop_pct,'take_pct':args.take_pct,
          'cost_bps_round_trip':args.cost_bps,'slip_bps_each_side':args.slip_bps,
          'live_trade_approval':False,
          'warnings':['Current-listed universe and current cap tier: survivorship/lookahead selection bias.',
                      '2023-2025 already inspected; not out-of-sample.',
                      'Daily OHLCV may be adjusted and inconsistent with original historical trade prices.',
                      'Intraday stop and take prices are assumptions; when both touched stop takes priority.',
                      'Opening gap executes at opening price; no guaranteed stop fills.',
                      'Close-marked daily MDD ignores intraday equity troughs.',
                      'Factor rank is an experimental proxy, NOT production C3 score.',
                      'No bid/ask, market impact, halt, liquidity, tax or exchange price limit simulation.',
                      'Invalid price dates are not repaired; scenarios holding on invalid dates are suppressed.',
                      'Nontrading (zero OHLC positive close zero volume) days prohibit execution.',
                      'Ticker coverage alone does not guarantee signal-level or exit coverage.',
                      'Missing histories are excluded; review failure report.',
                      'External OHLCV source provenance is user-supplied and not independently authenticated by this script.']}
    (REPORTS/'realism_v36_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    if coverage < .90:
        raise SystemExit(f'Insufficient OHLCV coverage: {len(bars)}/{len(tickers)} ({coverage:.1%}); '
                         'refusing misleading report; see realism_v36_failures.csv')
    if meta['signal_entry_coverage_pct'] < 90:
        raise SystemExit(f"Insufficient tradable signal entry coverage: {meta['signal_entry_coverage_pct']}%; refusing misleading report")
    summaries,trades,equities=[],[],[]
    rejected_scenarios=[]
    rejection_details=[]
    for hold in holds:
        for capital in capitals:
            for strat in ('A_baseline','B_improved'):
                for policy in ('ticker_ascending','factor_rank'):
                    result,ts,eq=replay(x,bars,capital,strat,hold,policy,
                                        args.stop_pct,args.take_pct,args.cost_bps,args.slip_bps)
                    if result:
                        summaries.append(result);trades.extend(ts);equities.extend(eq)
                    else:
                        diagnostics = eq or [rejection_detail('unknown_replay_rejection')]
                        for detail in diagnostics:
                            rejection_details.append({'hold':hold,'capital':capital,
                                                      'strategy':strat,'selection':policy,
                                                      **detail})
                        rejected_scenarios.append({'hold':hold,'capital':capital,
                                                   'strategy':strat,'selection':policy,
                                                   'reason':diagnostics[0]['reason']})
    pd.DataFrame(rejected_scenarios, columns=['hold','capital','strategy','selection','reason']).to_csv(
        REPORTS/'realism_v366_rejected_scenarios.csv',index=False,encoding='utf-8-sig')
    detail_columns=['hold','capital','strategy','selection','reason','ticker',
                    'failure_date','signal_id','position_entry_date','shares',
                    'entry_fill','Open','High','Low','Close','Volume']
    pd.DataFrame(rejection_details, columns=detail_columns).to_csv(
        REPORTS/'realism_v366_rejection_details.csv',index=False,encoding='utf-8-sig')
    if rejected_scenarios:
        meta['rejected_scenarios']=len(rejected_scenarios)
        meta['rejection_detail_file']='realism_v366_rejection_details.csv'
        (REPORTS/'realism_v36_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Rejection detail written: realism_v366_rejection_details.csv', flush=True)
        raise SystemExit(f'{len(rejected_scenarios)} scenarios unresolved; see realism_v366_rejection_details.csv and realism_v366_verification_candidates.csv. No automatic price repair.')
    pd.DataFrame(summaries).to_csv(REPORTS/'realism_v36_summary.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(trades).to_csv(REPORTS/'realism_v36_trades.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(equities).to_csv(REPORTS/'realism_v36_daily_equity.csv',index=False,encoding='utf-8-sig')
    meta['scenarios']=len(summaries)
    (REPORTS/'realism_v36_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'C3 v3.6.6 complete: {len(summaries)} scenarios; {len(trades)} trades; {len(errors)} failed tickers')


if __name__=='__main__':
    main()
