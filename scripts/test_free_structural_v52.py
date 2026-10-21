#!/usr/bin/env python3
"""Offline regression tests: no network, no orders, no future bars."""
import unittest
from datetime import date,timedelta
from free_structural_v52 import history_check,structural_row,build,last_confirmed_pivot

def history(n=100):
    first=date(2026,6,1)
    rows=[]
    for i in range(n):
        close=100+i*.4
        low=close-9 if i==n-12 else close-2
        rows.append(dict(date=(first+timedelta(days=i)).isoformat(),ticker='005930',
           open=str(close-.4),high=str(close+2),low=str(low),close=str(close),
           volume='1000',data_source='pykrx'))
    return rows

def candidate(rows):
    return dict(ticker='005930',name='fixture',latest_date=rows[-1]['date'],
       data_source='pykrx',turnover_source='SOURCE_REPORTED',instrument_type='COMMON')

def ranking():
    return dict(ticker='005930',c3_preliminary_score='65',k100_preliminary_score='60')

class FreeStructuralTests(unittest.TestCase):
    def test_pivot_stop_never_live_buy(self):
        rows=history();snapshot=date.fromisoformat(rows[-1]['date'])
        out=structural_row(candidate(rows),rows,snapshot,ranking(),ranking())
        self.assertEqual(out['trade_approval'],'NO')
        self.assertEqual(out['confirmed_pivot_date'],rows[-12]['date'])
        self.assertGreater(float(out['structural_stop_reference']),0)
        self.assertLess(float(out['structural_stop_reference']),float(out['close_reference']))
    def test_misaligned_snapshot_rejected(self):
        rows=history()
        self.assertEqual(history_check(rows,'005930',date.fromisoformat(rows[-2]['date']))[1],
                         'HISTORY_DATE_MISMATCH')
    def test_duplicate_and_invalid_ohlc_rejected(self):
        rows=history()
        self.assertEqual(history_check(rows+[rows[-1]],'005930',
          date.fromisoformat(rows[-1]['date']))[1],'HISTORY_NOT_CHRONOLOGICAL')
        bad=rows.copy();bad[-1]={**rows[-1],'low':'999'}
        self.assertEqual(history_check(bad,'005930',date.fromisoformat(rows[-1]['date']))[1],
                         'INVALID_HISTORY_OHLC')
    def test_unconfirmed_last_bar_never_pivot(self):
        rows=history();bars,_=history_check(rows,'005930',date.fromisoformat(rows[-1]['date']))
        self.assertNotEqual(last_confirmed_pivot(bars)[0],bars[-1]['date'])
    def test_stale_market_data_cash(self):
        rows=history();d=date.fromisoformat(rows[-1]['date'])
        status=dict(market_data_date=str(d),coverage_ratio=.99,scan_complete=True,
                    data_date_verified=True)
        _,report=build(status,[candidate(rows)],rows,[ranking()],[ranking()],d+timedelta(days=8))
        self.assertEqual(report['decision'],'CASH')
        self.assertFalse(report['trade_approved'])
        self.assertIn('MARKET_DATA_STALE_OR_FUTURE',report['global_blockers'])
    def test_special_stock_is_excluded(self):
        rows=history();d=date.fromisoformat(rows[-1]['date'])
        row={**candidate(rows),'instrument_type':'NON_COMMON_OR_SPECIAL'}
        result=structural_row(row,rows,d,ranking(),ranking())
        self.assertIn('SPECIAL_INSTRUMENT_EXCLUDED',result['blocking_reasons'])
        self.assertEqual(result['structure_status'],'WAIT_DATA_OR_STRUCTURE')
    def test_missing_history_no_fabricated_stop(self):
        rows=history();d=date.fromisoformat(rows[-1]['date'])
        result=structural_row(candidate(rows),[],d,ranking(),ranking())
        self.assertEqual(result['structural_stop_reference'],'')
        self.assertEqual(result['trade_approval'],'NO')

if __name__=='__main__':unittest.main()
