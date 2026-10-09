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
          'market_data_date': None, 'universe_source': None, 'ohlcv_sources': {},
          'coverage_ratio': 0, 'scan_complete': False, 'errors': [],
          'note': 'Candidate scan only; no trade approvals. Flows and account cash not verified.'}

def save_status():
    (OUT / 'status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')

def record_error(message):
    if len(status['errors']) < 40:
        status['errors'].append(str(message)[:300])

def normalize_codes(series):
    return sorted({s for x in series if (s := str(x).strip()).isdigit() and len(s) == 6})

def fetch_universe():
    for offset in (0, 1, 2, 3, 5, 7, 10):
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
        except Exception as e:
            record_error(f'pykrx universe {day}: {type(e).__name__}: {e}')
    try:
        import FinanceDataReader as fdr
        for source in ('KRX-DESC', 'KRX'):
            try:
                listing = fdr.StockListing(source)
                if listing is None or listing.empty:
                    raise ValueError('empty listing')
                col = next((c for c in ('Code', 'Symbol') if c in listing.columns), None)
                if col is None:
                    raise ValueError(f'unknown columns: {list(listing.columns)}')
                if 'Market' in listing.columns:
                    listing = listing[listing['Market'].astype(str).str.upper().isin(['KOSPI', 'KOSDAQ'])]
                codes = normalize_codes(listing[col].dropna())
                if len(codes) <= 1000:
                    raise ValueError(f'only {len(codes)} codes')
                status['universe_source'] = f'FDR {source} (current listing; not point-in-time)'
                status['universe_reference_date'] = NOW.date().isoformat()
                return codes
            except Exception as e:
                record_error(f'FDR {source}: {type(e).__name__}: {e}')
    except ImportError as e:
        record_error(f'FDR missing: {e}')
    return []

def fetch_ohlcv(code):
    errors = []
    try:
        df = stock.get_market_ohlcv_by_date(START, END, code, adjusted=True)
        if df is not None and not df.empty:
            return df, 'pykrx'
        errors.append('pykrx empty')
    except Exception as e:
        errors.append(f'pykrx {type(e).__name__}: {str(e)[:80]}')
    try:
        import FinanceDataReader as fdr
        raw = fdr.DataReader(code, START[:4]+'-'+START[4:6]+'-'+START[6:], END[:4]+'-'+END[4:6]+'-'+END[6:])
        if raw is None or raw.empty:
            raise ValueError('empty FDR dataframe')
        df = raw.rename(columns={'Open':'시가', 'High':'고가', 'Low':'저가', 'Close':'종가', 'Volume':'거래량'})
        return df, 'FinanceDataReader'
    except Exception as e:
        errors.append(f'FDR {type(e).__name__}: {str(e)[:80]}')
    raise ValueError('; '.join(errors))

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
    rec = {'close': int(c.iloc[-1]), 'ma20': round(ma20.iloc[-1], 2),
           'ma60': round(ma60.iloc[-1], 2), 'ma120': round(ma120.iloc[-1], 2),
           'rvol20': round(rvol, 3) if rvol is not None else None,
           'breakout': breakout, 'first_pullback_proxy': pullback,
           'reversal_proxy': reversal, 'weekly_filter': w_ok,
           'monthly_filter': m_ok,
           'score': 3 * (int(breakout) + int(pullback) + int(reversal)) + int(w_ok) + int(m_ok)}
    # Explicit OHLCV turnover is preferable; close*volume is only an estimate.
    if '거래대금' in df.columns and pd.notna(df['거래대금'].iloc[-1]):
        rec['turnover_krw'] = int(float(df['거래대금'].iloc[-1]))
        rec['turnover_source'] = 'SOURCE_REPORTED'
    else:
        rec['turnover_krw'] = int(float(c.iloc[-1]) * float(v.iloc[-1]))
        rec['turnover_source'] = 'ESTIMATED_CLOSE_X_VOLUME'
    return rec

