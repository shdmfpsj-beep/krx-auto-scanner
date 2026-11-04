import unittest
from c3_ict_observable_features_v1 import features

def b(day,o,h,l,c):
    return dict(date=day,open=o,high=h,low=l,close=c)

class ICTFeatureTests(unittest.TestCase):
    def test_sweep_reclaim_uses_only_prior_bars(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.append(b("10",91,105,89,95))
        x=features(bars)[-1]
        self.assertTrue(x["sweep_reclaim"])
        self.assertFalse(x["bullish_structure_break"])
        self.assertFalse(x["bullish_fvg"])
        # Future bar cannot change the historical signal.
        bars.append(b("11",100,200,50,150))
        self.assertEqual(features(bars)[10],x)

    def test_breakout_and_fvg(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        bars.append(b("10",112,121,111,119))
        x=features(bars)[-1]
        self.assertTrue(x["bullish_structure_break"])
        self.assertTrue(x["bullish_fvg"])
        self.assertFalse(x["sweep_reclaim"])

    def test_warmup_and_lookback(self):
        bars=[b(str(i),100,110,90,100) for i in range(10)]
        self.assertFalse(any(x["sweep_reclaim"] for x in features(bars)))
        with self.assertRaises(ValueError):
            features(bars,lookback=2)

if __name__=="__main__":
    unittest.main()
