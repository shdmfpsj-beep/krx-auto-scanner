"""Diagnose 000070 OHLCV and reproduce v1.6 price-row exclusion rules."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import pandas as pd

CODE = '000070'
START = '2025-10-24'
END = '2025-11-26'
OUT = Path('reports')
OUT.mkdir(parents=True, exist_ok=True)
COLS = ['Open', 'High', 'Low', 'Close', 'Volume']


def fetch(label, reader):
    try:
        df = reader()
        if df is None or df.empty:
            return {'source': label, 'status': 'empty', 'rows': 0}, pd.DataFrame(columns=COLS)
        df = df.copy()
        df.index = pd.to_datetime(df.index).normalize()
        df = df.loc[START:END].sort_index()
        df = df[~df.index.duplicated(keep='last')]
        for col in COLS:
            if col not in df.columns:
                df[col] = pd.NA
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df[COLS]
        df.index.name = 'date'
        df.to_csv(OUT / f'diagnose_000070_{label}_ohlcv.csv', encoding='utf-8-sig')
        return {'source': label, 'status': 'ok', 'rows': len(df)}, df
    except Exception as exc:
        return {'source': label, 'status': 'error', 'error': str(exc)[:400]}, pd.DataFrame(columns=COLS)


def classify(row):
    if row.isna().any():
        return 'excluded_missing_ohlcv'
    if (row[['Open', 'High', 'Low', 'Close']] <= 0).any():
        return 'excluded_nonpositive_price'
    if row['Volume'] <= 0:
        return 'excluded_zero_volume'
    return 'included'


def main():
    sources = []
    sources.append(fetch('fdr_code', lambda: fdr.DataReader(CODE, START, END)))
    try:
        from pykrx import stock
        def pykrx_reader():
            x = stock.get_market_ohlcv_by_date('20251024', '20251126', CODE)
            return x.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})
        sources.append(fetch('pykrx', pykrx_reader))
    except Exception as exc:
        sources.append(({'source': 'pykrx', 'status': 'error', 'error': str(exc)[:400]}, pd.DataFrame(columns=COLS)))

    # Use the union of returned dates; a business-day range alone includes holidays.
    all_dates = sorted(set().union(*(set(frame.index) for _, frame in sources)))
    if not all_dates:
        all_dates = list(pd.bdate_range(START, END))
    combined = pd.DataFrame(index=pd.DatetimeIndex(all_dates, name='date'))
    stats = []
    for meta, frame in sources:
        label = meta['source']
        aligned = frame.reindex(combined.index)
        for col in COLS:
            combined[f'{label}_{col.lower()}'] = aligned[col]
        reasons = []
        for day, row in aligned.iterrows():
            if day not in frame.index:
                reasons.append('missing_date')
            else:
                reasons.append(classify(row))
        combined[f'{label}_filter'] = reasons
        counts = pd.Series(reasons).value_counts().to_dict()
        stats.append({**meta, 'filter_counts': {str(k): int(v) for k, v in counts.items()}})
    if len(sources) == 2:
        left, right = sources[0][0]['source'], sources[1][0]['source']
        combined['open_difference'] = combined[f'{left}_open'] - combined[f'{right}_open']
        combined['volume_difference'] = combined[f'{left}_volume'] - combined[f'{right}_volume']
    combined.to_csv(OUT / 'diagnose_000070_ohlcv_comparison.csv', encoding='utf-8-sig')
    focus = combined.loc['2025-10-27':'2025-11-24']
    summary = {
        'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'ticker': CODE,
        'period': [START, END],
        'sources': stats,
        'focus_dates': [str(d.date()) for d in focus.index],
        'focus_fdr_filter_counts': {str(k): int(v) for k, v in focus['fdr_code_filter'].value_counts().to_dict().items()},
        'notes': [
            'Filter reproduces v1.6: drop NA, nonpositive OHLC, or Volume <= 0.',
            'Dates and OHLCV from vendors do not establish official trading suspension.',
            'FDR adjusted historical prices may not represent executable prices.',
            'Compare report CSV for per-day values and reasons.'
        ]
    }
    (OUT / 'diagnose_000070_ohlcv_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('\nDATE-BY-DATE FILTER AND OHLCV (2025-10-27 to 2025-11-24)')
    print(focus.to_string())


if __name__ == '__main__':
    main()
