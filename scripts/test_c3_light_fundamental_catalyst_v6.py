"""C3 v6 soft financial/news context tests. No P/L backtest or broker access."""
import os,unittest,tempfile
import pandas as pd
from c3_light_fundamental_catalyst_v6 import (
  latest_eligible_financial,catalyst_context,review_one,run)

ARCHIVE=os.getenv("C3_STOCK_FIRST_SOURCE_ZIP")
RANKED=os.getenv("C3_V5_RANKED_CSV")
FSTATE="PROVISIONAL_API_SNAPSHOT_NOT_PIT_VERIFIED"

def financial_frame(records):
    return pd.DataFrame(records,columns=[
     "ticker","filing_date","available_date","validation_status","receipt_no",
     "revenue_yoy_pct","op_profit_yoy_pct","op_margin_pct","debt_ratio_pct"])
def event_frame(records):
    return pd.DataFrame(records,columns=["ticker","filing_date","signal_date"])

class TestLightReview(unittest.TestCase):
    def row(self):
        return dict(ticker="271560",name="오리온",asof="2026-10-30",
            opportunity_score_not_probability=64.58,
            priority_class="PRIORITY_PULLBACK")

    def test_missing_fundamental_and_news_does_not_disqualify(self):
        x=review_one(self.row(),financial_frame([]),event_frame([]))
        self.assertEqual(x["combined_research_score"],64.58)
        self.assertEqual(x["financial_status"],"NO_COVERAGE_NEUTRAL")
        self.assertEqual(x["catalyst_status"],"NO_AUDITED_CATALYST_NEUTRAL")
        self.assertEqual(x["context_adjustment_points"],0)
        self.assertFalse(x["buy_approved"])

    def test_unpublished_report_cannot_appear_at_asof(self):
        f=financial_frame([dict(ticker="271560",filing_date="2026-11-02",
            available_date="2026-11-02",validation_status=FSTATE,
            receipt_no="X",revenue_yoy_pct=90,op_profit_yoy_pct=100,
            op_margin_pct=50,debt_ratio_pct=10)])
        x=latest_eligible_financial(f,"271560","2026-10-30")
        self.assertEqual(x["financial_status"],"NO_COVERAGE_NEUTRAL")
        self.assertIsNone(x["revenue_yoy_pct"])

    def test_provisional_severe_loss_only_a_flag_not_automatic_veto(self):
        f=financial_frame([dict(ticker="271560",filing_date="2026-10-29",
            available_date="2026-10-30",validation_status=FSTATE,
            receipt_no="X",revenue_yoy_pct=-25,op_profit_yoy_pct=-70,
            op_margin_pct=-15,debt_ratio_pct=650)])
        x=review_one(self.row(),f,event_frame([]))
        self.assertEqual(x["financial_risk_note"],
          "PROVISIONAL_POSSIBLE_LOSS_OR_LEVERAGE_NEEDS_REVIEW")
        self.assertEqual(x["combined_research_score"],64.58)
        self.assertEqual(x["context_adjustment_points"],0)

    def test_later_news_cannot_be_backfilled_as_earlier_catalyst(self):
        ev=event_frame([{"ticker":"271560","filing_date":"2026-11-03",
                         "signal_date":"2026-10-30"}])
        self.assertEqual(catalyst_context(ev,"271560","2026-10-30")[
            "catalyst_title_only_count"],0)

    def test_no_catalyst_points_from_historical_title_alone(self):
        ev=event_frame([{"ticker":"271560","filing_date":"2026-10-27",
                         "signal_date":"2026-10-30"}])
        x=catalyst_context(ev,"271560","2026-10-30")
        self.assertEqual(x["catalyst_bonus_points"],0)
        self.assertEqual(x["catalyst_status"],"TITLE_ONLY_NOT_A_CONFIRMED_CATALYST")

    @unittest.skipUnless(ARCHIVE and RANKED,"Frozen original scan and v5 ranking needed")
    def test_real_top2_stays_same_without_missing_news_penalty(self):
        with tempfile.TemporaryDirectory() as d:
            x=run(ARCHIVE,RANKED,d)
        self.assertEqual(x["candidate_count"],96)
        self.assertEqual([r["ticker"] for r in x["top2"]],["271560","026960"])
        self.assertEqual([r["combined_research_score"] for r in x["top2"]],[64.58,63.05])
        self.assertTrue(all(r["financial_status"]=="NO_COVERAGE_NEUTRAL" for r in x["top2"]))
        self.assertTrue(all(r["catalyst_bonus_points"]==0 for r in x["top2"]))
        self.assertTrue(x["no_historical_profitability_backtesting"])
        self.assertFalse(x["trade_approved"])
        self.assertFalse(x["orders_enabled"])

if __name__=="__main__":unittest.main()