def special_type_from_name(name):
    # A name can prove some special types; absence of keywords does NOT prove common stock.
    upper = name.upper()
    if any(token in upper for token in ('ETF', 'ETN', '스팩', 'SPAC', '리츠', 'REIT')):
        return 'NON_COMMON_OR_SPECIAL'
    return 'UNKNOWN'

def main():
    codes = fetch_universe()
    status['universe'] = len(codes)
    save_status()
    if not codes:
        record_error('Universe unavailable; no candidate report generated.')
        (OUT / 'candidates.csv').unlink(missing_ok=True)
        save_status()
        raise RuntimeError('Unable to retrieve KOSPI/KOSDAQ universe')
    rows = []
    for code in codes:
        status['download_attempted'] += 1
        try:
            df, source = fetch_ohlcv(code)
            if df is None or df.empty:
                raise ValueError('empty OHLCV')
            df = df[~df.index.duplicated(keep='last')].sort_index()
            if len(df) < 150:
                raise ValueError(f'only {len(df)} sessions')
            for col in ('시가', '고가', '저가', '종가', '거래량'):
                if col not in df.columns:
                    raise ValueError('missing ' + col)
            if df[['시가','고가','저가','종가','거래량']].tail(120).isna().any().any():
                raise ValueError('missing OHLCV values')
            if (df['종가'].tail(120) <= 0).any():
                raise ValueError('nonpositive close')
            latest = df.index[-1].date()
            if latest > CUTOFF or (CUTOFF - latest).days > 7:
                raise ValueError(f'invalid/stale market data {latest}')
            status['download_succeeded'] += 1
            rec = classify(df)
            status['valid_ohlcv'] += 1
            status['ohlcv_sources'][source] = status['ohlcv_sources'].get(source, 0) + 1
            if any(rec[k] for k in ('breakout', 'first_pullback_proxy', 'reversal_proxy')):
                rec.update(ticker=code, latest_date=str(latest), sessions=len(df), data_source=source)
                rows.append(rec)
            status['screened'] += 1
            last = str(latest)
            if status['market_data_date'] is None or last > status['market_data_date']:
                status['market_data_date'] = last
        except Exception as e:
            status['failed'] += 1
            record_error(f'{code}: {type(e).__name__}: {e}')
        if status['download_attempted'] % 50 == 0:
            save_status()
        time.sleep(float(os.getenv('REQUEST_DELAY', '0.2')))
    # Fetch names only for screened candidates, keeping 2600+ OHLCV requests unchanged.
    names_ok = 0
    for rec in rows:
        try:
            name = str(stock.get_market_ticker_name(rec['ticker']) or '').strip()
        except Exception:
            name = ''
        rec['name'] = name
        rec['instrument_type'] = special_type_from_name(name) if name else 'UNKNOWN'
        names_ok += bool(name)
    status['candidate_names_resolved'] = names_ok
    status['candidate_instrument_type_unknown'] = sum(r['instrument_type'] == 'UNKNOWN' for r in rows)
    status['candidate_turnover_estimated'] = sum(r['turnover_source'] != 'SOURCE_REPORTED' for r in rows)
    status['coverage_ratio'] = round(status['screened'] / len(codes), 4)
    status['scan_complete'] = status['coverage_ratio'] >= 0.95
    if rows:
        pd.DataFrame(rows).sort_values(['score', 'rvol20'], ascending=False).to_csv(
            OUT / 'candidates.csv', index=False, encoding='utf-8-sig')
    else:
        (OUT / 'candidates.csv').unlink(missing_ok=True)
    save_status()
    print(json.dumps(status, ensure_ascii=False))
    if not status['scan_complete']:
        raise RuntimeError(f'Incomplete KRX scan: {status["coverage_ratio"]:.1%} coverage; see reports/status.json')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        record_error('Fatal: ' + repr(e))
        save_status()
        traceback.print_exc()
        raise
