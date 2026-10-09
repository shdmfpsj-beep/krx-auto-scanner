"""C3 v1.0: historical as-of-date candidate reconstruction (research only).

Creates daily historical candidate snapshots from historical OHLCV. The universe
is queried for each historical date but pykrx completeness (especially delisted
stocks) is NOT guaranteed. No orders are placed.
"""
import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
OUT.mkdir(parents=True, exist_ok=True)


def historical_universe(day):
    ymd = day.strftime('%Y%m%d')
    kospi = stock.get_market_ticker_list(ymd, market='KOSPI') or []
    kosdaq = stock.get_market_ticker_list(ymd, market='KOSDAQ') or []
    return {str(t): 'KOSPI' for t in kospi} | {str(t): 'KOSDAQ' for t in kosdaq}


def fetch_prices(code, start, end):
    frame = stock.get_market_ohlcv_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), code, adjusted=True)
    if frame is None or frame.empty:
        return None
    frame = frame.rename(columns={'시가':'open','고가':'high','저가':'low','종가':'close','거래량':'volume','거래대금':'turnover'})
    if not {'open','high','low','close','volume'}.issubset(frame.columns):
        return None
    frame.index = pd.to_datetime(frame.index).normalize()
    frame = frame[~frame.index.duplicated(keep='last')].sort_index()
    for col in ('open','high','low','close','volume'):
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    return frame


def signals(frame):
    c = frame['close']
    v = frame['volume']
    h = frame['high']
    ma20 = c.rolling(20, min_periods=20).mean()
    ma60 = c.rolling(60, min_periods=60).mean()
    ma120 = c.rolling(120, min_periods=120).mean()
    rvol = v / v.shift(1).rolling(20, min_periods=20).mean()
    breakout = (c > h.shift(1).rolling(20, min_periods=20).max()) & (rvol >= 1.5) & (c > ma60)
    pullback = (ma20 > ma60) & (ma60 > ma120) & ((c / ma20 - 1).abs() <= .035) & (c > ma20)
    reversal = (c.shift(1) < ma60.shift(1)) & (c > ma60) & (ma20 > ma20.shift(5))
    # Completed prior calendar week/month only; avoids using incomplete future bars.
    weekly = c.resample('W-FRI').last().dropna()
    w_signal = (weekly > weekly.rolling(10, min_periods=10).mean()).shift(1)
    monthly = c.resample('ME').last().dropna()
    m_signal = (monthly > monthly.rolling(6, min_periods=6).mean()).shift(1)
    out = pd.DataFrame(index=frame.index)
    out['breakout'] = breakout.fillna(False)
    out['first_pullback_proxy'] = pullback.fillna(False)
    out['reversal_proxy'] = reversal.fillna(False)
    out['weekly_filter'] = w_signal.reindex(out.index, method='ffill').fillna(False).astype(bool)
    out['monthly_filter'] = m_signal.reindex(out.index, method='ffill').fillna(False).astype(bool)
    out['rvol20'] = rvol
    out['close'] = c
    out['volume'] = v
    out['turnover_krw'] = frame['turnover'] if 'turnover' in frame else c * v
    out['score'] = 3 * (out['breakout'].astype(int) + out['first_pullback_proxy'].astype(int) + out['reversal_proxy'].astype(int)) + out['weekly_filter'].astype(int) + out['monthly_filter'].astype(int)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=30, help='Calendar days to scan; start small')
    ap.add_argument('--limit', type=int, default=30, help='Maximum historical-universe tickers for pilot')
    ap.add_argument('--delay', type=float, default=.2)
    args = ap.parse_args()
    if args.days < 1 or args.limit < 1:
        ap.error('days and limit must be positive')
    today = datetime.now(ZoneInfo('Asia/Seoul')).date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=args.days - 1)
    status = {'version':'C3 v1.0 PIT candidate pilot','run_kst':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), 'requested_start':str(start),'requested_end':str(end),'ticker_limit':args.limit,'universe_dates':0,'historical_universe_size':0,'attempted':0,'succeeded':0,'candidates':0,'errors':[],'trade_approval':'NO','limitations':['Historical ticker list availability and delisted-stock completeness are not verified','Pilot uses a limited alphabetical subset, not an investable market-wide universe','Adjusted OHLCV may embed retrospective corporate-action adjustments','No trading simulation or transaction costs in this script','Daily signals use same-day close; entries must occur no earlier than next session']}
    try:
        # Union of daily historical listings; do not substitute present-day candidates.csv.
        universe_by_day = {}
        for day in pd.date_range(start, end, freq='B'):
            try:
                codes = historical_universe(day.date())
                if len(codes) > 1000:
                    universe_by_day[day.normalize()] = codes
            except Exception as exc:
                status['errors'].append(f'universe {day.date()}: {type(exc).__name__}: {exc}'[:250])
            time.sleep(args.delay)
        status['universe_dates'] = len(universe_by_day)
        if not universe_by_day:
            raise RuntimeError('No valid historical daily universe returned')
        all_codes = sorted(set().union(*(set(v) for v in universe_by_day.values())))
        status['historical_universe_size'] = len(all_codes)
        pilot_codes = all_codes[:args.limit]
        rows = []
        fetch_start = start - timedelta(days=550)
        for code in pilot_codes:
            status['attempted'] += 1
            try:
                df = fetch_prices(code, fetch_start, end)
                if df is None or len(df) < 150:
                    continue
                sig = signals(df)
                status['succeeded'] += 1
                for day, membership in universe_by_day.items():
                    if code not in membership or day not in sig.index:
                        continue
                    r = sig.loc[day]
                    if not (r['breakout'] or r['first_pullback_proxy'] or r['reversal_proxy']):
                        continue
                    if not pd.notna(r['rvol20']) or r['close'] <= 0 or r['volume'] <= 0:
                        continue
                    rows.append({'date':day.strftime('%Y-%m-%d'),'ticker':code,'market_asof':membership[code], 'close':float(r['close']),'rvol20':round(float(r['rvol20']),3),'breakout':bool(r['breakout']),'first_pullback_proxy':bool(r['first_pullback_proxy']),'reversal_proxy':bool(r['reversal_proxy']),'weekly_filter':bool(r['weekly_filter']),'monthly_filter':bool(r['monthly_filter']),'score':int(r['score']),'turnover_krw':float(r['turnover_krw'])})
            except Exception as exc:
                status['errors'].append(f'{code}: {type(exc).__name__}: {exc}'[:250])
            time.sleep(args.delay)
        cols = ['date','ticker','market_asof','close','rvol20','breakout','first_pullback_proxy','reversal_proxy','weekly_filter','monthly_filter','score','turnover_krw']
        pd.DataFrame(rows, columns=cols).sort_values(['date','score','rvol20'], ascending=[True,False,False]).to_csv(OUT/'pit_candidates_v10.csv', index=False, encoding='utf-8-sig')
        status['candidates'] = len(rows)
        status['pilot_complete'] = True
    except Exception as exc:
        status['pilot_complete'] = False
        status['errors'].append(f'FATAL: {type(exc).__name__}: {exc}'[:250])
        raise
    finally:
        (OUT/'pit_v10_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(status,ensure_ascii=False))

if __name__ == '__main__':
    main()
