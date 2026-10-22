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
    def test_price_certification_alone_cannot_mark_market_ready_without_flows(self):
        fake=obs()
        fake["provider_session_scope_verified"]=True
        fake["regular_strategy_eligible"]=True
        r=report(fake,"2026-10-23")
        self.assertEqual(r["market_source_status"],"PENDING_DATA_VALIDATION")
        self.assertIn("REGULAR_ONLY_FOREIGN_INSTITUTION_FLOW_NOT_VERIFIED",r["blockers"])
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["approved_buy_count"],0)

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
