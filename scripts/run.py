import csv, json, os, time, traceback
import hashlib, inspect, sys
from contextlib import contextmanager
from importlib.metadata import version as package_version, PackageNotFoundError
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from pykrx import stock
from market_session_policy_v66 import completed_scan_cutoff_date, source_policy_metadata
from c3_premove_handoff_v1 import PremoveObserver, record_failure as record_premove_failure, load_registered_watch, registered_failure

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
OUT.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(ZoneInfo('Asia/Seoul'))
CUTOFF = completed_scan_cutoff_date(NOW)  # KRX after-market ends at 20:00
END = CUTOFF.strftime('%Y%m%d')
START = (CUTOFF - timedelta(days=550)).strftime('%Y%m%d')

status = {
    'version': '2.2',
    'run_kst': NOW.isoformat(),
    'requested_end': END,
    'universe': 0,
    'download_attempted': 0,
    'download_succeeded': 0,
    'valid_ohlcv': 0,
    'screened': 0,
    'failed': 0,
    'external_screener_count': 0,
    'full_chart_verified': 0,
    'duplicates_removed': 0,
    'market_data_date': None,
    'market_data_date_counts': {},
    'reference_market_date': None,
    'reference_date_source': None,
    'candidate_date_mismatch': 0,
    'universe_source': None,
    'ohlcv_sources': {},
    'coverage_ratio': 0,
    'scan_complete': False,
    'data_date_verified': False,
    'errors': [],
    'note': 'Technical candidate scan only; no trade approvals. Flows and account cash not verified.'
}

status.update(source_policy_metadata(NOW))

