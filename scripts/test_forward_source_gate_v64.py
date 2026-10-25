"""v6.4 frozen alternative stop/risk unchanged; source disagreement gates ROI."""
from __future__ import annotations
import copy,unittest
from collections import Counter
from entry_strategy_v58 import METHODS
from forward_ledger_v63 import digest,canonical,SCHEMA as FROZEN
from forward_source_gate_v64 import gate,mobile,SCHEMA

DATE="2026-10-23"
def fixture():
    plans=[]
    for ticker,close,entry in [("003780",100,95),("089890",200,180)]:
        for variant in ("FIRST","SECOND"):
            plans.append(dict(asof=DATE,ticker=ticker,name="FIXTURE",
                method=METHODS[2],variant=variant,signal_close_reference=close,
                research_entry_reference=entry if variant=="FIRST" else entry-2,
                daily_structure_stop_reference=entry-10,
                nearest_target_repriced_reference=entry+15,
                trade_approved=False,orders_enabled=False))
    frozen=dict(schema=FROZEN,version=1,asof=DATE,
        freeze_utc="2026-10-24T23:30:00+00:00",
        freeze_status="FROZEN_ASOF_UNCERTIFIED",
        asof_signal_count=2,frozen_alternative_count=4,
        frozen_payload_sha256=digest(canonical(plans)),
        orders_enabled=False,trade_approved=False)
    src_rows=[]
    for ticker,cl1,cl2,klass in [
        ("003780",100,100,"CLOSE_AGREED_SESSION_UNCERTIFIED"),
        ("089890",200,195,"CLOSE_CONFLICT_SESSION_UNKNOWN")]:
        src_rows.append(dict(asof=DATE,ticker=ticker,
            classification=klass,recovery_close=str(cl1),v18_close=str(cl2),
            frozen_technical_signal_methods=METHODS[2],
            is_frozen_signal="True",
            trade_approved="False",orders_enabled="False",
            independent_regular_close_certified="False"))
    sr=dict(schema="C3_K100_SOURCE_CONSENSUS_V64",asof=DATE,
        manifest_sha256=frozen["frozen_payload_sha256"],
        candidate_count=2,
        classifications=dict(Counter(x["classification"] for x in src_rows)),
        provenance_run_ids=dict(sector_v18_run_id="39948306433"),
        trade_approved=False,orders_enabled=False,
        kst_regular_session_0900_1530_independently_certified=False,
        all_frozen_prices_tainted_until_certified=True)
    fwd=dict(schema=FROZEN,asof=DATE,
        frozen_payload_sha256=frozen["frozen_payload_sha256"],
        frozen_research_alternatives=4,
        observed_full_market_snapshot_days=7,
        observed_future_distinct_market_dates=["2026-10-26","2026-10-27"],
        trade_approved=False,orders_enabled=False,
        all_prices_regular_only_verified=False)
    fr=[]
    for p in plans:
        fr.append(dict(asof=DATE,ticker=p["ticker"],method=p["method"],
            variant=p["variant"],signal_close_reference=str(p["signal_close_reference"]),
            research_entry_reference=str(p["research_entry_reference"]),
            daily_structure_stop_reference=str(p["daily_structure_stop_reference"]),
            nearest_target_repriced_reference=str(p["nearest_target_repriced_reference"]),
            net_return_pct="7.5",trade_approved="False",orders_enabled="False"))
    return [frozen,plans,sr,src_rows,fwd,fr]

class V64GateTests(unittest.TestCase):
    def test_2_conflicting_and_2_agreed_alternatives_always_cash(self):
        m,rows=gate(*fixture())
        self.assertEqual(m["schema"],SCHEMA)
        self.assertEqual(m["frozen_alternative_count"],4)
        self.assertEqual(m["asof_source_conflict_or_invalid_variants"],2)
        self.assertEqual(m["asof_source_concordant_but_uncertified_variants"],2)
        self.assertEqual(m["any_pre_gate_simulated_roi_suppressed"],4)
        self.assertEqual(m["decision"],"CASH")
        self.assertTrue(all(x["net_return_pct"] is None for x in rows))
        self.assertTrue(all(x["trade_approved"] is False for x in rows))
        self.assertFalse(m["outcome_performance_published"])
        self.assertIn("정규장",mobile(m,rows))

    def test_source_hash_must_match_exactly_frozen_payload(self):
        inp=fixture();inp[2]["manifest_sha256"]="not-existing"
        with self.assertRaisesRegex(ValueError,"SOURCE_CONSENSUS_DATE_OR_COMPLETE"):
            gate(*inp)

    def test_forward_progress_cannot_use_different_frozen_signal(self):
        inp=fixture();inp[4]["frozen_payload_sha256"]="not-existing"
        with self.assertRaisesRegex(ValueError,"V63_FORWARD_AND_SOURCE_DATED"):
            gate(*inp)

    def test_forward_price_edit_after_frozen_is_rejected(self):
        inp=fixture();inp[5][0]["research_entry_reference"]="1000"
        with self.assertRaisesRegex(ValueError,"FROZEN_PRICE_CHANGED"):
            gate(*inp)

    def test_missing_or_duplicate_one_limit_is_not_silently_dropped(self):
        inp=fixture();inp[5]=inp[5][:-1]
        with self.assertRaisesRegex(ValueError,"V63_FORWARD_AND_SOURCE_DATED"):
            gate(*inp)
        inp=fixture();inp[5][-1]=copy.deepcopy(inp[5][0])
        with self.assertRaisesRegex(ValueError,"FORWARD_SIGNALS_NOT_EXACT_FROZEN"):
            gate(*inp)

    def test_certification_cannot_be_invented_on_matched_close(self):
        inp=fixture();inp[2]["kst_regular_session_0900_1530_independently_certified"]=True
        with self.assertRaisesRegex(ValueError,"SOURCE_CONSENSUS_DATE_OR_COMPLETE"):
            gate(*inp)
        inp=fixture();inp[3][0]["independent_regular_close_certified"]="True"
        with self.assertRaisesRegex(ValueError,"SOURCE_AUDIT_DUPLICATED_UNSAFE"):
            gate(*inp)

    def test_unreconciled_frozen_method_is_fatal(self):
        inp=fixture();inp[3][0]["frozen_technical_signal_methods"]=METHODS[0]
        with self.assertRaisesRegex(ValueError,"FROZEN_TECHNICAL_METHOD_UNRECONCILED"):
            gate(*inp)

    def test_row_source_class_count_is_not_mutable_without_detection(self):
        inp=fixture();inp[3][1]["classification"]="CLOSE_AGREED_SESSION_UNCERTIFIED"
        with self.assertRaisesRegex(ValueError,"SOURCE_AUDIT_CLASSIFICATION_TOTAL_CHANGED"):
            gate(*inp)

if __name__=="__main__":unittest.main()
