import json, os, time, traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
OUT.mkdir(parents=True, exist_ok=True)
NOW = datetime.now(ZoneInfo('Asia/Seoul'))
CUTOFF = NOW.date() if (NOW.hour, NOW.minute) >= (16, 10) else NOW.date() - timedelta(days=1)
END = CUTOFF.strftime('%Y%m%d')
START = (CUTOFF - timedelta(days=550)).strftime('%Y%m%d')
status = {'run_kst': NOW.isoformat(), 'requested_end': END, 'universe': 0,
          'download_attempted': 0, 'download_succeeded': 0, 'valid_ohlcv': 0,
          'screened': 0, 'failed': 0, 'external_screener_count': 0,
          'full_chart_verified': 0, 'duplicates_removed': 0,
          'market_data_date': None, 'universe_source': None, 'errors': [],
          'note': 'Candidate scan only; no trade approvals. Flows, volume profile and account cash not verified.'}

def save_status():
    (OUT / 'status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')

def record_error(message):
    if len(status['errors']) < 40:
        status['errors'].append(str(message)[:300])

def fetch_universe():
    # Primary: pykrx, checking up to 20 calendar days for holidays.
    for offset in range(20):
        day = (CUTOFF - timedelta(days=offset)).strftime('%Y%m%d')
        try:
            a = stock.get_market_ticker_list(day, market='KOSPI')
            b = stock.get_market_ticker_list(day, market='KOSDAQ')
            codes = sorted(set(a) | set(b))
            if len(codes) > 1000:
                status['universe_source'] = 'pykrx'
                status['universe_reference_date'] = day
                status['duplicates_removed'] = len(a) + len(b) - len(codes)
                return codes
            record_error(f'pykrx universe {day}: only {len(codes)} tickers')
        except Exception as e:
            record_error(f'pykrx universe {day}: {type(e).__name__}: {e}')
        time.sleep(0.3)
    # Secondary: KRX listed-symbol snapshot via FinanceDataReader.
    # This is a CURRENT listing, not a historical point-in-time universe.
    try:
        import FinanceDataReader as fdr
        listing = fdr.StockListing('KRX')
        if listing is None or listing.empty or 'Code' not in listing.columns:
            raise ValueError('missing Code or empty listing')
        if 'Market' in listing.columns:
            listing = listing[listing['Market'].astype(str).str.upper().isin(['KOSPI', 'KOSDAQ'])]
        codes = sorted({str(x).zfill(6) for x in listing['Code'].dropna()
                        if str(x).strip().isdigit() and len(str(x).strip()) <= 6})
        if len(codes) <= 1000:
            raise ValueError(f'only {len(codes)} tickers')
        status['universe_source'] = 'FinanceDataReader current KRX listing (not historical)'
        status['universe_reference_date'] = NOW.date().isoformat()
        return codes
    except Exception as e:
        record_error(f'FDR universe: {type(e).__name__}: {e}')
    return []

def classify(df):
    c = df['종가'].astype(float)
    v = df['거래량'].astype(float)
    ma20, ma60, ma120 = (c.rolling(n).mean() for n in (20, 60, 120))
    prior_volume = v.iloc[-21:-1].mean()
    rvol = float(v.iloc[-1] / prior_volume) if prior_volume > 0 else None
    high20 = df['고가'].astype(float).iloc[-21:-1].max()
    breakout = bool(c.iloc[-1] > high20 and rvol is not None and rvol >= 1.5 and c.iloc[-1] > ma60.iloc[-1])
    pullback = bool(ma20.iloc[-1] > ma60.iloc[-1] > ma120.iloc[-1] and abs(c.iloc[-1] / ma20.iloc[-1] - 1) <= .035 and c.iloc[-1] > ma20.iloc[-1])
    reversal = bool(c.iloc[-2] < ma60.iloc[-2] and c.iloc[-1] > ma60.iloc[-1] and ma20.iloc[-1] > ma20.iloc[-6])
    weekly = c.resample('W-FRI').last().dropna()
    monthly = c.resample('ME').last().dropna()
    w_ok = bool(len(weekly) >= 30 and weekly.iloc[-1] > weekly.rolling(10).mean().iloc[-1])
    m_ok = bool(len(monthly) >= 8 and monthly.iloc[-1] > monthly.rolling(6).mean().iloc[-1])
    return {'close': int(c.iloc[-1]), 'ma20': round(ma20.iloc[-1], 2),
            'ma60': round(ma60.iloc[-1], 2), 'ma120': round(ma120.iloc[-1], 2),
            'rvol20': round(rvol, 3) if rvol is not None else None,
            'breakout': breakout, 'first_pullback_proxy': pullback,
            'reversal_proxy': reversal, 'weekly_filter': w_ok,
            'monthly_filter': m_ok,
            'score': 3 * (int(breakout) + int(pullback) + int(reversal)) + int(w_ok) + int(m_ok)}

def main():
    codes = fetch_universe()
    status['universe'] = len(codes)
    save_status()
    if not codes:
        record_error('Universe download unavailable; no candidate report generated.')
        (OUT / 'candidates.csv').unlink(missing_ok=True)
        save_status()
        raise RuntimeError('Unable to retrieve KOSPI/KOSDAQ universe')
    rows = []
    for code in codes:
        status['download_attempted'] += 1
        try:
            df = stock.get_market_ohlcv_by_date(START, END, code, adjusted=True)
            if df is None or df.empty:
                raise ValueError('empty OHLCV')
            df = df[~df.index.duplicated(keep='last')].sort_index()
            if len(df) < 150:
                raise ValueError(f'only {len(df)} sessions')
            for col in ('시가', '고가', '저가', '종가', '거래량'):
                if col not in df.columns:
                    raise ValueError('missing ' + col)
            if (df['종가'].tail(120) <= 0).any():
                raise ValueError('nonpositive close')
            if df.index[-1].date() > CUTOFF:
                raise ValueError('future market data date')
            if (CUTOFF - df.index[-1].date()).days > 7:
                raise ValueError('stale market data')
            status['download_succeeded'] += 1
            rec = classify(df)
            status['valid_ohlcv'] += 1
            if any(rec[k] for k in ('breakout', 'first_pullback_proxy', 'reversal_proxy')):
                rec.update(ticker=code, latest_date=str(df.index[-1].date()), sessions=len(df))
                rows.append(rec)
            status['screened'] += 1
            last = str(df.index[-1].date())
            if status['market_data_date'] is None or last > status['market_data_date']:
                status['market_data_date'] = last
        except Exception as e:
            status['failed'] += 1
            record_error(f'{code}: {type(e).__name__}: {e}')
        if status['download_attempted'] % 50 == 0:
            save_status()
        time.sleep(float(os.getenv('REQUEST_DELAY', '0.2')))
    if rows:
        pd.DataFrame(rows).sort_values(['score', 'rvol20'], ascending=False).to_csv(
            OUT / 'candidates.csv', index=False, encoding='utf-8-sig')
    else:
        (OUT / 'candidates.csv').unlink(missing_ok=True)
    save_status()
    print(json.dumps(status, ensure_ascii=False))
    if status['valid_ohlcv'] == 0:
        raise RuntimeError('No valid OHLCV downloaded; see reports/status.json')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        record_error('Fatal: ' + repr(e))
        save_status()
        traceback.print_exc()
        raise
