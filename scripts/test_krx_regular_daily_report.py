import tempfile,unittest,json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from krx_regular_daily_report import report,markdown,nominal_regular_day
from krx_regular_after_layers import capture

Z=ZoneInfo("Asia/Seoul")
def obs(close=100):
    rows={f"{i:06d}":{"Open":98,"High":104,"Low":96,"Close":close,
                     "Volume":1000,"TurnoverKRW":100000} for i in range(1,120)}
    return capture("regular",datetime(2026,10,23,15,35,tzinfo=Z),{"KOSPI":rows})
class Tests(unittest.TestCase):
    def test_regular_snapshot_does_not_fake_certification_or_buy(self):
        r=report(obs(),"2026-10-23")
        self.assertTrue(r["regular_snapshot_available"])
        self.assertTrue(r["after_market_excluded"])
        self.assertFalse(r["provider_session_scope_verified"])
        self.assertEqual(r["sector_selection_outcome"],"PENDING_DATA_VALIDATION")
        self.assertEqual(r["approved_buy_count"],0)
        self.assertEqual(r["decision"],"CASH")
        self.assertIn("PROVIDER_REGULAR_SESSION_SCOPE_NOT_ATTESTED",r["blockers"])
        self.assertIn("애프터마켓 자료",markdown(r))
    def test_price_certification_is_research_ready_without_institutional_flows(self):
        fake=obs()
        # Frozen fixture represents future fully authenticated regular price.
        # Missing institutional data must not block PRICE readiness but other
        # strategy evidence remains absent; never approve a BUY.
        fake["provider_session_scope_verified"]=True
        fake["regular_strategy_eligible"]=True
        r=report(fake,"2026-10-23")
        self.assertEqual(r["market_source_status"],"REGULAR_PRICE_SOURCE_VERIFIED_RESEARCH_ONLY")
        self.assertEqual(r["investor_flow_policy"],"OPTIONAL_CONFIRMATION_NOT_BUY_GATE")
        self.assertEqual(r["investor_flow_data_status"],"NOT_PROVIDED")
        self.assertNotIn("REGULAR_ONLY_FOREIGN_INSTITUTION_FLOW_NOT_VERIFIED",r["blockers"])
        self.assertIn("STRUCTURAL_ENTRY_AND_FINAL_SCORE_NOT_VERIFIED",r["mandatory_remaining_evidence"])
        self.assertIn("선택적 확인",markdown(r))
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["approved_buy_count"],0)

    def test_dated_valid_krx_minute_probes_are_price_subset_only(self):
        audit={"schema":"kis_krx_minute_audit_v1","date":"20261023",
               "regular_reconstructions":[
                 {"ticker":"005930","asof":"20261023","market_code":"J",
                  "regular_ohlcv_reconstruction_verified":True,
                  "regular_ohlcv":{"Open":100,"High":102,"Low":99,"Close":101,"Volume":10000},
                  "minutes_seen":391,"trade_approved":False}],
               "audited_tickers":["005930"],"data_status":"PARTIAL_REGULAR_MINUTE_PRICE_OBSERVED"}
        r=report(obs(),"2026-10-23",audit)
        self.assertEqual(r["kis_krx_minute_price_probe"]["status"],
                         "REGULAR_MINUTE_PRICE_SUBSET_OBSERVED")
        self.assertEqual(r["kis_krx_minute_price_probe"]["verified_subset_count"],1)
        self.assertEqual(r["kis_krx_minute_price_probe"]["ticker_samples"][0]["ticker"],"005930")
        self.assertFalse(r["kis_krx_minute_price_probe"]["investor_flow_validated"])
        self.assertEqual(r["market_source_status"],"PENDING_DATA_VALIDATION")
        self.assertEqual(r["approved_buy_count"],0)
        self.assertIn("KIS KRX 분봉 교차검증",markdown(r))

    def test_stale_or_wrong_market_official_quote_cannot_upgrade_readiness(self):
        audit={"date":"20261022","regular_reconstructions":[
                 {"ticker":"005930","asof":"20261022","market_code":"UN",
                  "regular_ohlcv_reconstruction_verified":True,
                  "regular_ohlcv":{"Open":100,"High":102,"Low":99,"Close":101,"Volume":1000},
                  "trade_approved":False}],"audited_tickers":["005930"]}
        r=report(obs(),"2026-10-23",audit)
        self.assertEqual(r["kis_krx_minute_price_probe"]["status"],"SOURCE_ASOF_MISMATCH")
        self.assertEqual(r["kis_krx_minute_price_probe"]["verified_subset_count"],0)
        self.assertFalse(r["trade_approved"])

    def test_unverified_regular_price_still_blocks_with_optional_flow(self):
        r=report(obs(),"2026-10-23")
        self.assertEqual(r["market_source_status"],"PENDING_DATA_VALIDATION")
        self.assertIn("PROVIDER_REGULAR_SESSION_SCOPE_NOT_ATTESTED",r["blockers"])
        self.assertNotIn("REGULAR_ONLY_FOREIGN_INSTITUTION_FLOW_NOT_VERIFIED",r["blockers"])
        self.assertFalse(r["trade_approved"])

    def test_previous_day_snapshot_cannot_be_used_as_today_close(self):
        r=report(obs(),"2026-10-26")
        self.assertIn("REGULAR_SOURCE_ASOF_MISMATCH",r["blockers"])
    def test_aftermarket_snapshot_cannot_be_fed_to_regular_report(self):
        d=obs();d["phase"]="after"
        r=report(d,"2026-10-23")
        self.assertIn("REGULAR_SESSION_REQUIRED",r["blockers"])
        self.assertEqual(r["approved_buy_count"],0)
    def test_missing_file_is_pending_not_zero_qualifying_stocks(self):
        r=report({},"2026-10-23")
        self.assertFalse(r["regular_snapshot_available"])
        self.assertIsNone(r["verified_sector_count"])
        self.assertIn("SNAPSHOT_MISSING",r["blockers"])
    def test_regular_day_is_current_after_close_and_last_weekday_preopen(self):
        dt=lambda x:datetime.fromisoformat(x).replace(tzinfo=Z)
        self.assertEqual(nominal_regular_day(dt("2026-10-23T15:32:00")),"2026-10-22")
        self.assertEqual(nominal_regular_day(dt("2026-10-23T15:33:00")),"2026-10-23")
        self.assertEqual(nominal_regular_day(dt("2026-10-26T08:35:00")),"2026-10-23")
if __name__=="__main__":unittest.main()
