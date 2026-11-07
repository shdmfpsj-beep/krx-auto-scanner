"""V8 adversarial prospective-evidence and stop-testing criteria.

Every case is synthetic. Separate pinned real archive smoke is in the workflow.
"""
import copy
import unittest
from c3_v8_prospective_contract import evidence_snapshot,review_gate

OLD="2026-11-06T22:30:00+09:00"
NEW="2026-11-07T08:30:00+09:00"
NEXT="2026-11-09T09:00:00+09:00"
SHA="7bad1564f2d017e6bd0481758d0f6e0f8aa0c289"

def source():
    def plan(t,high,low,stop,r1,close):
        return dict(ticker=t,decision_date="2026-11-06",high=high,low=low,
                    stop=stop,resistance=r1,reference_close=close)
    def row(t,n,rank,close,plan_a):
        return dict(ticker=t,name=n,model="B",rank=rank,
            decision_date="2026-11-06",reference_close=close,
            signal_id="immutable-"+t,registered_at="2026-11-06T14:21:39+00:00",
            source_regular_only_certified=False,buy_approved=False,
            entry_plans={
                "A_SUPPORT_LIMIT":dict(plan=plan_a,reason=None),
                "B_CONFIRMED_PULLBACK":dict(plan=None,reason="NO_PLAN"),
                "C_LIMITED_BREAKOUT":dict(plan=None,reason="NO_PLAN")})
    return dict(
        source_price_asof="2026-11-06",
        source_regular_only_certified=False,
        generated_at="2026-11-06T22:07:18+00:00",
        analysis_completed_at="2026-11-06T14:21:39+00:00",
        source_received_at="2026-11-06T22:07:10+00:00",
        new_registered_signals=0,
        research_top2_registered_for_source_session=True,
        research_top2=[
            row("028050","Samsung E&A",1,60500,
                plan("028050",63500,60700,57700,65500,60500)),
            row("030530","Wonik Holdings",2,28300,
                plan("030530",23500,22100,20600,30400,28300))],
    )
def calc(source_doc=None,check_at=NEW):
    return evidence_snapshot(source() if source_doc is None else source_doc,
         check_at=check_at,next_session_open=NEXT,source_commit=SHA)

