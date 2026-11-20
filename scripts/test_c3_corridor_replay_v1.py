"""Offline replay checks; optional frozen artifact integrity test."""
import os, tempfile, unittest
import pandas as pd
from c3_corridor_replay_v1 import (
    observed_unbroken_pivot_high, read_bundle, load_and_audit,
    run, research_score, atr_14)
from c3_entry_corridor_v1 import build_corridors

class TestCohortReplay(unittest.TestCase):
    def bars(self):
        b=pd.DataFrame({'date':[f'2026-10-{i:02d}' for i in range(1,19)],
                        'open':[100.]*18,'high':[105.]*18,'low':[95.]*18,
                        'close':[100.]*18,'volume':[500]*18})
        b.loc[8,'high']=122.
        return b

    def test_two_future_bars_required_to_confirm_pivot(self):
        b=self.bars()
        self.assertIsNone(observed_unbroken_pivot_high(b.iloc[:10].copy(),100.,'2026-10-10')[0])
        self.assertEqual(observed_unbroken_pivot_high(b.iloc[:11].copy(),100.,'2026-10-11')[0],122.)

    def test_breached_pivot_not_resistance(self):
        b=self.bars();b.loc[13,'high']=123.
        high,date,_=observed_unbroken_pivot_high(b,100.,'2026-10-18')
        self.assertEqual((high,date),(123.,'2026-10-14'))

    def test_wrong_asof_is_error(self):
        with self.assertRaisesRegex(ValueError,'UNVERIFIED_TAIL_DATE'):
            observed_unbroken_pivot_high(self.bars(),100.,'2026-10-17')

    def test_atr_positive(self):
        self.assertGreater(atr_14(self.bars()),0)

    def test_ranking_not_trade_authorization(self):
        x=build_corridors(asof='2026-10-30',close=10000,atr14=350,
            confirmed_support=9600,structural_stop=9250,
            verified_first_resistance=11800,support_confirmed_at='2026-10-28',
            resistance_source='5bar')
        score,near,potential=research_score('EARLY_LAUNCH',6.,56.,x,10000,350)
        self.assertGreater(score,0)
        self.assertTrue(near)
        self.assertFalse(x['buy_approved'])
        self.assertFalse(x['orders_enabled'])

    @unittest.skipUnless(os.getenv('C3_REPLAY_ARTIFACT_PATH'),'No frozen artifact supplied')
    def test_real_frozen_cohort(self):
        path=os.environ['C3_REPLAY_ARTIFACT_PATH']
        raw=read_bundle(path)
        asof,stage,reg,obs,hist,names=load_and_audit(raw)
        self.assertEqual(asof,'2026-10-30')
        self.assertEqual(len(names),36)
        with tempfile.TemporaryDirectory() as d:
            result=run(path,d)
        self.assertEqual(result['evaluated_price_stage_count'],stage['price_stage_case_count'])
        self.assertEqual([x['ticker'] for x in result['research_top2']],['271560','012630'])
        self.assertFalse(result['trade_approved'])
        self.assertFalse(result['regular_only_source_certified'])

    @unittest.skipUnless(os.getenv('C3_REPLAY_ARTIFACT_PATH'),'No frozen artifact supplied')
    def test_reject_modified_frozen_observations(self):
        raw=read_bundle(os.environ['C3_REPLAY_ARTIFACT_PATH'])
        raw['c3_premove_observations_v1.csv']+=b'0'
        with self.assertRaisesRegex(ValueError,'STAGE_SHA256_MISMATCH'):
            load_and_audit(raw)

if __name__=='__main__':unittest.main()
