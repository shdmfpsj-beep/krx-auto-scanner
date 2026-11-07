"""C3 v19 midnight and 22:30 readiness/provenance regression tests (offline)."""
import copy
import unittest

from c3_readiness_gate_v19 import assess,source_evidence,parsed

DAY="2026-11-06"
READY=parsed("2026-11-06T23:30:00+09:00")
PREMATURE=parsed("2026-11-06T22:30:00+09:00")
REPORT=dict(
    source_price_asof=DAY,
    generated_at="2026-11-06T23:21:58+09:00",
    analysis_completed_at="2026-11-06T23:21:38+09:00",
    source_received_at="2026-11-06T23:21:34+09:00",
    source_run_id="42233092127",data_quality_state="RESEARCH_VALIDATED",
    source_provider="FINANCEDATA_KRX_CACHE",
    source_regular_only_certified=False,orders_enabled=False,
    errors=[],current_action="CASH",
    source_quality_gate=dict(status="QUALITY_GATE_PASSED",errors=[],
                            full_current_listing_census_verified=False,
                            markets={"KOSPI":{"rows":938},"KOSDAQ":{"rows":1831}}),
    current_scope=dict(price_rows=2769,analysis_eligible=1986),
    research_top2_registered_for_source_session=True,
    new_registered_signals=4,
    performance=dict(registered_signals=4),
    research_top2=[
        dict(ticker="028050",rank=1,name="삼성E&A",reference_close=60500),
        dict(ticker="030530",rank=2,name="원익홀딩스",reference_close=28300)],
)
SUMMARY=dict(source_price_asof=DAY,generated_at=REPORT["generated_at"],
             source_run_id=REPORT["source_run_id"])
AUDIT=dict(actual_data=dict(asof=DAY,official_status="OFFICIAL_MARKETS_NOT_COMPLETE",
    official_response_diagnostics=[
        dict(market="KOSPI",asof=DAY,http_status=200,outblock_rows=0),
        dict(market="KOSDAQ",asof=DAY,http_status=200,outblock_rows=0)],
    earlier_official_control=dict(asof="2026-11-05",rows=2769),
    original_session_contract=dict(provider="FINANCEDATA_KRX_CACHE",
                                   regular_input_allowed=False),
    full_current_listing_census_independently_verified=False))

