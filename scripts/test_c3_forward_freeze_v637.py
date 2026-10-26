import copy
import json
from pathlib import Path
import tempfile
import unittest
import pandas as pd

import c3_forward_freeze_v637 as f
from c3_research_v637 import enrich


class ForwardFreezeTests(unittest.TestCase):
    def fixture(self):
        closes=[10000.]*50+[9400.]*34+[9410.,9440.,9480.,9500.,9550.,10050.]
        days=pd.bdate_range('2025-09-01',periods=len(closes)).strftime('%Y-%m-%d').tolist()
        x=pd.DataFrame(dict(Date=days,Open=[c-20 for c in closes],High=[c+30 for c in closes],
                            Low=[c-200 for c in closes],Close=closes,Volume=[1000.]*89+[1400.],
                            TurnoverKRW=[4e9]*90))
        b=enrich(x);b['ret5']=100*(b.Close/b.Close.shift(5)-1);b['ret20']=100*(b.Close/b.Close.shift(20)-1)
        return x,b.set_index('Date'),days[-1]
    def test_candidate_uses_completed_D(self):
        x,b,d=self.fixture();r=f.candidate_on_D(x,'000001',d,b)
        self.assertIsNotNone(r);self.assertEqual(r['asof'],d)
    def test_future_price_append_cannot_change_today_candidate(self):
        x,b,d=self.fixture();a=f.candidate_on_D(x,'000001',d,b)
        row=x.iloc[-1].copy();row['Date']='2026-12-30';row['Close']=1e9
        extended=pd.concat([x,pd.DataFrame([row])],ignore_index=True)
        self.assertEqual(a,f.candidate_on_D(extended,'000001',d,b))
    def test_future_source_without_D_row_not_accepted(self):
        x,b,d=self.fixture();self.assertIsNone(f.candidate_on_D(x.iloc[:-1],'000001',d,b))
    def test_freeze_cannot_be_rewritten_with_new_winner(self):
        with tempfile.TemporaryDirectory() as p:
            path=Path(p)/'freeze.json';f.freeze_once(path,dict(ticker='000001'))
            with self.assertRaises(ValueError):f.freeze_once(path,dict(ticker='000002'))
    def test_identical_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as p:
            path=Path(p)/'freeze.json';a=f.freeze_once(path,dict(ticker='000001'))
            self.assertEqual(a,f.freeze_once(path,dict(ticker='000001')))
    def test_fingerprint_detects_rule_change(self):
        self.assertNotEqual(f.canonical_digest(dict(trail=7)),f.canonical_digest(dict(trail=8)))


if __name__=='__main__':unittest.main()
