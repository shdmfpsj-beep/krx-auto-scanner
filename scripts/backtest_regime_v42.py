"""C3 v4.2 research: independent KOSPI/KOSDAQ index regimes x entry quality x dip variants.
Run from repository root: python scripts/backtest_regime_v42.py
Depends on scripts/backtest_entry_v40_full.py; never alters scheduled scans.
"""
import argparse
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
SPEC = importlib.util.spec_from_file_location('c3_v40', Path(__file__).with_name('backtest_entry_v40_full.py'))
v40 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v40)


def assign_regime(signals):
    """Regime at signal time based on LAST AVAILABLE PRIOR session's KOSPI and KOSDAQ closes.

    Up: both indexes > MA60, at least one > MA120, KOSPI MA20 rising.
    Down: both indexes < MA60 and KOSPI < MA120.
    Otherwise: neutral. Unknown/insufficient index data is never assumed bullish.
    """
    import FinanceDataReader as fdr
    x = signals.sort_values(['signal_date', 'signal_id']).copy()
    first = pd.Timestamp(x.signal_date.min()) - pd.Timedelta(days=280)
    last = pd.Timestamp(x.signal_date.max())
    frames = {}
    for symbol, name in [('KS11', 'kospi'), ('KQ11', 'kosdaq')]:
        raw = fdr.DataReader(symbol, first.strftime('%Y-%m-%d'),
                             (last + pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
        if raw is None or raw.empty or 'Close' not in raw.columns:
            raise RuntimeError(f'Index history unavailable for {symbol}; fail closed')
        z = raw[['Close']].rename(columns={'Close': name}).copy()
        z.index = pd.to_datetime(z.index).normalize()
        z = z[~z.index.duplicated(keep='last')].sort_index()
        z[name] = pd.to_numeric(z[name], errors='coerce')
        z[f'{name}_ma20'] = z[name].rolling(20, min_periods=20).mean()
        z[f'{name}_ma60'] = z[name].rolling(60, min_periods=60).mean()
        z[f'{name}_ma120'] = z[name].rolling(120, min_periods=120).mean()
        z[f'{name}_ma20_prev5'] = z[f'{name}_ma20'].shift(5)
        frames[name] = z
    idx = frames['kospi'].join(frames['kosdaq'], how='inner')
    if len(idx) < 125:
        raise RuntimeError('Insufficient overlapping index history; fail closed')
    # FinanceDataReader may name its DatetimeIndex 'Date' rather than 'index'.
    # Set the axis name explicitly before reset_index to avoid KeyError.
    idx = idx.rename_axis('index_date').reset_index()
    idx['index_date'] = pd.to_datetime(idx['index_date']).dt.normalize()
    x['signal_date'] = pd.to_datetime(x['signal_date']).dt.normalize()
    # strict prior session (< signal_date), prevents same-day close lookahead
    x = pd.merge_asof(x.sort_values('signal_date'), idx.sort_values('index_date'),
                      left_on='signal_date', right_on='index_date',
                      direction='backward', allow_exact_matches=False)
    valid = x[['kospi','kosdaq','kospi_ma20','kospi_ma60','kospi_ma120',
               'kosdaq_ma60','kosdaq_ma120','kospi_ma20_prev5']].notna().all(axis=1)
    up = ((x.kospi > x.kospi_ma60) & (x.kosdaq > x.kosdaq_ma60) &
          ((x.kospi > x.kospi_ma120) | (x.kosdaq > x.kosdaq_ma120)) &
          (x.kospi_ma20 > x.kospi_ma20_prev5))
    down = ((x.kospi < x.kospi_ma60) & (x.kosdaq < x.kosdaq_ma60) &
            (x.kospi < x.kospi_ma120))
    x['regime'] = 'unknown'
    x.loc[valid, 'regime'] = 'neutral'
    x.loc[valid & up, 'regime'] = 'up'
    x.loc[valid & down, 'regime'] = 'down'
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default=str(REPORTS/'entry_v32_paired_trades.csv'))
    ap.add_argument('--capital', type=int, default=1000000, help='Research normalization only, not fixed live capital')
    ap.add_argument('--holds', default='5,10')
    ap.add_argument('--download-attempts', type=int, default=4)
    args = ap.parse_args()
    if args.capital <= 0: ap.error('capital must be positive')
    holds = [int(z) for z in args.holds.split(',')]
    if not holds or min(holds) <= 0: ap.error('invalid holds')
    x = v40.load_signals(Path(args.input))
    x = x.loc[~x.ticker.isin({'088980'})].copy()
    x = assign_regime(x)
    REPORTS.mkdir(parents=True,exist_ok=True)
    x.groupby(['regime','setup']).size().rename('signals').reset_index().to_csv(REPORTS/'regime_v42_signal_counts.csv',index=False,encoding='utf-8-sig')
    if x.regime.eq('unknown').mean() > .10:
        raise SystemExit('More than 10% unknown index regimes; refusing misleading result')
    tickers = sorted(x.ticker.unique())
    start = x.entry_date.min() - pd.Timedelta(days=10)
    end = x.entry_date.max() + pd.Timedelta(days=max(60,max(holds)*3))
    bars, failures = {}, []
    for i,ticker in enumerate(tickers, 1):
        try:
            bars[ticker],_ = v40.history(ticker,start,end,x.loc[x.ticker.eq(ticker),'entry_date'],
                                         False,args.download_attempts,1.5)
        except Exception as exc:
            failures.append({'ticker':ticker,'error':str(exc)[:500]})
        if i % 20 == 0 or i == len(tickers):
            print(f'v4.2 data {i}/{len(tickers)} loaded={len(bars)}',flush=True)
    REPORTS.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(failures,columns=['ticker','error']).to_csv(REPORTS/'regime_v42_data_failures.csv',index=False)
    if len(bars)/len(tickers) < .90:
        raise SystemExit('v4.2 OHLCV coverage below 90%; refusing misleading result')
    # One position portfolio; 2023-24 development and 2025 later check.
    # Regime uses only prior 60 calendar days of signals, NOT the future.
    rules = {
        'all': lambda d: pd.Series(True,index=d.index),
        'pullback': lambda d: d.ma_rising & d.setup.eq('pullback'),
        'breakout': lambda d: d.ma_rising & d.setup.eq('breakout'),
        'regime_switch': lambda d: ((d.regime.eq('up') & d.ma_rising & d.setup.eq('breakout')) |
                                    (d.regime.eq('neutral') & d.ma_rising & d.setup.eq('pullback'))),
        
    }
    periods = [('development_2023_2024','2023-01-01','2024-12-31'),
               ('later_2025','2025-01-01','2025-12-31')]
    results, rejected = [], []
    for period,start_date,end_date in periods:
        pool=x.loc[x.entry_date.between(start_date,end_date)].copy()
        for rule_name, rule in rules.items():
            chosen=pool.loc[rule(pool).fillna(False)].copy()
            if chosen.empty:
                rejected.append({'period':period,'rule':rule_name,'reason':'no_signals'})
                continue
            for hold in holds:
                for selection in ('ticker_ascending','factor_rank'):
                    arms=[('all_in',None),('cash_half',None)] + [(f'dip_{n}pct',n/100) for n in (2,3,4,5)]
                    for arm,threshold in arms:
                        if arm=='all_in':
                            summary, trades, diagnostic=v40.replay(chosen,bars,args.capital,'A_baseline',hold,selection,.07,.15,15,10)
                        else:
                            summary,trades,diagnostic=v40.replay_dip_v39(
                                chosen,bars,args.capital,'A_baseline',hold,selection,.07,.15,15,10,
                                'cash_50_no_add' if arm=='cash_half' else 'dip_50_50',threshold or .02)
                        if summary is None:
                            rejected.append({'period':period,'rule':rule_name,'hold':hold,
                                             'selection':selection,'arm':arm,'reason':'replay_rejected'})
                            continue
                        results.append({'period':period,'rule':rule_name,'hold':hold,'selection':selection,
                                        'arm':arm,'capital_research_only':args.capital,
                                        'eligible_signals':len(chosen),'trades_closed':summary['trades_closed'],
                                        'return_pct':summary['total_return_pct'],
                                        'mdd_pct':summary['daily_close_mdd_pct'],
                                        'win_rate_pct':summary['win_rate_pct'],
                                        'adds_executed':summary.get('adds_executed',0)})
    frame=pd.DataFrame(results)
    if frame.empty: raise SystemExit('No valid v4.2 scenarios')
    key=['period','rule','hold','selection']
    control=frame.loc[frame.arm.eq('cash_half'),key+['return_pct','mdd_pct']].rename(
        columns={'return_pct':'cash_control_return_pct','mdd_pct':'cash_control_mdd_pct'})
    frame=frame.merge(control,on=key,how='left',validate='many_to_one')
    frame['delta_vs_cash_pp']=frame.return_pct-frame.cash_control_return_pct
    frame.to_csv(REPORTS/'regime_v42_comparison.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(rejected,columns=['period','rule','hold','selection','arm','reason']).to_csv(
        REPORTS/'regime_v42_rejected.csv',index=False,encoding='utf-8-sig')
    x.groupby(['regime','setup']).size().rename('signals').reset_index().to_csv(
        REPORTS/'regime_v42_signal_counts.csv',index=False,encoding='utf-8-sig')
    meta={'version':'v4.2','completed':len(frame),'rejected':len(rejected),
          'capital_research_only':args.capital,'holds':holds,
          'regime':'Prior-session KOSPI and KOSDAQ close/MA20/MA60/MA120, with strict asof lag; down regime holds cash under regime_switch',
          'limitations':['Research only; survivor bias and signal feature point-in-time not independently audited.',
                         '2025 has been inspected previously, NOT a pristine out-of-sample test.',
                         'Index data is fetched by FinanceDataReader and may be revised; source accuracy and point-in-time index constituents are not audited.',
                         'Daily OHLCV cannot identify intraday path; v3.9 conservative stop-first assumption.',
                         'Different arms may trade different numbers of positions; compare exposure and trade count.',
                         'Capital is research normalization; live sizing uses actual orderable cash.',
                         'Regime thresholds were designed after reviewing prior periods, so 2025 is NOT independent validation.',
                         'Regime-switch holds cash in down/unknown regimes; compare number of trades and exposure.',
                         'Index MA values are calculated on adjusted or unadjusted provider closes as supplied; no guarantee of historic revision-free data.']}
    (REPORTS/'regime_v42_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'v4.2 completed {len(frame)} rejected {len(rejected)}',flush=True)

if __name__=='__main__':
    main()
