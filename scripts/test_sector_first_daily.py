#!/usr/bin/env python3
"""Offline sector-first contract tests; no network credentials or trade orders."""
import unittest
from datetime import date,timedelta
from sector_first_daily import build,render,price_reference

D=date(2026,10,22)
def inputs():
    ids=["SEMIS","POWER","SHIP"]
    status=dict(asof=str(D),scan_date=str(D),core_data_verified=True,
      evidence_scan_dates_aligned=True,research_top3_sector_ids=ids)
    sectors=[dict(sector_id=x,sector_name=x,asof=str(D),
      research_eligible="YES",rs_5d_pp=str(3-i),
      breadth_up_5d_pct="65",foreign_net_buy_5d_krw="1000000",
      institution_net_buy_5d_krw="2000000") for i,x in enumerate(ids)]
    stocks=[dict(ticker=f"{i+1:06d}",name=f"Stock{i}",asof=str(D),
      sector_id=x,price_flow_ready="YES",research_proxy_index=str(95-i),
      trade_approval="NO",close="110",plan_status="STRUCTURE_CANDIDATE_REQUIRES_VALIDATION",
      plan_first_entry="105",plan_second_entry="102",plan_stop_reference="98",
      plan_reward_risk="2.3") for i,x in enumerate(ids)]
    return status,sectors,stocks

class SectorFirstTests(unittest.TestCase):
    def test_three_research_sectors_and_stocks_still_cash(self):
        s,sectors,stocks=inputs()
        out=build(s,sectors,stocks,D)
        self.assertEqual(len(out["sector_top3"]),3)
        self.assertEqual(len(out["stock_research_top5"]),3)
        self.assertEqual(out["decision"],"CASH")
        self.assertFalse(out["trade_approved"])
        self.assertIsNone(out["stock_research_top5"][0]["final_verified_score"])
        self.assertEqual(out["stock_research_top5"][0]["stop_reference"],98.0)
    def test_stale_sector_data_never_becomes_current_top3(self):
        s,sectors,stocks=inputs()
        o=build(s,sectors,stocks,D+timedelta(days=1))
        self.assertEqual(o["sector_top3"],[])
        self.assertEqual(o["stock_research_top5"],[])
        self.assertIn("NOT_TODAYS_COMPLETE_SECTOR_DATA",o["blockers"])
    def test_scan_date_mismatch_blocks_selection(self):
        s,sectors,stocks=inputs()
        s["scan_date"]="2026-10-21"
        o=build(s,sectors,stocks,D)
        self.assertEqual(o["sector_top3"],[])
        self.assertEqual(o["decision"],"CASH")
    def test_non_top3_stock_must_never_rank(self):
        s,sectors,stocks=inputs()
        stocks.append({**stocks[0],"ticker":"999999","sector_id":"OTHER",
                       "research_proxy_index":"100"})
        o=build(s,sectors,stocks,D)
        self.assertNotIn("999999",[r["ticker"] for r in o["stock_research_top5"]])
    def test_biotech_excluded_from_sector_and_stock(self):
        s,sectors,stocks=inputs()
        sectors[1]["sector_name"]="바이오"
        stocks[0]["name"]="제약 성장주"
        o=build(s,sectors,stocks,D)
        self.assertEqual(len(o["sector_top3"]),2)
        self.assertEqual({r["sector_id"] for r in o["sector_top3"]},{"SEMIS","SHIP"})
        self.assertNotIn("000001",[r["ticker"] for r in o["stock_research_top5"]])
        self.assertNotIn("000002",[r["ticker"] for r in o["stock_research_top5"]])
        self.assertIn("LESS_THAN_3_PROVISIONAL_SECTORS",o["blockers"])
    def test_unverified_or_invalid_ohlcv_levels_are_blank(self):
        r=dict(plan_status="STRUCTURE_CANDIDATE_REQUIRES_VALIDATION",
               plan_first_entry="100",plan_second_entry="102",
               plan_stop_reference="98",plan_reward_risk="3")
        self.assertEqual(price_reference(r),("","","",""))
        r.update(plan_first_entry="105",plan_second_entry="102",plan_reward_risk="1.2")
        self.assertEqual(price_reference(r),("","","",""))
        r["plan_reward_risk"]="2.5"
        self.assertEqual(price_reference(r),(105.0,102.0,98.0,2.5))
    def test_missing_all_sources_still_renders_cash(self):
        o=build({},[],[],D)
        md=render(o)
        self.assertIn("CASH",md)
        self.assertIn("오늘 확정할 섹터 없음",md)
        self.assertEqual(o["sector_top3"],[])
        self.assertFalse(o["orders_enabled"])
    def test_source_stock_not_approved(self):
        s,sectors,stocks=inputs()
        stocks[0]["trade_approval"]="YES"
        o=build(s,sectors,stocks,D)
        self.assertNotIn("000001",[r["ticker"] for r in o["stock_research_top5"]])

if __name__=="__main__":
    unittest.main()
