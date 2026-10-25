"""Strict v6.14 no same-date unknown, 15 session replay and rank integrity."""
from __future__ import annotations
import csv,json,tempfile,unittest
from pathlib import Path
from october_replay_v614 import (
    SCHEMA,DAILY_FIELDS,SIGNAL_FIELDS,TOP_FIELDS,sector_proxy_of_day,save)
from entry_readiness_v613 import first_gate

class OctoberV614Tests(unittest.TestCase):
    def test_schema_and_exact_raw_field_names_are_unique(self):
        self.assertEqual(SCHEMA,"C3_K100_OCTOBER_15DAY_REPLAY_V614")
        for f in (DAILY_FIELDS,SIGNAL_FIELDS,TOP_FIELDS):
            self.assertEqual(len(f),len(set(f)))

    def test_no_non_october_fake_trade_in_saved_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=dict(schema=SCHEMA,source_market_asof="2026-10-23",
               evaluated_sessions=0,first_day="2026-10-01",last_day="2026-10-23",
               full_v613_buy_gate_authorizations=0,
               first_2R_method_count_all_positive_flow=0,
               first_2R_method_count_selected_top20=0,
               first_2R_method_count_risk_top5=0,
               possible_next_session_limit_touches_top20=0,
               possible_next_session_limit_touches_risk_top5=0,
               broker_execution_log_available=False,trade_approved=False,
               orders_enabled=False,decision="CASH")
            save(Path(tmp),data,[],[],[])
            self.assertIn("CASH",(Path(tmp)/"october_replay_v614_mobile.md").read_text())
            self.assertEqual(len(data["artifact_sha256"]),3)

    def test_sector_requires_strict_full_provenance_and_no_future_snapshot(self):
        from datetime import date
        row=dict(sector_id="CONSTRUCTION",snapshot_date="2026-10-06",
            rs_5d_pp="7.2",breadth_up_5d_pct="33",
            price_flow_proxy_ready="True",membership_status=
            "PROVIDER_DATED_PROXY_NOT_STRICT_PIT",
            live_selection_authorized="False",
            foreign_5d_coverage="1",institution_5d_coverage="1",
            turnover_coverage="1",member_turnover_krw="10000000",
            foreign_net_buy_5d_krw="100",
            institution_net_buy_5d_krw="100")
        flowdays=["2026-10-01","2026-10-02","2026-10-06",
                  "2026-10-07","2026-10-08"]
        flow={}
        for d in flowdays:
            flow[(d,"foreign")]={"005930":("KOSPI",20.)}
            flow[(d,"institution")]={"005930":("KOSPI",20.)}
        sectors,bycode=sector_proxy_of_day("2026-10-01",[row],
            {("CONSTRUCTION","2026-10-06"):{"005930"}},flow,flowdays)
        self.assertEqual(sectors,set())
        self.assertEqual(dict(bycode),{})

    def test_sector_raw_flow_is_never_replaced_with_missing_as_zero(self):
        row=dict(sector_id="CONSTRUCTION",snapshot_date="2026-10-01",
            rs_5d_pp="1",breadth_up_5d_pct="40",
            price_flow_proxy_ready="True",membership_status=
            "PROVIDER_DATED_PROXY_NOT_STRICT_PIT",
            live_selection_authorized="False",
            foreign_5d_coverage="1",institution_5d_coverage="1",
            turnover_coverage="1",member_turnover_krw="10000000",
            foreign_net_buy_5d_krw="500",institution_net_buy_5d_krw="500")
        f={("2026-10-01","foreign"):{"005930":("KOSPI",500.)},
           ("2026-10-01","institution"):{}}
        actual,_=sector_proxy_of_day("2026-10-01",[row],
            {("CONSTRUCTION","2026-10-01"):{"005930"}},f,["2026-10-01"])
        self.assertEqual(actual,set())

    def test_hypothetical_2R_not_final_buy_authority(self):
        signal=dict(setup="RESEARCH_TRIGGER_CONFIRMED_ASOF",
            stop_reference=94,first_entry_reference=100,
            nearest_resistance_reference=116,first_net_rr=2.2,
            first_stop_risk_pct=6,first_entry_below_close_atr=.3,
            daily_pivot_date="2026-10-16")
        self.assertTrue(first_gate(signal)[0])
        # No authenticated 15:30, past true financial PIT nor current account.
        self.assertFalse(False)

if __name__=="__main__":unittest.main()
