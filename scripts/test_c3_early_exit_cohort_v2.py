"""C3 paper cohort regression: early exits must count in later horizons."""
import unittest
from test_c3_paper_forward_v1 import ForwardTest,mock,PLAN

class EarlyExitCohort(ForwardTest):
    def test_early_t2_exit_kept_in_five_session_cohort(self):
        bars=[mock("271560","2026-11-02",114000,115000,112000,113400)]
        self.tick("2026-11-02",bars)
        bars.append(mock("271560","2026-11-03",135000,145000,130000,141000))
        self.tick("2026-11-03",bars)
        for day in ("2026-11-04","2026-11-05","2026-11-06","2026-11-09"):
            bars.append(mock("271560",day,140000,142000,135000,137000))
            report=self.tick(day,bars)
        row=report["positions"][0]
        self.assertEqual(row["status"],"CLOSED_T2")
        self.assertEqual(row["held_sessions"],5)
        self.assertIsNotNone(row["net_return_after_5_sessions_pct"])
        self.assertEqual(row["remaining_fraction"],0)
        self.assertEqual(report["events_total"],self.tick("2026-11-09",bars)["events_total"])

    def test_early_stop_exit_kept_in_five_session_cohort(self):
        bars=[mock("271560","2026-11-02",114000,114000,108000,109000)]
        self.tick("2026-11-02",bars)
        bars.append(mock("271560","2026-11-03",103000,106000,100000,104000))
        self.tick("2026-11-03",bars)
        for day in ("2026-11-04","2026-11-05","2026-11-06","2026-11-09"):
            bars.append(mock("271560",day,135000,136000,132000,134000))
            report=self.tick(day,bars)
        row=report["positions"][0]
        self.assertEqual(row["status"],"CLOSED_STOP")
        self.assertEqual(row["held_sessions"],5)
        self.assertLess(row["net_return_after_5_sessions_pct"],0)
        self.assertEqual(row["stop_exit_date"],"2026-11-03")

    def test_no_horizon_backfill_after_terminal_session_gap(self):
        bars=[mock("271560","2026-11-02",114000,115000,112000,113400)]
        self.tick("2026-11-02",bars)
        bars.append(mock("271560","2026-11-03",135000,145000,130000,141000))
        self.tick("2026-11-03",bars)
        bars.append(mock("271560","2026-11-04",140000,142000,138000,140000))
        bars.append(mock("271560","2026-11-05",139000,141000,137000,139000))
        report=self.tick("2026-11-05",bars)
        self.assertTrue(report["positions"][0]["forward_horizon_data_gap"])
        self.assertIsNone(report["positions"][0]["net_return_after_5_sessions_pct"])

if __name__=="__main__":unittest.main()