class V8ForwardEvidence(unittest.TestCase):
    def test_2230_retroactive_future_report_not_visible(self):
        r=calc(check_at=OLD)
        self.assertEqual(r["status"],"ARCHIVED_REPORT_NOT_AVAILABLE_AS_OF_CHECK")
        self.assertIsNone(r["selected_count"])
        self.assertIsNone(r["selected"])

    def test_nov7_sees_original_two_not_zero_new(self):
        r=calc()
        self.assertEqual(r["selected_count"],2)
        self.assertEqual([x["ticker"] for x in r["selected"]],["028050","030530"])
        self.assertEqual(r["status"],"TOP2_REGISTERED_BUT_SOURCE_UNCERTIFIED")
        self.assertEqual(r["current_action"],"CASH")
        self.assertFalse(r["time_of_delivery_independently_verified"])

    def test_provenance_is_not_promoted_from_official_price_parity(self):
        r=calc()
        self.assertFalse(r["official_regular_only_certified"])
        self.assertTrue(all(x["buy_recommendation"]=="NOT_AUTHORIZED"
                         for x in r["selected"]))

    def test_missing_original_rank_does_not_silently_become_no_picks(self):
        s=source()
        s["research_top2"][1]["rank"]=1
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            calc(s)

    def test_non_b_record_rejected(self):
        s=source();s["research_top2"][1]["model"]="A"
        with self.assertRaisesRegex(ValueError,"ORIGINAL_B_TOP2"):
            calc(s)

    def test_future_source_date_not_accepted_as_friday(self):
        s=source();s["research_top2"][0]["decision_date"]="2026-11-09"
        with self.assertRaisesRegex(ValueError,"ORIGINAL_B_TOP2"):
            calc(s)

    def test_second_stock_uses_its_own_stop_resistance(self):
        r=calc()
        a=r["selected"][0]["entry_plan_diagnostics"]["A_SUPPORT_LIMIT"]
        b=r["selected"][1]["entry_plan_diagnostics"]["A_SUPPORT_LIMIT"]
        self.assertLess(a["costed_R1_RR"],1.)
        self.assertTrue("FIRST_RESISTANCE_RR_BELOW_1" in a["review_flags"])
        self.assertGreater(b["gap_from_close_to_limit_pct"],20.)
        self.assertTrue("FROZEN_STOP_DISTANCE_OVER_12_PCT" in b["review_flags"])

    def test_no_registered_evidence_not_improper_verified_zero(self):
        s=source();s["research_top2_registered_for_source_session"]=False
        r=calc(s)
        self.assertEqual(r["status"],"NO_FROZEN_REGISTERED_TOP2_EVIDENCE")
        self.assertIsNone(r["selected_count"])

    def test_invalid_signal_id_rejected(self):
        s=source();s["research_top2"][1]["signal_id"]=s["research_top2"][0]["signal_id"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            calc(s)

    def test_report_received_after_generation_rejected(self):
        s=source();s["source_received_at"]="2026-11-08T10:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"TIME_ORDER"):
            calc(s)

    def test_wrong_signal_ticker_in_frozen_plan_rejected(self):
        s=source();s["research_top2"][0]["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]["ticker"]="030530"
        with self.assertRaisesRegex(ValueError,"PLAN_SIGNAL_IDENTITY"):
            calc(s)

    def test_no_future_outcome_silently_declared_20pct(self):
        r=calc()
        self.assertTrue(all(x["forward_20pct_in_20d"]=="UNKNOWN_UNTIL_MATURED"
                         for x in r["selected"]))
        self.assertTrue(all(x=="FUTURE_OUTCOME_UNMATURED_OR_NOT_READ"
                         for x in r["evaluation_windows"].values()))

    def test_report_after_next_open_not_mislabelled_preopen(self):
        r=calc(check_at="2026-11-09T11:00:00+09:00")
        self.assertEqual(r["status"],"AFTER_NEXT_OPEN_NOT_PREOPEN_DECISION")
        self.assertEqual(r["current_action"],"CASH")

    def test_future_snapshot_no_magic_time_travel(self):
        s=source();s["generated_at"]="2026-11-09T10:00:00+09:00"
        s["source_received_at"]="2026-11-09T09:59:00+09:00"
        r=calc(s)
        self.assertIsNone(r["selected_count"])

    def test_naive_check_timestamp_invalid(self):
        with self.assertRaisesRegex(ValueError,"NAIVE"):
            calc(check_at="2026-11-07T08:30:00")

    def test_report_does_not_modify_original_input(self):
        s=source();before=copy.deepcopy(s);calc(s)
        self.assertEqual(s,before)

    def test_unknown_first_resistance_never_claims_safe(self):
        s=source();s["research_top2"][1]["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]["resistance"]=None
        b=calc(s)["selected"][1]["entry_plan_diagnostics"]["A_SUPPORT_LIMIT"]
        self.assertIn("FIRST_RESISTANCE_MISSING",b["review_flags"])
        self.assertIsNone(b["costed_R1_RR"])

    def test_missing_plan_still_keeps_stock_selection(self):
        s=source();s["research_top2"][0]["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]=None
        r=calc(s)
        self.assertEqual(r["selected_count"],2)
        self.assertEqual(r["selected"][0]["entry_plan_diagnostics"]["A_SUPPORT_LIMIT"]["status"],
                         "NO_ORIGINAL_PLAN")

def episode(d,t,**kw):
    item=dict(decision_date=d,ticker=t,registered_in_advance=True,
        regular_only_certified=True,time_evidence_verified=True,
        independent_episode=True,complete_20d_evidence=True,censored=False)
    item.update(kw)
    return item

class V8Gates(unittest.TestCase):
    def test_zero_does_not_pass(self):
        self.assertFalse(review_gate([])["process_review_ready"])

    def test_independent_60_and_matured_30_only_review_not_profit_claim(self):
        sample=[episode("2026-11-%02d"%(i%28+1),"T%04d"%i) for i in range(60)]
        # Twenty-day maturity counts distinct episodes: this synthetic
        # fixture checks accounting only, never claims those dates are real.
        r=review_gate(sample)
        self.assertTrue(r["process_review_ready"])
        self.assertFalse(r["proof_of_statistical_edge"])
        self.assertFalse(r["strategy_promotable"])

    def test_uncertified_and_unpublished_never_qualify(self):
        a=episode("2026-11-09","A")
        b=dict(a,ticker="B",regular_only_certified=False)
        c=dict(a,ticker="C",registered_in_advance=False)
        d=dict(a,ticker="D",time_evidence_verified=False)
        r=review_gate([a,b,c,d])
        self.assertEqual(r["unique_valid_independent_signals"],1)
        self.assertEqual(r["exclude_reasons"]["UNCERTIFIED_SOURCE"],1)
        self.assertEqual(r["exclude_reasons"]["NOT_PUBLISHED_IN_ADVANCE"],1)
        self.assertEqual(r["exclude_reasons"]["UNVERIFIED_ASOF_CLOCK"],1)

    def test_duplicate_and_censored_do_not_create_extra_matured(self):
        a=episode("2026-11-09","A")
        b=dict(a)
        c=dict(a,ticker="C",censored=True)
        d=dict(a,ticker="D",complete_20d_evidence=False)
        r=review_gate([a,b,c,d],minimum_distinct=3,minimum_complete_20d=3)
        self.assertEqual(r["unique_valid_independent_signals"],3)
        self.assertEqual(r["genuinely_matured_20d"],1)
        self.assertFalse(r["process_review_ready"])

    def test_overlapping_signals_not_new_independent_evidence(self):
        r=review_gate([episode("2026-11-09","A",independent_episode=False)])
        self.assertEqual(r["exclude_reasons"]["OVERLAPPING_EPISODE"],1)

if __name__=="__main__":
    unittest.main(verbosity=2)
