import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import c3_research_v637 as r
import c3_eligibility_v637 as e
from c3_event_replay_v637 import Policy,replay


class EligibilityTests(unittest.TestCase):
    def setUp(self):self.common=dict(name='시험보통주',security_group='주권',share_kind='보통주')
    def test_explicit_common_equity(self):self.assertTrue(e.classify(self.common,'반도체 제조업')[0])
    def test_preferred_share_excluded(self):self.assertFalse(e.classify(dict(self.common,share_kind='우선주'),'기타 금융업')[0])
    def test_etf_excluded(self):self.assertFalse(e.classify(dict(self.common,security_group='수익증권'),'반도체')[0])
    def test_reit_excluded(self):self.assertFalse(e.classify(dict(self.common,security_group='부동산투자회사'),'부동산 임대업')[0])
    def test_pharma_excluded(self):self.assertEqual(e.classify(self.common,'의약품 제조업')[1],'PHARMA_BIO_EXCLUDED')
    def test_biotech_research_excluded(self):self.assertFalse(e.classify(self.common,'자연과학 연구개발업')[0])
    def test_unknown_industry_not_assumed_eligible(self):self.assertFalse(e.classify(self.common,None)[0])
    def test_devices_not_automatically_pharma(self):self.assertTrue(e.classify(self.common,'의료용 기기 제조업')[0])
    def test_spac_excluded(self):self.assertFalse(e.classify(dict(self.common,name='하나스팩보통주'),'금융 지원 서비스업')[0])
    def test_missing_issuer_rejected(self):self.assertFalse(e.classify(None,'전자부품 제조업')[0])


class ResearchDiagnosticsTests(unittest.TestCase):
    def rows(self):
        return [dict(asof='2026-01-02',ticker='000001',V632_BASE=5.,BALANCED_LEADER=1.,signal_close=100.,stopD=94.,atr14=2.,market_trend=True),
                dict(asof='2026-01-02',ticker='000002',V632_BASE=3.,BALANCED_LEADER=6.,signal_close=100.,stopD=94.,atr14=2.,market_trend=True)]
    def test_original_rank_uses_d_features(self):self.assertEqual(r.select_D(self.rows(),'V632_BASE')[0]['ticker'],'000001')
    def test_balanced_rank_uses_d_features(self):self.assertEqual(r.select_D(self.rows(),'BALANCED_LEADER')[0]['ticker'],'000002')
    def test_future_outcomes_cannot_change_selection(self):
        rows=self.rows();a=r.select_D(rows,'V632_BASE')
        rows[0]['future_return']=-99.;rows[1]['future_return']=999.
        self.assertEqual(a[0]['ticker'],r.select_D(rows,'V632_BASE')[0]['ticker'])
    def test_unknown_rank_rejected(self):
        with self.assertRaises(ValueError):r.select_D(self.rows(),'BEST_FUTURE')
    def test_random_selector_deterministic(self):self.assertEqual(r.selected_random(self.rows(),637000),r.selected_random(self.rows(),637000))
    def test_random_selector_ignores_outcome(self):
        rows=self.rows();a=r.selected_random(rows,637001)[0]['ticker']
        rows[0]['future_return']=-100.;rows[1]['future_return']=100.
        self.assertEqual(a,r.selected_random(rows,637001)[0]['ticker'])
    def test_enrichment_no_future_peek(self):
        days=pd.bdate_range('2025-09-01',periods=80).strftime('%Y-%m-%d')
        x=pd.DataFrame(dict(Date=days,Open=range(100,180),High=range(102,182),Low=range(98,178),Close=range(101,181)))
        a=r.enrich(x.iloc[:70]).iloc[-1]
        b=x.copy();b.loc[70:,'Close']=100000.
        z=r.enrich(b).iloc[69]
        self.assertEqual(a['atr14'],z['atr14']);self.assertEqual(a['ma20'],z['ma20'])
    def test_invalid_price_ordering_rejected(self):
        x=pd.DataFrame(dict(Date=['2026-01-02','2026-01-02'],Open=[1,1],High=[2,2],Low=[1,1],Close=[1,1]))
        with self.assertRaises(ValueError):r.enrich(x)
    def test_monthly_marks_keep_idle_months(self):
        run=dict(summary=dict(initial_cash=100.),daily=[dict(date='2026-01-30',equity_krw=100.),dict(date='2026-02-27',equity_krw=100.)])
        self.assertEqual([m['pnl_krw'] for m in r.monthly(run)],[0.,0.])
    def test_monthly_pnl_sums_to_equity(self):
        run=dict(summary=dict(initial_cash=100.),daily=[dict(date='2026-01-30',equity_krw=90.),dict(date='2026-02-27',equity_krw=105.)])
        self.assertEqual(sum(m['pnl_krw'] for m in r.monthly(run)),5.)
    def test_replay_end_equity_includes_open_mark(self):
        dates=['2026-01-02','2026-01-05'];bar=dict(date=dates[1],open=100.,high=103.,low=99.,close=102.,atr14=2.,ma5=100.)
        rr=replay(dates,{'000001':{dates[1]:bar}},[self.rows()[0]],Policy())
        self.assertEqual(rr['summary']['open_position_count'],1)
        self.assertAlmostEqual(rr['summary']['final_equity_krw']-1e6,rr['summary']['open_liquidation_pnl_krw'])


if __name__=='__main__':unittest.main()
