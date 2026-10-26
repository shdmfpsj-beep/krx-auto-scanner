import copy,unittest
import numpy as np
import pandas as pd
import c3_research_v638 as r
import c3_followup_v638 as f
from c3_research_v637 import _bars


class StopFirstFeaturesTests(unittest.TestCase):
    def fixture(self):
        closes=[10000.]*50+[9400.]*34+[9410.,9440.,9480.,9500.,9550.,10050.]
        days=pd.bdate_range('2025-09-01',periods=90).strftime('%Y-%m-%d').tolist()
        frame=pd.DataFrame(dict(Date=days,Open=[c-20 for c in closes],High=[c+30 for c in closes],
            Low=[c-200 for c in closes],Close=closes,Volume=[1000.]*89+[1400.],TurnoverKRW=[6e9]*90))
        frame.loc[82,'Low']=9100.
        return frame

    def test_actual_confirmed_stop_used_for_structure_rank(self):
        x=r.features(self.fixture());bars=_bars(x);bench=x.set_index('Date')
        s,why=r.candidate_from_index(x,bars,89,'000001',r.PATTERNS[0],bench)
        self.assertIsNone(why)
        compact_risk=100*(s['signal_close']-float(x.iloc[89].rolling3_stop))/s['signal_close']
        self.assertAlmostEqual(s['STRUCTURE_D_SCORE']-s['LEGACY_D_SCORE'],.45*(compact_risk-s['riskD_pct']))

    def test_future_prices_cannot_change_D_candidate(self):
        frame=self.fixture();x=r.features(frame);bars=_bars(x)
        before,_=r.candidate_from_index(x,bars,89,'000001',r.PATTERNS[0],x.set_index('Date'))
        row=frame.iloc[-1].copy();row['Date']='2026-12-30';row['Close']=1e9;row['High']=1e9+100
        z=r.features(pd.concat([frame,pd.DataFrame([row])],ignore_index=True));after,_=r.candidate_from_index(z,_bars(z),89,'000001',r.PATTERNS[0],z.set_index('Date'))
        self.assertEqual(before,after)

    def test_broken_stop_cannot_enter_candidate_pool(self):
        frame=self.fixture();frame.loc[89,'Low']=8900.
        x=r.features(frame);s,reason=r.candidate_from_index(x,_bars(x),89,'000001',r.PATTERNS[0],x.set_index('Date'))
        self.assertIsNone(s);self.assertEqual(reason,'NO_UNBROKEN_DAILY_PIVOT')

    def test_invalid_bar_breaks_65_bar_readiness(self):
        frame=self.fixture();frame.loc[80,['Open','High','Low','Close']]=0.
        x=r.features(frame);self.assertFalse(bool(x.iloc[-1].valid65))

    def test_selection_ignores_future_outcome_columns(self):
        rows=[dict(pattern=r.PATTERNS[0],asof='2026-01-02',ticker='000001',LEGACY_D_SCORE=2.),
              dict(pattern=r.PATTERNS[0],asof='2026-01-02',ticker='000002',LEGACY_D_SCORE=1.)]
        a=r.choose_D(rows,r.PATTERNS[0],'LEGACY_D_SCORE')[0]['ticker']
        rows[0]['future_return']=-100;rows[1]['future_return']=100
        self.assertEqual(a,r.choose_D(rows,r.PATTERNS[0],'LEGACY_D_SCORE')[0]['ticker'])

    def test_unknown_rank_is_rejected(self):
        with self.assertRaises(ValueError):r.choose_D([],r.PATTERNS[0],'FUTURE_WINNER')
    def test_future_session_is_rejected_before_source_read(self):
        with self.assertRaisesRegex(ValueError,'REQUESTED_SESSION_NOT_COMPLETED'):
            r.load_pool('must_not_read.zip','must_not_read.csv',last='2999-01-01')

    def test_random_choice_is_reproducible(self):
        rows=[dict(pattern=r.PATTERNS[0],asof='2026-01-02',ticker='000001'),
              dict(pattern=r.PATTERNS[0],asof='2026-01-02',ticker='000002')]
        self.assertEqual(r.choose_D(rows,r.PATTERNS[0],'LEGACY_D_SCORE',638000),
                         r.choose_D(rows,r.PATTERNS[0],'LEGACY_D_SCORE',638000))

    def test_D_ranked_candidates_have_only_same_day_members(self):
        rows=[dict(asof='2026-01-02',ticker='000001',rs20=3.,rs5=1.,turnover_accel=1.,LEGACY_D_SCORE=1.),
              dict(asof='2026-01-02',ticker='000002',rs20=2.,rs5=2.,turnover_accel=2.,LEGACY_D_SCORE=2.),
              dict(asof='2026-01-05',ticker='000003',rs20=9.,rs5=9.,turnover_accel=9.,LEGACY_D_SCORE=9.)]
        got=f.D_choices(rows,'LEGACY_D_SCORE',alternatives=True)
        self.assertEqual(len(got[0]['D_ranked_candidates']),2)
        self.assertTrue(all(c['asof']==got[0]['asof'] for c in got[0]['D_ranked_candidates']))

    def test_relative_rank_has_no_fitted_weights(self):
        rows=[dict(asof='2026-01-02',ticker='000001',rs20=3.,rs5=1.,turnover_accel=1.),
              dict(asof='2026-01-02',ticker='000002',rs20=2.,rs5=2.,turnover_accel=2.)]
        self.assertEqual(f.D_choices(rows,'RS20_THEN_MONEY')[0]['ticker'],'000001')


if __name__=='__main__':unittest.main()
