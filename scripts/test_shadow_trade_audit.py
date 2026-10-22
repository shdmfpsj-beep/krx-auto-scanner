#!/usr/bin/env python3
"""Offline no-future-return tests for prospective 5-session shadow ledger."""
import csv,tempfile,unittest
from pathlib import Path
from shadow_trade_audit import (
    evaluate,new_signals,merge_signals,price_history,summarise,ROUNDTRIP_COST_PCT)

SIG=dict(signal_date="2026-10-22",ticker="005930",sector_id="SEMICON",
         signal_close=100,signal_atr14=6,stop_reference=95,
         no_chase_reference=104,prior_high=120,
         research_proxy_index=80,plan_version="next_open_5d_v1")
REPORT=dict(asof="2026-10-22",status="PROVISIONAL_RESEARCH_ONLY",
      stock_research_top5=[dict(ticker="005930",sector_id="SEMICON",proxy_index=80)])
REF=dict(ticker="005930",latest_complete_date="2026-10-22",
         data_source="V18_KRX_CACHED",close="100",atr14="6",
         historical_stop_reference="95",no_chase_reference="104",
         prior_60d_high="120")
def bar(day,op=100,high=105,low=97,close=102):
    return dict(date=day,open=op,high=high,low=low,close=close)
DATES=["2026-10-23","2026-10-26","2026-10-27","2026-10-28","2026-10-29"]

class ShadowTests(unittest.TestCase):
    def test_new_signal_uses_verified_completed_asof_sector_ticker(self):
        rows=new_signals(REPORT,[REF])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["stop_reference"],95.0)
        self.assertEqual(rows[0]["signal_date"],"2026-10-22")
    def test_stale_source_never_creates_new_entry(self):
        self.assertEqual(new_signals(REPORT,[{**REF,"latest_complete_date":"2026-10-21"}]),[])
        self.assertEqual(new_signals({**REPORT,"asof":"2026-10-21"},[REF]),[])
        self.assertEqual(new_signals({**REPORT,"status":"NO_VERIFIED_TOP3"},[REF]),[])
    def test_conservative_stop_first_when_same_daily_candle_touches_both(self):
        bars=[bar(DATES[0],high=111,low=94)]
        outcome=evaluate(SIG,bars)
        self.assertEqual(outcome["status"],"CLOSED")
        self.assertEqual(outcome["exit_reason"],"STOP_FIRST_CONSERVATIVE")
        self.assertLess(outcome["net_return_pct"],-5)
    def test_target_filled_next_session_net_of_cost(self):
        result=evaluate(SIG,[bar(DATES[0],high=111,low=97)])
        self.assertEqual(result["exit_reason"],"TARGET_2R")
        self.assertAlmostEqual(result["net_return_pct"],10-ROUNDTRIP_COST_PCT)
    def test_gapped_below_stop_exit_is_not_fictitious_fill_at_stop(self):
        outcome=evaluate(SIG,[bar(DATES[0]),bar(DATES[1],op=92,high=99,low=90,close=95)])
        self.assertEqual(outcome["exit_reason"],"STOP_GAP_DOWN")
        self.assertEqual(outcome["exit_price"],92)
    def test_gap_up_no_chase_is_skipped(self):
        out=evaluate(SIG,[bar(DATES[0],op=108,high=110,low=100)])
        self.assertEqual(out["status"],"SKIP_GAP_UP_ABOVE_NO_CHASE")
    def test_prior_high_prevents_unrealistic_two_r_reward(self):
        s={**SIG,"prior_high":109}
        out=evaluate(s,[bar(DATES[0])])
        self.assertEqual(out["status"],"SKIP_PRIOR_RESISTANCE_BLOCKS_2R")
    def test_no_future_day_means_no_win_rate(self):
        results,summary=summarise([SIG],{})
        self.assertEqual(results[0]["status"],"PENDING_NEXT_TRADING_DAY")
        self.assertIsNone(summary["realised_paper_win_rate_pct"])
        self.assertIsNone(summary["realised_paper_avg_net_pct"])
    def test_horizon_requires_five_future_completed_bars(self):
        few=[bar(d) for d in DATES[:4]]
        out=evaluate(SIG,few)
        self.assertEqual(out["status"],"OPEN_WAIT_MORE_BARS")
        complete=evaluate(SIG,[bar(d) for d in DATES])
        self.assertEqual(complete["status"],"CLOSED")
        self.assertEqual(complete["exit_reason"],"HORIZON_5D_CLOSE")
        self.assertEqual(complete["hold_sessions"],5)
    def test_persist_first_signal_terms_do_not_rewrite_future_history(self):
        earlier={**SIG,"stop_reference":95}
        later={**SIG,"stop_reference":90}
        result=merge_signals([earlier],[later])
        self.assertEqual(result[0]["stop_reference"],95)
        self.assertEqual(len(result),1)
    def test_valid_bulk_market_evidence_from_existing_free_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"market/daily_prices/KOSPI"
            root.mkdir(parents=True)
            for d in ["2026-10-23","2026-10-26"]:
                with (root/(d+".csv")).open("w",newline="",encoding="utf-8") as f:
                    w=csv.DictWriter(f,fieldnames=["Date","ticker","Open","High","Low","Close"])
                    w.writeheader()
                    w.writerow(dict(Date=d,ticker="005930",Open=100,High=103,Low=97,Close=102))
            data=price_history(tmp,{"005930"})
            self.assertEqual(len(data["005930"]),2)
            self.assertEqual(evaluate(SIG,data["005930"])["status"],"OPEN_WAIT_MORE_BARS")
    def test_pre_open_signal_cannot_be_counted_as_filled_same_day(self):
        series=[bar("2026-10-22",high=111,low=94)]
        self.assertEqual(evaluate(SIG,series)["status"],"PENDING_NEXT_TRADING_DAY")
    def test_ledger_disallows_comparing_two_different_versions(self):
        bad={**SIG,"plan_version":"unknown"}
        self.assertEqual(merge_signals([bad],[]),[])

if __name__=="__main__":unittest.main()