class ReadinessGateTests(unittest.TestCase):
    def setUp(self):
        self.latest=copy.deepcopy(REPORT)
        self.summary=copy.deepcopy(SUMMARY)

    def gate(self,clock=READY,runs=(),audit=AUDIT):
        return assess(self.latest,self.summary,clock,runs,audit)

    def test_2230_not_zero_when_research_result_arrived_at_2321(self):
        x=self.gate(PREMATURE)
        self.assertFalse(x["registered_top2_final_at_check_time"])
        self.assertEqual(x["status"],"RESEARCH_NOT_YET_AVAILABLE_AT_CHECK_TIME")
        self.assertIn("미완료",x["recommendation_for_chatgpt"])
        self.assertEqual(x["known_top2"],[])

    def test_2230_workflow_active_is_explicitly_running_not_no_top2(self):
        x=self.gate(PREMATURE,runs=[dict(id=123,status="in_progress",name="caller")])
        self.assertEqual(x["status"],"RESEARCH_IN_PROGRESS")
        self.assertEqual(len(x["active_research_runs"]),1)

    def test_2330_new_report_is_final_research_only(self):
        x=self.gate()
        self.assertEqual(x["status"],"FINAL_RESEARCH_TOP2_UNCERTIFIED_SESSION")
        self.assertEqual([r["ticker"] for r in x["known_top2"]],["028050","030530"])
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["source_attestation"]["regular_only_independently_certified"])

    def test_zero_new_signals_is_not_zero_original_registered_signals(self):
        self.latest["new_registered_signals"]=0
        x=self.gate()
        self.assertEqual(x["original_report_registered_signal_count"],4)
        self.assertEqual(x["status"],"FINAL_RESEARCH_TOP2_UNCERTIFIED_SESSION")

    def test_stale_day_never_infers_missing_market_top2(self):
        self.latest["source_price_asof"]="2026-11-05"
        x=self.gate()
        self.assertEqual(x["status"],"SOURCE_OR_REPORT_NOT_YET_READY")
        self.assertEqual(x["known_top2"],[])

    def test_partial_publication_different_source_run_not_final(self):
        self.summary["source_run_id"]="OLD"
        self.assertEqual(self.gate()["status"],"SOURCE_AND_SUMMARY_REVISION_MISMATCH")

    def test_registered_but_missing_cards_is_not_zero_final(self):
        self.latest["research_top2"]=[]
        x=self.gate()
        self.assertEqual(x["status"],"NO_VERIFIABLE_FINAL_TOP2")
        self.assertFalse(x["registered_top2_final_at_check_time"])

    def test_research_immutable_not_registered_yet(self):
        self.latest["research_top2_registered_for_source_session"]=False
        self.assertEqual(self.gate()["status"],"RESEARCH_NOT_REGISTERED")

    def test_source_quarantine_blocks_picks(self):
        self.latest["source_quality_gate"]["status"]="QUALITY_GATE_FAILED"
        self.assertEqual(self.gate()["status"],"SOURCE_QUARANTINED")

    def test_future_source_receipt_does_not_become_final(self):
        self.latest["source_received_at"]="2026-11-07T09:00:00+09:00"
        self.assertEqual(self.gate()["status"],"RESEARCH_NOT_YET_AVAILABLE_AT_CHECK_TIME")

    def test_original_contract_does_not_authorize_session_from_quality_pass(self):
        x=self.gate()
        self.assertTrue(x["source_attestation"]["research_quality_passed"])
        self.assertFalse(x["source_attestation"]["regular_only_independently_certified"])
        self.assertFalse(x["orders_enabled"])
        self.assertIn("OFFICIAL_SAME_DAY_API_RETURNED_EMPTY",x["source_attestation"]["caveats"])
        self.assertEqual(x["source_attestation"]["official_prior_day_control_rows"],2769)

    def test_later_official_2769_rows_is_still_regular_session_uncertified(self):
        recent=dict(requested_asof=DAY,official_target_status="OFFICIAL_DAILY_ROWS_PRESENT_SESSION_UNCERTIFIED",
                    official_target_rows=2769)
        x=assess(self.latest,self.summary,READY,(),AUDIT,recheck=recent)
        self.assertEqual(x["source_attestation"]["latest_official_dated_probe"]["rows"],2769)
        self.assertFalse(x["source_attestation"]["latest_official_dated_probe"]["regular_only_certified"])
        self.assertFalse(x["trade_approved"])

    def test_mismatched_new_official_day_cannot_be_applied_to_old_session(self):
        recent=dict(requested_asof="2026-11-05",official_target_rows=2769)
        x=assess(self.latest,self.summary,READY,(),AUDIT,recheck=recent)
        self.assertIsNone(x["source_attestation"]["latest_official_dated_probe"])

    def test_fake_report_self_declared_certification_is_insufficient(self):
        self.latest["source_regular_only_certified"]=True
        x=self.gate()
        self.assertFalse(x["source_attestation"]["regular_only_independently_certified"])
        self.assertFalse(x["trade_approved"])
        self.assertIn("VOLUME_AND_TURNOVER_ARE_NOT_0900_1530_ONLY",
                      x["source_attestation"]["caveats"])

    def test_no_trading_day_does_not_reuse_fridays_picks_as_saturday_new(self):
        saturday=parsed("2026-11-07T22:30:00+09:00")
        x=self.gate(saturday)
        self.assertEqual(x["status"],"NO_NOMINAL_WEEKDAY_SESSION")
        self.assertFalse(x["registered_top2_final_at_check_time"])

    def test_00_30_previous_session_is_expected(self):
        morning=parsed("2026-11-09T08:30:00+09:00")
        x=self.gate(morning)
        self.assertEqual(x["status"],"FINAL_RESEARCH_TOP2_UNCERTIFIED_SESSION")

    def test_late_update_next_day_never_changes_2230_historical_state(self):
        self.latest["generated_at"]="2026-11-07T07:07:18+09:00"
        self.latest["analysis_completed_at"]="2026-11-06T23:21:38+09:00"
        self.summary["generated_at"]=self.latest["generated_at"]
        self.assertEqual(self.gate(PREMATURE)["status"],"RESEARCH_NOT_YET_AVAILABLE_AT_CHECK_TIME")

    def test_datetime_requires_timezone(self):
        with self.assertRaisesRegex(ValueError,"TIMEZONE_REQUIRED"):
            parsed("2026-11-06T22:30:00")

if __name__=="__main__":unittest.main(verbosity=2)
