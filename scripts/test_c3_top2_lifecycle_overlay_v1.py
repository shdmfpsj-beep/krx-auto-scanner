#!/usr/bin/env python3
"""Synthetic adversarial checks; all prices are fixtures, not trade evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from c3_top2_lifecycle_overlay_v1 import (
    EvidenceError, evaluate, fingerprint, load_history, run,
)

DAYS = ["2026-11-06", "2026-11-09", "2026-11-10",
        "2026-11-11", "2026-11-12", "2026-11-13"]


def calendar(day):
    return {"dates": DAYS[:DAYS.index(day) + 1]}


def row(ticker, rank, day):
    wonik = ticker == "030530"
    close, low, high, stop, rr = (
        (28300, 22100, 23500, 20600, 2.160401355) if wonik
        else (60500, 60700, 63500, 57700, 0.229744351)
    )
    # Not a valid BUY decision; a frozen research fixture.
    return {
        "rank": rank, "model": "B", "ticker": ticker,
        "name": "원익홀딩스" if wonik else "삼성E&A",
        "signal_id": f"research-{ticker}-{day}",
        "source_price_asof": day, "reference_close": close, "close": close,
        "buy_approved": False, "live_action": "CASH",
        "market_regime": "DOWN", "order_validity_sessions": 1,
        "entry_plans": {
            "A_SUPPORT_LIMIT": {
                "plan": {
                    "ticker": ticker, "signal_key": f"{ticker}:pivot",
                    "low": low, "high": high, "stop": stop,
                    "net_r1_rr": rr,
                }, "reason": None
            }
        }
    }


def report(day, tickers=("028050", "030530")):
    return {
        "source_price_asof": day, "preview_price_asof": day,
        "research_top2_registered_for_source_session": True,
        "research_preview_only": False, "errors": [],
        "research_top2": [row(t, i + 1, day) for i, t in enumerate(tickers)],
        "source_regular_only_certified": False,
        "orders_enabled": False, "current_action": "CASH",
        "new_registered_signals": 0,  # Re-read must not erase original selections.
    }


class LifecycleTests(unittest.TestCase):
    def test_actual_nov6_like_report_remains_cash_and_diagnostic_only(self):
        source = report(DAYS[0])
        clone = copy.deepcopy(source)
        x = evaluate(source, calendar(DAYS[0]), [])
        self.assertEqual(source, clone)
        self.assertEqual(x["status"], "RESEARCH_STATUS_ONLY")
        self.assertEqual([p["ticker"] for p in x["top2"]], ["028050", "030530"])
        self.assertEqual(x["top2"][0]["watch_status"], "FIRST_OBSERVED_TOP2")
        self.assertIn("R1_RR_BELOW_1_OR_UNKNOWN_DIAGNOSTIC", x["top2"][0]["diagnostics"])
        self.assertIn("LIMIT_OVER_10PCT_BELOW_CLOSE_DIAGNOSTIC", x["top2"][1]["diagnostics"])
        self.assertIn("STOP_OVER_12PCT_DIAGNOSTIC", x["top2"][1]["diagnostics"])
        self.assertAlmostEqual(x["top2"][1]["band"]["gap_close_vs_upper_pct"], 20.43)
        self.assertEqual(x["top2"][1]["original_plan_validity"], "NEXT_ONE_TRADING_SESSION_ONLY")
        self.assertFalse(x["buy_approved"])
        self.assertFalse(x["orders_enabled"])

    def test_three_and_five_actual_sessions_never_change_original_one_day_plan(self):
        history = []
        for index, day in enumerate(DAYS):
            result = evaluate(report(day), calendar(day), history)
            history = result["history"]
            age = result["top2"][1]["consecutive_prior_sessions_lower_bound"]
            self.assertEqual(age, index)
            if index == 3:
                self.assertEqual(result["top2"][1]["watch_status"], "WATCH_REEVALUATE")
            if index == 5:
                self.assertEqual(result["top2"][1]["watch_status"], "OLD_WATCH_ARCHIVE_REVIEW")
                self.assertEqual(result["top2"][1]["original_plan_validity"], "NEXT_ONE_TRADING_SESSION_ONLY")
                self.assertEqual(result["top2"][1]["action"], "CASH")
        self.assertEqual(len(history), 6)

    def test_new_ranking_replaces_prior_watcher_without_banning_ticker(self):
        a = evaluate(report(DAYS[0]), calendar(DAYS[0]), [])
        b = evaluate(report(DAYS[1], ("028050", "005930")),
                     calendar(DAYS[1]), a["history"])
        self.assertEqual(b["out_of_top2"], ["030530"])
        self.assertEqual(b["top2"][1]["consecutive_prior_sessions_lower_bound"], 0)
        # A previous exclusion must not prevent genuinely fresh selection.
        c = evaluate(report(DAYS[2], ("030530", "028050")),
                     calendar(DAYS[2]), b["history"])
        self.assertEqual(c["top2"][0]["watch_status"], "FIRST_OBSERVED_TOP2")
        self.assertIn("005930", c["out_of_top2"])

    def test_same_day_replay_is_idempotent_but_changed_plan_rejected(self):
        a = evaluate(report(DAYS[0]), calendar(DAYS[0]), [])
        replay = evaluate(report(DAYS[0]), calendar(DAYS[0]), a["history"])
        self.assertEqual(replay["history"], a["history"])
        changed = report(DAYS[0])
        changed["research_top2"][1]["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]["high"] = 23600
        with self.assertRaisesRegex(EvidenceError, "SAME_DATE_REPLAY_CONFLICT"):
            evaluate(changed, calendar(DAYS[0]), a["history"])

    def test_missing_completed_session_is_not_counted_as_no_selection(self):
        a = evaluate(report(DAYS[0]), calendar(DAYS[0]), [])
        result = evaluate(report(DAYS[2]), calendar(DAYS[2]), a["history"])
        self.assertIsNone(result["top2"][0]["consecutive_prior_sessions_lower_bound"])
        self.assertEqual(result["top2"][0]["watch_status"], "HISTORY_GAP_REVIEW")

    def test_stale_source_never_becomes_new_top2(self):
        result = evaluate(report(DAYS[0]), calendar(DAYS[1]), [])
        self.assertEqual(result["status"], "DATA_PENDING")
        self.assertIsNone(result["snapshot"])
        self.assertEqual(result["history"], [])
        self.assertEqual(result["top2"], [])

    def test_missing_registration_does_not_create_snapshot(self):
        x = report(DAYS[0])
        x["research_top2_registered_for_source_session"] = False
        self.assertEqual(evaluate(x, calendar(DAYS[0]), [])["status"], "DATA_PENDING")

    def test_invalid_rank_or_upstream_buy_is_not_repaired_silently(self):
        x = report(DAYS[0])
        x["research_top2"][1]["rank"] = 1
        with self.assertRaises(EvidenceError):
            evaluate(x, calendar(DAYS[0]), [])
        x = report(DAYS[0])
        x["research_top2"][0]["buy_approved"] = True
        with self.assertRaises(EvidenceError):
            evaluate(x, calendar(DAYS[0]), [])
        x = report(DAYS[0])
        x["research_top2"][0]["order_validity_sessions"] = 5
        with self.assertRaises(EvidenceError):
            evaluate(x, calendar(DAYS[0]), [])

    def test_future_history_is_rejected(self):
        a = evaluate(report(DAYS[1]), calendar(DAYS[1]), [])
        with self.assertRaises(EvidenceError):
            evaluate(report(DAYS[0]), calendar(DAYS[0]), a["history"])

    def test_hash_tampered_history_is_rejected(self):
        a = evaluate(report(DAYS[0]), calendar(DAYS[0]), [])
        corrupted = copy.deepcopy(a["history"])
        corrupted[0]["pairs"][1]["ticker"] = "005930"
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "history.jsonl"
            file.write_text(json.dumps(corrupted[0], ensure_ascii=False) + "\n")
            with self.assertRaises(EvidenceError):
                load_history(file)

    def test_filesystem_run_only_writes_derived_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / "latest.json"
            q = root / "calendar.json"
            p.write_text(json.dumps(report(DAYS[0]), ensure_ascii=False))
            q.write_text(json.dumps(calendar(DAYS[0])))
            before = (p.read_bytes(), q.read_bytes())
            result = run(p, q, None, root / "derived")
            self.assertEqual(before, (p.read_bytes(), q.read_bytes()))
            self.assertEqual(result["status"], "RESEARCH_STATUS_ONLY")
            self.assertTrue((root / "derived/c3_top2_lifecycle_status.json").is_file())
            self.assertTrue((root / "derived/c3_top2_observed_history.jsonl").is_file())
            self.assertTrue((root / "derived/c3_top2_lifecycle_mobile.md").is_file())

    def test_history_source_date_digest_is_stable(self):
        a = evaluate(report(DAYS[0]), calendar(DAYS[0]), [])
        s = a["snapshot"]
        self.assertEqual(s["fingerprint"], fingerprint(
            {"source_date": s["source_date"], "pairs": s["pairs"]}))


if __name__ == "__main__":
    unittest.main()
