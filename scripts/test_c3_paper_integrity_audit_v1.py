"""Regression tests for the read-only paper ledger audit. Synthetic fixtures only."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from c3_paper_integrity_audit_v1 import audit

PLAN = dict(plan_id="TEST-271560", ticker="271560", name="SYNTHETIC",
    selection_date="2026-10-30", registered_day="2026-10-31",
    source_run_id="test", source_close="114200", watch_low="110900",
    watch_high="113700", structure_stop="109600", target1="131500",
    target2="141700", expires_after_sessions="5",
    source_scope="PYKRX_RESEARCH_REGULAR_ONLY_UNCERTIFIED",
    stop_rule="NEXT_OPEN_AFTER_CLOSE_BELOW_STOP")

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.plans = root / "plans.csv"
        self.ledger = root / "ledger.json"
        self.position = dict(plan=copy.deepcopy(PLAN), status="OPEN",
            entry_date="2026-11-02", last_observed_date="2026-11-03",
            last_mark_date="2026-11-03", held_sessions=1,
            trade_approved=False, orders_enabled=False,
            source_regular_only_certified=False,
            net_return_after_5_sessions_pct=None,
            net_return_after_10_sessions_pct=None,
            net_return_after_20_sessions_pct=None)
        self.data = dict(positions={PLAN["plan_id"]: self.position},
            events=[dict(event_key="event-1", plan_id=PLAN["plan_id"],
                source_session="2026-11-02", actual_broker_fill=False)],
            real_broker_orders=False, authoritative_regular_scope=False)

    def check(self):
        with self.plans.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(PLAN))
            writer.writeheader()
            writer.writerow(PLAN)
        self.ledger.write_text(json.dumps(self.data), encoding="utf-8")
        return audit(self.plans, self.ledger)

    def test_valid_fixture_passes(self):
        self.assertTrue(self.check()["ok"])

    def test_modified_registered_price_rejected(self):
        self.position["plan"]["structure_stop"] = "100000"
        self.assertIn("TEST-271560:PLAN_MISMATCH:structure_stop",
                      self.check()["errors"])

    def test_registration_day_entry_rejected(self):
        self.position["entry_date"] = "2026-10-30"
        self.assertIn("TEST-271560:RETROACTIVE_ENTRY", self.check()["errors"])

    def test_early_horizon_result_rejected(self):
        self.position["net_return_after_5_sessions_pct"] = 10.0
        self.assertIn("TEST-271560:PREMATURE_5_SESSION_RESULT",
                      self.check()["errors"])

    def test_duplicate_event_rejected(self):
        self.data["events"].append(copy.deepcopy(self.data["events"][0]))
        self.assertIn("DUPLICATE_EVENT_KEY", self.check()["errors"])

    def test_real_broker_fill_claim_rejected(self):
        self.data["events"][0]["actual_broker_fill"] = True
        self.assertIn("TEST-271560:BROKER_FILL_CLAIM", self.check()["errors"])

    def test_order_enablement_rejected(self):
        self.position["orders_enabled"] = True
        self.assertIn("TEST-271560:TRADING_SAFETY_FLAG", self.check()["errors"])

    def test_future_mark_rejected(self):
        self.position["last_mark_date"] = "2026-11-04"
        self.assertIn("TEST-271560:FUTURE_MARK", self.check()["errors"])

if __name__ == "__main__":
    unittest.main()
