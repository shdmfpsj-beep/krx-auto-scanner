"""Independent FDR OHLCV continuity diagnostic for Samyang Holdings (000070)."""
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
OUT.mkdir(exist_ok=True)


def get_data(label, reader):
    try:
        df = reader()
        if df is None or df.empty:
            return {'source': label, 'status': 'empty', 'rows': 0}, pd.DataFrame()
        df = df.copy()
        df.index = pd.to_datetime(df.index).normalize()
        df = df.loc[START:END].sort_index()
        cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
        df = df[cols]
        df.index.name = 'date'
        df.to_csv(OUT / f'diagnose_000070_{label}.csv', encoding='utf-8-sig')
        return {'source': label, 'status': 'ok', 'rows': len(df),
                'first_date': str(df.index.min().date()) if len(df) else None,
                'last_date': str(df.index.max().date()) if len(df) else None,
                'dates': [str(d.date()) for d in df.index]}, df
    except Exception as exc:
        return {'source': label, 'status': 'error', 'error': str(exc)[:400]}, pd.DataFrame()


def main():
    results = []
    results.append(get_data('fdr_code', lambda: fdr.DataReader(CODE, START, END)))
    # Yahoo listing may not be supported by installed FDR version or Yahoo availability.
    results.append(get_data('fdr_yahoo', lambda: fdr.DataReader('000070.KS', START, END)))
    try:
        from pykrx import stock
        def pykrx_reader():
            df = stock.get_market_ohlcv_by_date('20251024', '20251126', CODE)
            return df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})
        results.append(get_data('pykrx', pykrx_reader))
    except Exception as exc:
        results.append(({'source': 'pykrx', 'status': 'error', 'error': str(exc)[:400]}, pd.DataFrame()))

    base = pd.bdate_range(START, END)
    combined = pd.DataFrame(index=base)
    combined.index.name = 'date'
    for meta, frame in results:
        name = meta['source']
        if not frame.empty:
            combined[f'{name}_open'] = frame['Open'].reindex(base) if 'Open' in frame else pd.NA
            combined[f'{name}_volume'] = frame['Volume'].reindex(base) if 'Volume' in frame else pd.NA
        else:
            combined[f'{name}_open'] = pd.NA
            combined[f'{name}_volume'] = pd.NA
    combined.to_csv(OUT / 'diagnose_000070_comparison.csv', encoding='utf-8-sig')
    summary = {'run_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
               'ticker': CODE, 'period': [START, END],
               'sources': [meta for meta, _ in results],
               'notes': ['Business-day index includes holidays; missing entries are not automatically trading halts.',
                         'A missing quote from multiple vendors does not establish an official trading suspension.',
                         'Confirm any halt against KRX/KIND disclosures before interpretation.']}
    (OUT / 'diagnose_000070_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