def save_status():
    (OUT / 'status.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

def record_error(message):
    if len(status['errors']) < 40:
        status['errors'].append(str(message)[:300])

def normalize_codes(series):
    return sorted({
        s for x in series
        if (s := str(x).strip()).isdigit() and len(s) == 6
    })

# Collection evidence never changes the requested adjusted series or certifies
# its market scope. Only the actual function/module paths are traced. Arguments,
# environment values, credentials and response headers are never recorded.
SOURCE_LOG = OUT / 'c3_source_observations_v1.jsonl'
RUNTIME_FILE = OUT / 'c3_source_runtime_v1.json'
CALENDAR_FILE = OUT / 'c3_reference_calendar_v1.json'
UNIVERSE_FILE = OUT / 'c3_universe_capture_v1.json'

def utc_now():
    return datetime.now(ZoneInfo('UTC')).isoformat()

def function_evidence(fn):
    try:
        unwrapped = inspect.unwrap(fn)
        source = inspect.getsource(unwrapped)
        return {'module': unwrapped.__module__, 'name': unwrapped.__name__,
                'source_sha256': hashlib.sha256(source.encode()).hexdigest()}
    except (AttributeError, OSError, TypeError):
        return {'module': getattr(fn, '__module__', None),
                'name': getattr(fn, '__name__', None), 'source_sha256': None}

def runtime_evidence():
    versions = {}
    for name in ('pykrx', 'pandas', 'finance-datareader'):
        try:
            versions[name] = package_version(name)
        except PackageNotFoundError:
            versions[name] = None
    return {'schema': 'C3_SOURCE_RUNTIME_V1', 'captured_at_utc': utc_now(),
            'python_version': sys.version.split()[0], 'packages': versions,
            'run_context': {key: os.getenv(key) for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA')},
            'api_functions': {name: function_evidence(getattr(stock, name, None))
                              for name in ('get_market_ohlcv_by_date', 'get_market_ohlcv_by_ticker')},
            'regular_only_scope_verified': False, 'orders_enabled': False}

@contextmanager
def trace_price_route():
    evidence = {'actual_provider_calls': [], 'trace_completed': False,
                'trace_skipped_existing_profiler': False}
    previous = sys.getprofile()
    if previous is not None:
        evidence['trace_skipped_existing_profiler'] = True
        yield evidence
        return
    seen = set()
    def profile(frame, event, arg):
        if event != 'call':
            return
        module = str(frame.f_globals.get('__name__', ''))
        name = frame.f_code.co_name
        if module.startswith(('pykrx.website.naver', 'pykrx.website.krx')) and name == 'get_market_ohlcv_by_date':
            identity = (module, name)
            if identity not in seen:
                seen.add(identity)
                evidence['actual_provider_calls'].append({'module': module, 'function': name})
    try:
        sys.setprofile(profile)
        yield evidence
        evidence['trace_completed'] = True
    finally:
        sys.setprofile(previous)

def record_source_response(code, df, label, api, request, started, route=None):
    record = {'schema': 'C3_SOURCE_RESPONSE_V1', 'ticker': str(code),
              'source_label': label, 'api': api, 'request': request,
              'fetch_started_at_utc': started, 'response_received_at_utc': utc_now(),
              'rows': len(df), 'response_columns': list(map(str, df.columns)),
              'latest_observed_date': str(pd.Timestamp(df.index[-1]).date()),
              'latest_raw_close': float(df['종가'].iloc[-1]) if '종가' in df and pd.notna(df['종가'].iloc[-1]) else None,
              'raw_response_csv_sha256': hashlib.sha256(df.to_csv(index=True).encode()).hexdigest(),
              'runtime_manifest': RUNTIME_FILE.name,
              'runtime_manifest_sha256': hashlib.sha256(RUNTIME_FILE.read_bytes()).hexdigest() if RUNTIME_FILE.exists() else None,
              'route': route, 'regular_only_scope_verified': False,
              'source_reported_turnover_field_present': '거래대금' in df.columns,
              'turnover_unit_and_regular_scope_verified': False, 'orders_enabled': False}
    SOURCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with SOURCE_LOG.open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
    except (OSError, ValueError) as error:
        # A diagnostic write failure must never silently select another price
        # provider. The original response remains original and is still audited.
        record['diagnostic_stream_write_error'] = type(error).__name__
        record_error('SOURCE_EVIDENCE_WRITE_FAILED:' + type(error).__name__)
    df.attrs['c3_source_response'] = record
    return df, label

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
                    listing = listing[
                        listing['Market'].astype(str).str.upper().isin(['KOSPI', 'KOSDAQ'])
                    ]
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
        started = utc_now()
        with trace_price_route() as route:
            df = stock.get_market_ohlcv_by_date(START, END, code, adjusted=True)
        if df is not None and not df.empty:
            return record_source_response(code, df, 'pykrx', 'get_market_ohlcv_by_date',
                                          {'start': START, 'end': END, 'adjusted': True}, started, route)
        errors.append('pykrx empty')
    except Exception as e:
        errors.append(f'pykrx {type(e).__name__}: {str(e)[:80]}')

    try:
        import FinanceDataReader as fdr
        started = utc_now()
        raw = fdr.DataReader(
            code,
            START[:4] + '-' + START[4:6] + '-' + START[6:],
            END[:4] + '-' + END[4:6] + '-' + END[6:]
        )
        if raw is None or raw.empty:
            raise ValueError('empty FDR dataframe')
        df = raw.rename(columns={
            'Open': '시가',
            'High': '고가',
            'Low': '저가',
            'Close': '종가',
            'Volume': '거래량'
        })
        return record_source_response(code, df, 'FinanceDataReader', 'DataReader',
                                      {'start': START, 'end': END, 'adjusted': 'PROVIDER_DEFAULT_UNKNOWN'}, started)
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
    breakout = bool(
        c.iloc[-1] > high20
        and rvol is not None
        and rvol >= 1.5
        and c.iloc[-1] > ma60.iloc[-1]
    )
    pullback = bool(
        ma20.iloc[-1] > ma60.iloc[-1] > ma120.iloc[-1]
        and abs(c.iloc[-1] / ma20.iloc[-1] - 1) <= 0.035
        and c.iloc[-1] > ma20.iloc[-1]
    )
    reversal = bool(
        c.iloc[-2] < ma60.iloc[-2]
        and c.iloc[-1] > ma60.iloc[-1]
        and ma20.iloc[-1] > ma20.iloc[-6]
    )

    weekly = c.resample('W-FRI').last().dropna()
    monthly = c.resample('ME').last().dropna()
    w_ok = bool(
        len(weekly) >= 30
        and weekly.iloc[-1] > weekly.rolling(10).mean().iloc[-1]
    )
    m_ok = bool(
        len(monthly) >= 8
        and monthly.iloc[-1] > monthly.rolling(6).mean().iloc[-1]
    )

    rec = {
        'close': int(c.iloc[-1]),
        'ma20': round(ma20.iloc[-1], 2),
        'ma60': round(ma60.iloc[-1], 2),
        'ma120': round(ma120.iloc[-1], 2),
        'rvol20': round(rvol, 3) if rvol is not None else None,
        'breakout': breakout,
        'first_pullback_proxy': pullback,
        'reversal_proxy': reversal,
        'weekly_filter': w_ok,
        'monthly_filter': m_ok,
        'score': (
            3 * (int(breakout) + int(pullback) + int(reversal))
            + int(w_ok) + int(m_ok)
        )
    }

    if '거래대금' in df.columns and pd.notna(df['거래대금'].iloc[-1]):
        rec['turnover_krw'] = int(float(df['거래대금'].iloc[-1]))
        rec['turnover_source'] = 'SOURCE_REPORTED'
    else:
        rec['turnover_krw'] = int(float(c.iloc[-1]) * float(v.iloc[-1]))
        rec['turnover_source'] = 'ESTIMATED_CLOSE_X_VOLUME'
    return rec

def special_type_from_name(name):
    upper = name.upper()
    if any(token in upper for token in (
        'ETF', 'ETN', '스팩', 'SPAC', '리츠', 'REIT'
    )):
        return 'NON_COMMON_OR_SPECIAL'
    if name.endswith('우') or name.endswith('우B') or name.endswith('우C'):
        return 'NON_COMMON_OR_SPECIAL'
    return 'UNKNOWN'

def main():
    # Reset only this run's diagnostic stream; never append stale attempts.
    SOURCE_LOG.unlink(missing_ok=True)
    RUNTIME_FILE.write_text(json.dumps(runtime_evidence(), ensure_ascii=False, indent=2), encoding='utf-8')
    CALENDAR_FILE.unlink(missing_ok=True)
    registered_failure(OUT,CUTOFF.isoformat(),RuntimeError('THIS_RUN_CAPTURE_NOT_COMPLETED'))
    try:
        registered_watch=load_registered_watch(ROOT/'config/c3_registered_reclaim_v1.json')
        status['registered_followup_config_loaded']=True
        status['registered_followup_required_count']=registered_watch['registered_count']
    except (OSError,ValueError,KeyError,TypeError) as watch_error:
        registered_watch=None
        status['registered_followup_config_loaded']=False
        record_error('REGISTERED_COHORT_CONFIG_UNAVAILABLE:'+type(watch_error).__name__)
    codes = fetch_universe()
    UNIVERSE_FILE.write_text(json.dumps({'schema': 'C3_UNIVERSE_CAPTURE_V1',
        'captured_at_utc': utc_now(), 'source': status.get('universe_source'),
        'reference_date': status.get('universe_reference_date'), 'tickers': codes,
        'total': len(codes), 'full_market_completeness_certified': False},
        ensure_ascii=False, indent=2), encoding='utf-8')
    status['universe'] = len(codes)
    save_status()

    if not codes:
        record_error('Universe unavailable; no candidate report generated.')
        (OUT / 'candidates.csv').unlink(missing_ok=True)
        save_status()
        raise RuntimeError('Unable to retrieve KOSPI/KOSDAQ universe')

    valid_rows = []
    candidate_daily_bars = []
    latest_dates = Counter()
    premove = PremoveObserver(CUTOFF.isoformat(),registered_watch=registered_watch)
    premove_calendar = []
    premove_calendar_source = {'ticker': '069500', 'status': 'UNAVAILABLE',
                              'role': 'OBSERVED_SESSION_GRID_NOT_REGULAR_SCOPE_PROOF'}
    try:
        calendar_frame, calendar_provider = fetch_ohlcv('069500')
        if calendar_frame is None or calendar_frame.empty:
            raise ValueError('EMPTY_REFERENCE_CALENDAR')
        premove_calendar = [pd.Timestamp(d).date().isoformat() for d in calendar_frame.index]
        premove_calendar_source.update(status='CAPTURED', provider=calendar_provider)
        CALENDAR_FILE.write_text(json.dumps({'schema': 'C3_REFERENCE_CALENDAR_V1',
            'ticker': '069500', 'dates': premove_calendar, 'source': premove_calendar_source,
            'response': calendar_frame.attrs.get('c3_source_response'),
            'official_exchange_calendar_certified': False, 'regular_only_scope_verified': False},
            ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as calendar_error:
        premove_calendar_source['error'] = type(calendar_error).__name__ + ':' + str(calendar_error)

    for code in codes:
        status['download_attempted'] += 1
        try:
            df, source = fetch_ohlcv(code)
            if df is None or df.empty:
                raise ValueError('empty OHLCV')

            # Observe before the legacy setup gate, minimum150 rows, and
            # legacy duplicate removal. The observer retains invalid-source
            # evidence without repairing it and cannot approve trades.
            try:
                premove.observe(code, df, source)
            except Exception as premove_error:
                if code not in premove.received:
                    premove.errors[code] = type(premove_error).__name__ + ':' + str(premove_error)
            df = df[~df.index.duplicated(keep='last')].sort_index()
            if len(df) < 150:
                raise ValueError(f'only {len(df)} sessions')

            required = ('시가', '고가', '저가', '종가', '거래량')
            for col in required:
                if col not in df.columns:
                    raise ValueError('missing ' + col)

            if df[list(required)].tail(120).isna().any().any():
                raise ValueError('missing OHLCV values')
            if (df['종가'].tail(120) <= 0).any():
                raise ValueError('nonpositive close')

            latest = pd.Timestamp(df.index[-1]).date()
            if latest > CUTOFF or (CUTOFF - latest).days > 7:
                raise ValueError(f'invalid/stale market data {latest}')

            status['download_succeeded'] += 1
            rec = classify(df)
            status['valid_ohlcv'] += 1
            status['screened'] += 1
            status['ohlcv_sources'][source] = (
                status['ohlcv_sources'].get(source, 0) + 1
            )

            date_string = str(latest)
            latest_dates[date_string] += 1

            if any(rec[k] for k in (
                'breakout', 'first_pullback_proxy', 'reversal_proxy'
            )):
                rec.update(
                    ticker=code,
                    latest_date=date_string,
                    sessions=len(df),
                    data_source=source
                )
                valid_rows.append(rec)
                # Reuse completed OHLCV already downloaded during full scan.
                # This avoids a second round of API requests for stop research.
                for bar_date, bar in df.tail(120).iterrows():
                    candidate_daily_bars.append({
                        'ticker': code, 'date': pd.Timestamp(bar_date).date().isoformat(),
                        'open': float(bar['시가']), 'high': float(bar['고가']),
                        'low': float(bar['저가']), 'close': float(bar['종가']),
                        'volume': float(bar['거래량']), 'data_source': source,
                    })

        except Exception as e:
            if code not in premove.received and code not in premove.errors:
                premove.errors[code] = 'SOURCE_UNAVAILABLE:' + type(e).__name__ + ':' + str(e)
            status['failed'] += 1
            record_error(f'{code}: {type(e).__name__}: {e}')

        if status['download_attempted'] % 50 == 0:
            save_status()
        time.sleep(float(os.getenv('REQUEST_DELAY', '0.2')))

    status['market_data_date_counts'] = dict(sorted(latest_dates.items()))
    if latest_dates:
        reference_date, reference_count = max(
            latest_dates.items(),
            key=lambda item: (item[1], item[0])
        )
        status['reference_market_date'] = reference_date
        status['market_data_date'] = reference_date
        status['reference_date_source'] = 'MOST_COMMON_VALID_OHLCV_DATE'
        status['data_date_verified'] = (
            reference_count / max(1, sum(latest_dates.values())) >= 0.95
        )

    try:
        observed = premove.finish(OUT, status['reference_market_date'] or CUTOFF.isoformat(),
                                  premove_calendar, premove_calendar_source)
        status['premove_observation_audit_completed'] = observed['observation_audit_completed']
        status['premove_price_stage_cases'] = observed['price_stage_case_count']
        status['premove_source_count'] = observed['observed_source_count']
    except Exception as premove_error:
        record_premove_failure(OUT, CUTOFF.isoformat(), premove_error)
        status['premove_observation_audit_completed'] = False
        status['premove_price_stage_cases'] = 0
        registered_failure(OUT,CUTOFF.isoformat(),premove_error)

    rows = [
        rec for rec in valid_rows
        if rec['latest_date'] == status['reference_market_date']
    ]
    status['candidate_date_mismatch'] = len(valid_rows) - len(rows)

    names_ok = 0
    for rec in rows:
        try:
            name = str(stock.get_market_ticker_name(rec['ticker']) or '').strip()
        except Exception:
            name = ''
        rec['name'] = name
        rec['instrument_type'] = (
            special_type_from_name(name) if name else 'UNKNOWN'
        )
        names_ok += bool(name)

    status['candidate_names_resolved'] = names_ok
    status['candidate_instrument_type_unknown'] = sum(
        r['instrument_type'] == 'UNKNOWN' for r in rows
    )
    status['candidate_turnover_estimated'] = sum(
        r['turnover_source'] != 'SOURCE_REPORTED' for r in rows
    )

    status['coverage_ratio'] = round(
        status['screened'] / len(codes), 4
    )
    status['scan_complete'] = (
        status['coverage_ratio'] >= 0.95
        and status['data_date_verified']
    )

    if status['scan_complete'] and rows:
        pd.DataFrame(rows).sort_values(
            ['score', 'rvol20'], ascending=False
        ).to_csv(
            OUT / 'candidates.csv',
            index=False,
            encoding='utf-8-sig'
        )
        allowed_codes = {rec['ticker'] for rec in rows}
        with (OUT / 'candidate_daily_history_v52.csv').open(
            'w', encoding='utf-8-sig', newline=''
        ) as history_output:
            history_writer = csv.DictWriter(history_output, fieldnames=(
                'ticker', 'date', 'open', 'high', 'low', 'close',
                'volume', 'data_source'
            ))
            history_writer.writeheader()
            history_writer.writerows(
                bar for bar in candidate_daily_bars
                if bar['ticker'] in allowed_codes
            )
    else:
        (OUT / 'candidates.csv').unlink(missing_ok=True)
        (OUT / 'candidate_daily_history_v52.csv').unlink(missing_ok=True)

    save_status()
    print(json.dumps(status, ensure_ascii=False))

    if not status['scan_complete']:
        raise RuntimeError(
            'Incomplete or inconsistent KRX scan: '
            f'coverage={status["coverage_ratio"]:.1%}, '
            f'date_verified={status["data_date_verified"]}; '
            'see reports/status.json'
        )

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        record_error('Fatal: ' + repr(e))
        save_status()
        traceback.print_exc()
        raise



