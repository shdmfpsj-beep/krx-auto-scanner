#!/usr/bin/env python3
"""Daily measurable progress: weak market is NOT corrupt source data."""
import unittest
from daily_readiness_progress import build,markdown

DAY="2026-10-22"
def sample(sid="CONSTRUCTION",flow=20_000_000_000,breadth=43.75):
    return dict(sector_id=sid,price_flow_coverage=1.0,breadth_coverage=1.0,
                day_breadth_pct=breadth,day_net_flow_krw=flow)
def inputs():
    money=dict(asof=DAY,market_price_stock_count=2675,
        sector_samples=[sample("CONSTRUCTION"),sample("POWER",31_500_000_000,16.67),
                        sample("INSURANCE",11_560_000_000,36.36)],
        selected_top3=[],complete_three=False,overlaps_removed=True)
    bridge=dict(asof=DAY,daily_money_gate="INVALID_STALE_OR_INCOMPLETE")
    summary=dict(asof=DAY,stock_research_top5=[],sector_top3=[],decision="CASH")
    entry=dict(asof=DAY,stock_count=0,technical_geometry_pass_count=0,candidates=[])
    paper=dict(signal_count=0,closed_count=0)
    proof=dict(profit_proof_status="INSUFFICIENT_PROSPECTIVE_EVIDENCE",
               sample_sufficiency_met=False,integrity_pass=True)
    return money,bridge,summary,entry,paper,proof

class DailyProgressTests(unittest.TestCase):
    def test_no_positive_flow_session_is_data_verified_and_cash(self):
        a=list(inputs())
        for item in a[0]["sector_samples"]:
            item["day_net_flow_krw"]=-abs(item["day_net_flow_krw"])
            item["base_eligible"]=True
        r=build(*a)
        self.assertEqual(r["evidence_progress_pct"],29)
        self.assertEqual(r["passed_gates"],2)
        self.assertEqual(r["market_source_status"],"VERIFIED_NO_POSITIVE_FLOW_SECTOR")
        self.assertTrue(r["success_on_cautious_cash_day"])
        self.assertEqual(r["completed_paper_trades"],0)
        self.assertFalse(r["trade_approved"])
        self.assertIn("2/7관문",markdown(r))
    def test_stale_cross_file_dates_never_count_as_verified(self):
        a=list(inputs())
        a[1]={**a[1],"asof":"2026-10-21"}
        r=build(*a)
        self.assertEqual(r["passed_gates"],0)
        self.assertEqual(r["market_source_status"],"SOURCE_ASOF_MISMATCH")
    def test_no_data_gives_zero_not_fake_progress(self):
        r=build(*({} for _ in range(6)))
        self.assertEqual(r["passed_gates"],0)
        self.assertEqual(r["evidence_progress_pct"],0)
        self.assertEqual(r["decision"],"CASH")
    def test_unknown_stock_breadth_blocks_market_completeness(self):
        a=list(inputs())
        a[0]["sector_samples"][2]["breadth_coverage"]=0.4
        r=build(*a)
        self.assertEqual(r["passed_gates"],1)
        self.assertEqual(r["market_source_status"],"DATA_MISSING_OR_LOW_COVERAGE")
    def test_partial_two_sector_set_does_not_claim_three(self):
        a=list(inputs())
        a[0]["selected_top3"]=[dict(sector_id="POWER",day_breadth_pct=65,
                                    incremental_day_net_flow_krw=1_000_000_000)]
        r=build(*a)
        self.assertEqual(r["passed_gates"],2)
        self.assertEqual(r["market_source_status"],"FLOW_RANKING_MISSING_OR_PARTIAL")
    def test_future_paper_profit_cannot_overcome_missing_market_gates(self):
        a=list(inputs())
        a[4]=dict(signal_count=35,closed_count=31)
        a[5]=dict(sample_sufficiency_met=True,integrity_pass=True,
                  profit_proof_status="PROVISIONAL_PAPER_EDGE_NOT_LIVE_OR_OOS_PROVEN")
        r=build(*a)
        self.assertEqual(r["passed_gates"],4)
        self.assertFalse(r["trade_approved"])
        self.assertFalse(r["orders_enabled"])
        self.assertEqual(r["decision"],"CASH")
    def test_full_research_gates_are_not_live_buy_certification(self):
        a=list(inputs())
        a[0]["selected_top3"]=[dict(sector_id=s,day_breadth_pct=71,
                             incremental_day_net_flow_krw=50_000_000_000,
                             flow_coverage=1.0)
                             for s in ("A","B","C")]
        a[0]["complete_three"]=True
        a[1].update(daily_money_rank_applied=True,
                    daily_money_gate="VERIFIED_1D_EARLY_FLOW_RESEARCH_ONLY")
        a[2]["sector_top3"]=[dict(sector_id=s) for s in ("A","B","C")]
        a[2]["stock_research_top5"]=[dict(ticker=f"{i:06d}")
                                      for i in range(5)]
        a[3].update(stock_count=5,technical_geometry_pass_count=2)
        a[4].update(signal_count=40,closed_count=35)
        a[5].update(sample_sufficiency_met=True,integrity_pass=True,
            profit_proof_status="PROVISIONAL_PAPER_EDGE_NOT_LIVE_OR_OOS_PROVEN")
        r=build(*a)
        self.assertEqual(r["passed_gates"],7)
        self.assertEqual(r["evidence_progress_pct"],100)
        self.assertFalse(r["final_80_trade_score_verified"])
        self.assertFalse(r["trade_approved"])
    def test_early_flow_three_sectors_pass_research_not_trade(self):
        a=list(inputs())
        a[0]["selected_top3"]=[dict(sector_id=s,day_breadth_pct=b,
               incremental_day_net_flow_krw=50_000_000_000,
               flow_coverage=1.0) for s,b in
               (("CONSTRUCTION",43.75),("POWER",16.67),("DEFENSE",0))]
        a[0]["complete_three"]=True
        a[1].update(daily_money_rank_applied=True,
                    daily_money_gate="VERIFIED_1D_EARLY_FLOW_RESEARCH_ONLY")
        a[2]["sector_top3"]=[dict(sector_id=s) for s in
                            ("CONSTRUCTION","POWER","DEFENSE")]
        r=build(*a)
        self.assertEqual(r["passed_gates"],3)
        self.assertEqual(r["market_source_status"],"PRE_EXPANSION_FLOW_WATCH")
        self.assertEqual(r["expanding_sector_count"],0)
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["decision"],"CASH")

    def test_high_positive_flow_is_not_enough_without_breadth(self):
        a=list(inputs())
        a[0]["sector_samples"]=[sample("POWER",600_000_000_000,25),
                                sample("CONSTRUCTION",200_000_000_000,30),
                                sample("SHIP",90_000_000_000,20)]
        r=build(*a)
        self.assertEqual(r["market_source_status"],"FLOW_RANKING_MISSING_OR_PARTIAL")
        self.assertFalse(r["gates"][2]["passed"])

if __name__=="__main__":unittest.main()
