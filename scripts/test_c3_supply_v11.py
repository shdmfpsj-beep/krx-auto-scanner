"""Synthetic source safety checks, not market performance tests."""
import io,tempfile,unittest,zipfile
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from c3_supply_v11 import rows_from_frame,compare,completed_day,FAMILIES,quality_state,choose_source,seal,open_sealed


def frame():return pd.DataFrame(dict(Open=[100],High=[110],Low=[90],Close=[105],Volume=[1000]),index=pd.to_datetime(['2026-11-05']))


class SupplyV11Tests(unittest.TestCase):
    def rows(self):return rows_from_frame(frame(),'000001','KOSPI','2026-11-05')
    def test_ohlcv_does_not_invent_turnover(self):
        r=self.rows()[0];self.assertTrue(r['valid_ohlcv']);self.assertIsNone(r['turnover_krw'])
    def test_missing_fields_and_duplicate_dates_rejected(self):
        for df in (frame().drop(columns='Open'),pd.concat([frame(),frame()])):
            with self.assertRaises(ValueError):rows_from_frame(df,'000001','KOSPI','2026-11-05')
    def test_future_provider_bars_are_not_current_eod(self):
        with self.assertRaisesRegex(ValueError,'NO_COMPLETED'):rows_from_frame(frame(),'000001','KOSPI','2026-11-04')
    def test_halts_are_not_tradable_bars(self):
        df=frame();df.loc[:,'Open']=0;df.loc[:,'High']=0;df.loc[:,'Low']=0;df.loc[:,'Volume']=0
        r=rows_from_frame(df,'000001','KOSPI','2026-11-05')[0];self.assertTrue(r['halt_like']);self.assertFalse(r['valid_ohlcv'])
    def test_clock_before_close_does_not_request_todays_eod(self):
        self.assertEqual(completed_day(datetime(2026,11,6,0,tzinfo=timezone.utc)),'2026-11-05');self.assertEqual(completed_day(datetime(2026,11,6,7,tzinfo=timezone.utc)),'2026-11-06')
    def test_comparison_separates_missing_turnover_and_missing_counterpart(self):
        a=self.rows();result=compare(a,a,['2026-11-05']);self.assertEqual(result['counts']['MATCH_OHLCV'],1);self.assertEqual(result['counts']['TURNOVER_UNAVAILABLE'],1)
        self.assertEqual(compare(a,[],['2026-11-05'])['counts']['MISSING_COUNTERPART'],1)
    def test_same_vendor_wrappers_are_not_independent(self):
        self.assertEqual(FAMILIES['PYKRX_ADJUSTED'],FAMILIES['FDR_NAVER']);self.assertEqual(FAMILIES['FDR_NAVER'],FAMILIES['NAVER_JSON'])
    def test_same_family_cannot_promote_research_validated(self):
        e=dict(independent_families=['NAVER','NAVER'],current_ohlcv_exact_match=True,price_basis_verified=True,date_and_coverage_verified=True)
        self.assertEqual(quality_state(self.rows(),e),'OHLCV_UNVERIFIED');e['independent_families'].append('OTHER');self.assertEqual(quality_state(self.rows(),e),'RESEARCH_VALIDATED')
    def test_close_only_conflict_and_unavailable_are_distinct(self):
        self.assertEqual(quality_state([],{}),'UNAVAILABLE');self.assertEqual(quality_state([dict(close=100)],{}),'CLOSE_ONLY');self.assertEqual(quality_state(self.rows(),dict(unresolved_conflict=True)),'CONFLICT')
    def test_no_cross_source_turnover_fill_or_partial_universe_promotion(self):
        c=dict(state='RESEARCH_VALIDATED',whole_universe_verified=True,rows=self.rows());self.assertIsNone(choose_source([c]));c['rows'][0]['turnover_krw']=100000;self.assertIs(choose_source([c]),c);c['whole_universe_verified']=False;self.assertIsNone(choose_source([c]))
if __name__=='__main__':unittest.main()
