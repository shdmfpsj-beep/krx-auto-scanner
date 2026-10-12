#!/usr/bin/env python3
"""Small unit tests for v8.8 pre-breakout audit."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from krx_preignition_quality_v88 import features,belongs,make_audit

def bars(seq):
    return [{'date':f'2026-01-{i+1:02d}','o':p,'h':p+2,'l':p-2,'c':p,'v':100+i} for i,p in enumerate(seq)]

class QualityTest(unittest.TestCase):
    def test_clean_below_resistance(self):
        b=bars([10]*25)
        r=features(b,24,13)
        self.assertEqual(r['purity_class'],'CLEAN_PREBREAKOUT')
    def test_previous_breach(self):
        b=bars([10]*25);b[23]['h']=15
        r=features(b,24,13)
        self.assertEqual(r['purity_class'],'PRIOR_BREACH')
    def test_signal_day_probe(self):
        b=bars([10]*25);b[24]['h']=15
        r=features(b,24,13)
        self.assertEqual(r['purity_class'],'SIGNAL_DAY_PROBE')
    def test_no_future_lookahead(self):
        b=bars([10]*25)
        old=features(b,24,13)
        b.extend([{'date':'2026-01-26','o':50,'h':100,'l':1,'c':3,'v':999999}])
        self.assertEqual(old,features(b,24,13))
    def test_unfiltered(self):
        x=features(bars([10]*25),24,13)
        self.assertTrue(belongs(x,'ALL'))
        self.assertTrue(belongs(x,'CLEAN_PREBREAKOUT'))
        self.assertFalse(belongs(x,'PRIOR_BREACH'))

if __name__=='__main__':unittest.main()
