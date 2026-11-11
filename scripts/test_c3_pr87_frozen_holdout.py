import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_pr87_frozen_holdout import evaluate,wilson,ci,entry_touch

def base_cohort():
    items=[{"ticker":f"{i:06d}","date":"2026-06-30","features":{}} for i in range(78)]
    return {"events":items,"deduplicated_events":78,"horizon_groups":{"20":{"observed":43}}}

class FrozenHoldoutTests(unittest.TestCase):
    def test_wilson_and_ci(self):
        l,h=wilson(5,20)
        self.assertLess(l,.25)
        self.assertGreater(h,.25)
        self.assertIsNone(wilson(0,0))
        self.assertEqual(ci([7]*10),[7.0,7.0])

    def test_missing_original_event_fail_closed(self):
        b=base_cohort()
        with self.assertRaisesRegex(ValueError,"FROZEN_PR87_COHORT_NOT_PRESERVED"):
            evaluate(b,{"events":[]},{"events":[]})

    def test_future_matured_label_excluded_from_training(self):
        b=base_cohort()
        new={"ticker":"999999","date":"2026-09-16","features":{
            "momentum_20d_pct":1.,"rvol_20d":1.,"ma20_extension_pct":1.,
            "ma20_vs_ma60_pct":1.,"stop_distance_pct":1.}}
        ex={"events":b["events"]+[new]}
        q=[]
        for e in ex["events"]:
            h={str(n):{"quality":"CENSORED","maturity_date":None} for n in (5,10,20)}
            if e["ticker"] in ("000000","999999"):
                for n in (5,10,20):
                    h[str(n)]={"quality":"QC_VALID_EXPLORATORY","maturity_date":"2026-09-20"}
            q.append({"ticker":e["ticker"],"date":e["date"],"asof_quality":[],"horizons":h})
            e["outcomes"]={str(n):({"close_return_pct":1.,"mfe_pct":2.,"mae_pct":-1.}
                  if e["ticker"] in ("000000","999999") else {}) for n in (5,10,20)}
        result=evaluate(b,ex,{"events":q,"market_sessions":150})
        for n in (5,10,20):
            self.assertEqual(result["periods"][str(n)]["train_n"],0)
            self.assertEqual(result["periods"][str(n)]["holdout_n"],1)
        self.assertFalse(result["predictor_promotion"])
        self.assertEqual(result["decision"],"CASH")

    def test_no_next_session_without_source(self):
        r=entry_touch({"ticker":"000001","date":"2026-09-16",
                       "features":{"stop_distance_pct":3}}, {},[])
        self.assertEqual(r["status"],"BLOCKED_NO_NEXT_MARKET_SESSION")
        self.assertIsNone(r["trade_pnl"])

if __name__=="__main__":unittest.main()
