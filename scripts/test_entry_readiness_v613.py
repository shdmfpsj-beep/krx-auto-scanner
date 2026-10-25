"""v6.13 independent first structural 2R research and no BUY."""
from __future__ import annotations
import json,csv,tempfile,unittest
from pathlib import Path
from entry_readiness_v613 import (
    SCHEMA,first_gate,second_gate,finite,save,validate_inputs,FIELDS,METHOD_FIELDS)
from entry_strategy_v58 import COST_PCT,MIN_RR

def signal():
    return dict(setup="RESEARCH_TRIGGER_CONFIRMED_ASOF",
        stop_reference=94,first_entry_reference=100,
        nearest_resistance_reference=116,first_net_rr=2.17,
        second_net_rr=None,first_stop_risk_pct=6,
        first_entry_below_close_atr=0.32,daily_pivot_date="2026-10-19",
        second_entry_reference=None,second_stop_risk_pct=None,
        second_entry_policy="NO_CONFIRMED_SEPARATE_SECOND_SUPPORT")

class V613ReadinessTests(unittest.TestCase):
    def test_existing_cost_model_is_not_overridden(self):
        self.assertEqual(COST_PCT,0.5)
        self.assertEqual(MIN_RR,2.0)
        self.assertEqual(SCHEMA,"C3_K100_FIRST_ENTRY_INDEPENDENT_READINESS_V613")

    def test_first_cost_2r_can_be_valid_without_second_price(self):
        r=signal()
        self.assertEqual(first_gate(r)[0],True)
        self.assertFalse(second_gate(r))
        self.assertIn("SECOND_OPTIONAL",first_gate(r)[1])

    def test_optional_second_only_when_real_pivot_policy_and_2r(self):
        r=signal()
        r.update(second_entry_reference=98,second_stop_risk_pct=4.08,
            second_net_rr=2.8,
            second_entry_policy="ALTERNATIVE_LIMIT_IF_FIRST_NOT_FILLED_NO_AVERAGING_DOWN")
        self.assertTrue(second_gate(r))
        self.assertTrue(first_gate(r)[0])
        self.assertFalse(second_gate({**r,"second_entry_policy":"AVERAGE_DOWN"}))
        self.assertFalse(second_gate({**r,"second_net_rr":1.8}))

    def test_above_or_equal_stop_cannot_form_valid_entry(self):
        self.assertFalse(first_gate({**signal(),"stop_reference":101})[0])
        self.assertFalse(first_gate({**signal(),"stop_reference":100})[0])
        self.assertFalse(first_gate({**signal(),"stop_reference":0})[0])

    def test_nearest_ceiling_must_be_over_first(self):
        for c in (None,100,92,float("nan")):
            self.assertFalse(first_gate({**signal(),"nearest_resistance_reference":c})[0])

    def test_first_RR_never_rounded_up_below_two(self):
        self.assertFalse(first_gate({**signal(),"first_net_rr":1.999})[0])
        self.assertTrue(first_gate({**signal(),"first_net_rr":2.0})[0])

    def test_structural_risk_window_and_far_pullback_capped(self):
        self.assertFalse(first_gate({**signal(),"first_stop_risk_pct":1.9})[0])
        self.assertFalse(first_gate({**signal(),"first_stop_risk_pct":12.1})[0])
        self.assertFalse(first_gate({**signal(),"first_entry_below_close_atr":1.01})[0])

    def test_price_without_confirmed_daily_trigger_not_eligible(self):
        self.assertFalse(first_gate({**signal(),"setup":"NO_CONFIRMED_SETUP"})[0])
        self.assertFalse(first_gate({**signal(),"daily_pivot_date":None})[0])

    def test_second_price_does_not_allow_averaging_or_above_first(self):
        r=signal()
        r.update(second_entry_reference=101,second_stop_risk_pct=4,
            second_net_rr=4,second_entry_policy=
            "ALTERNATIVE_LIMIT_IF_FIRST_NOT_FILLED_NO_AVERAGING_DOWN")
        self.assertFalse(second_gate(r))
        r["second_entry_reference"]=93
        self.assertFalse(second_gate(r))

    def test_nonfinite_prices_and_strings_cannot_enter_price_gate(self):
        self.assertIsNone(finite(True))
        self.assertIsNone(finite(""))
        self.assertIsNone(finite(float("inf")))
        self.assertIsNone(finite(float("nan")))
        self.assertFalse(first_gate({**signal(),"first_entry_reference":"garbled"})[0])

    def test_forged_prior_status_cannot_produce_readiness(self):
        with tempfile.TemporaryDirectory() as d:
            t=Path(d)/"top";i=Path(d)/"issuer";v=Path(d)/"v18"
            for path in (t,i,v):path.mkdir()
            (t/"top20_quality_v612_status.json").write_text(json.dumps(
                dict(schema=SCHEMA,asof="2026-10-23",trade_approved=True)))
            (i/"issuer_entry_v610_status.json").write_text("{}")
            (v/"diagnostics").mkdir()
            (v/"diagnostics/collection_status.json").write_text("{}")
            with self.assertRaisesRegex(ValueError,"V613_EXACT_ASOF_PREDECESSOR"):
                validate_inputs(t,i,v)

    def test_output_is_pure_readonly_and_safely_holds_empty_top5(self):
        with tempfile.TemporaryDirectory() as d:
            r=dict(schema=SCHEMA,asof="2026-10-23",method_evaluations=0,
                confirmed_technical_method_count=0,
                confirmed_first_cost_2r_reference_method_count=0,
                first_valid_without_optional_second_count=0,
                trade_approved=False,orders_enabled=False,decision="CASH")
            save(Path(d),r,[],[])
            self.assertTrue((Path(d)/"entry_readiness_v613_all.csv").is_file())
            self.assertEqual(len(FIELDS),len(set(FIELDS)))
            self.assertEqual(len(METHOD_FIELDS),len(set(METHOD_FIELDS)))
            m=json.loads((Path(d)/"entry_readiness_v613_status.json").read_text())
            self.assertEqual(len(m["artifact_file_sha256"]),2)
            self.assertIn("CASH",(Path(d)/"entry_readiness_v613_mobile.md").read_text())

if __name__=="__main__":unittest.main()
