import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_temporal_quality_validation import auc,audit_segment,feature_asof,evaluate

class TemporalQualityTests(unittest.TestCase):
    def test_auc_ties_and_no_positive_class(self):
        self.assertEqual(auc([True,False,True,False],[2,1,2,1]),1)
        self.assertEqual(auc([True,False],[2,2]),.5)
        self.assertIsNone(auc([True,True],[1,2]))

    def test_feature_has_no_future_access(self):
        bars=[{'date':f'd{i:03}','close':100+i,'volume':1000+i} for i in range(85)]
        original=feature_asof(bars,60)
        bars[70]['close']=99999
        self.assertEqual(original,feature_asof(bars,60))

    def test_missing_ticker_sessions_and_unexplained_price_gap(self):
        bars=[{'date':'d0','close':100},{'date':'d3','close':101}]
        index={'d0':0,'d1':1,'d2':2,'d3':3}
        self.assertIn('TICKER_MARKET_SESSION_GAP',audit_segment(bars,1,1,index))
        bars[1]['close']=200
        self.assertIn('UNEXPLAINED_CLOSE_DISCONTINUITY',audit_segment(bars,1,1,index))

    def test_no_trading_or_regime_mutation(self):
        result=evaluate([],{'events':[]})
        self.assertEqual(result['decision'],'CASH')
        self.assertFalse(result['feature_weights_changed'])
        self.assertFalse(result['operational_top2_changed'])
        self.assertFalse(result['trading_approved'])
        self.assertEqual(result['horizon_groups']['20']['qc_valid'],0)

    def test_missing_data_cannot_imply_continuation(self):
        result=evaluate([],{ 'events':[] })
        self.assertEqual(result['continuation_common20']['common_quality_valid_20'],0)
        self.assertEqual(result['continuation_common20']['up_all_5_10_20d'],0)

    def test_duplicate_source_is_rejected(self):
        bar={'ticker':'000001','date':'d0','open':10,'high':11,'low':9,'close':10,'volume':100}
        with self.assertRaisesRegex(ValueError,'DUPLICATE_TICKER_DATE_SOURCE'):
            evaluate([bar,bar],{'events':[]})

if __name__=='__main__':unittest.main()
