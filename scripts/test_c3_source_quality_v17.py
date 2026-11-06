"""Regression faults only. They do not register or correct production signals."""
import copy,unittest
from c3_runtime_v10 import quality
from c3_data_quality_v17 import classify_bar
from c3_forward_report_v8 import registration_note


def row(market='KOSPI'):
    return dict(ticker='000001' if market=='KOSPI' else '000002',market=market,asof='2026-11-06',open=100,high=110,low=90,close=105,volume=10,turnover_krw=1000)


class SourceQualityTests(unittest.TestCase):
    def check(self,changes):
        baseline=[row(),row('KOSDAQ')];rows=copy.deepcopy(baseline);rows[0].update(changes)
        return quality(rows,baseline,'2026-11-06')
    def test_zero_volume_positive_value_is_not_a_halt(self):
        self.assertIn('INVALID_OHLC:KOSPI',self.check(dict(volume=0,turnover_krw=100))['errors'])
    def test_impossible_zero_volume_ohlc_is_not_a_halt(self):
        self.assertTrue(self.check(dict(open=1000,volume=0,turnover_krw=0))['errors'])
    def test_fractional_shares_are_rejected(self):self.assertTrue(self.check(dict(volume=0.5))['errors'])
    def test_zero_trade_bar_remains_observable_but_untradable(self):
        self.assertFalse(self.check(dict(open=0,high=0,low=0,volume=0,turnover_krw=0))['errors'])
        self.assertEqual(classify_bar(dict(row(),open=0,high=0,low=0,volume=0,turnover_krw=0)),'NO_TRADES_OBSERVED')
    def test_registered_signal_is_not_labeled_a_preview(self):
        s=registration_note(dict(research_top2_registered_for_source_session=True,new_decision_registered=True))
        self.assertIn('실제 등록',s);self.assertNotIn('미등록',s)
    def test_rerun_of_registered_session_keeps_registered_label(self):
        self.assertIn('실제 등록',registration_note(dict(research_top2_registered_for_source_session=True,new_decision_registered=False)))
    def test_unregistered_old_candidate_stays_preview(self):
        self.assertIn('미등록 연구 미리보기',registration_note(dict(research_top2_registered_for_source_session=False)))


if __name__=='__main__':unittest.main()
