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
    def test_concentrated_absolute_top5_keeps_best_and_watches_all_three_sectors(self):
        summary,sectors,rows=inputs()
        # Seven valid constituent stocks, five leading one sector.
        rows=[dict(rows[0],ticker=f"{i+100:06d}",
                   name=f"LeadStock{i}",research_proxy_index=str(99-i))
              for i in range(5)]
        rows.extend([{**inputs()[2][1],"research_proxy_index":"54"},
                     {**inputs()[2][2],"research_proxy_index":"50"}])
        result=build(summary,sectors,rows,D)
        self.assertEqual(len(result["stock_research_top5"]),5)
        self.assertEqual(set(x["sector_id"] for x in result["stock_research_top5"]),
                         {"SEMIS"})
        self.assertTrue(result["stock_top5_concentration_warning"])
        self.assertEqual(len(result["sector_leader_watch"]),3)
        self.assertEqual([x["sector_id"] for x in result["sector_leader_watch"]],
                         ["SEMIS","POWER","SHIP"])
        self.assertTrue(result["sector_leader_watch"][1]["not_in_global_top5"])
        self.assertTrue(result["sector_leader_watch"][2]["not_in_global_top5"])
        self.assertEqual(result["decision"],"CASH")
        self.assertFalse(result["sector_watch_is_buy_recommendation"])
        self.assertIn("집중 경고",render(result))
    def test_research_watch_with_unavailable_sector_does_not_invent_company(self):
        summary,sectors,rows=inputs()
        rows=[r for r in rows if r["sector_id"]!="SHIP"]
        result=build(summary,sectors,rows,D)
        self.assertEqual(len(result["sector_leader_watch"]),2)
        self.assertNotIn("SHIP",[r["sector_id"] for r in result["sector_leader_watch"]])
        self.assertIn("데이터 부족",render(result))
    def test_pre_expansion_money_sectors_are_visible_but_never_approved(self):
        s,sectors,stocks=inputs()
        s["research_top3_sector_ids"]=["CONSTRUCTION","POWER","DEFENSE"]
        sectors=[]
        for sid,breadth in (("CONSTRUCTION",43.75),("POWER",16.67),("DEFENSE",0)):
            sectors.append(dict(sector_id=sid,sector_name=sid,asof=str(D),
               research_eligible="YES",trade_approval="NO",
               day_net_1d_incremental_krw="100000000",
               day_breadth_up_pct=str(breadth),
               flow_phase=("NARROW_POSITIVE" if breadth else "DIVERGENT_ALL_DOWN")))
        stocks[0]["sector_id"]="CONSTRUCTION"
        out=build(s,sectors,stocks,D)
        self.assertEqual(len(out["sector_top3"]),3)
        self.assertEqual(out["pre_expansion_sector_count"],3)
        self.assertEqual(out["status"],"EARLY_FLOW_WATCH_ONLY")
        self.assertEqual(out["decision"],"CASH")
        self.assertFalse(out["orders_enabled"])
        self.assertTrue(all(x["buy_approval"]=="NO" for x in out["sector_top3"]))
        self.assertIn("DIVERGENT_ALL_DOWN",render(out))
        self.assertIn("자금 선행",render(out))

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
        self.assertIn("판정 보류 (자료 정합성 미충족)",md)
        self.assertEqual(o["sector_top3"],[])
        self.assertFalse(o["orders_enabled"])
    def test_missing_or_mismatched_asof_is_pending_not_verified_zero(self):
        s,sectors,stocks=inputs()
        s["scan_date"]="2026-10-21"
        result=build(s,sectors,stocks,D)
        self.assertEqual(result["sector_selection_outcome"],"PENDING_DATA_VALIDATION")
        self.assertEqual(result["stock_selection_outcome"],"PENDING_DATA_VALIDATION")
        self.assertIsNone(result["verified_sector_count"])
        self.assertIsNone(result["verified_stock_research_count"])
        self.assertEqual(result["approved_buy_count"],0)
        md=render(result)
        self.assertIn("판정 보류",md)
        self.assertIn("최종 산출 보류",md)
        self.assertNotIn("검증 완료: 조건 충족 섹터 0개",md)

    def test_verified_no_positive_money_reports_real_zero(self):
        s,sectors,stocks=inputs()
        s["research_top3_sector_ids"]=[]
        s["daily_money_gate"]="VERIFIED_NO_QUALIFYING_SECTOR"
        result=build(s,sectors,stocks,D)
        self.assertEqual(result["sector_selection_outcome"],"VERIFIED_NO_QUALIFYING_SECTOR")
        self.assertEqual(result["verified_sector_count"],0)
        self.assertIn("검증 완료: 조건 충족 섹터 0개",render(result))
        self.assertEqual(result["decision"],"CASH")

    def test_explicit_c3_full_exit_is_not_treated_as_active_position(self):
        from c3_account_state import load_c3_position
        state=load_c3_position()
        s,sectors,stocks=inputs()
        result=build(s,sectors,stocks,D,state)
        self.assertEqual(result["c3_position_state"]["closed_shares_remaining"],0)
        self.assertFalse(result["c3_position_state"]["prior_thesis_active"])
        self.assertIn("세방전지(004490) 전량 매도",render(result))
        self.assertNotIn("4주 보유",render(result))

    def test_source_stock_not_approved(self):
        s,sectors,stocks=inputs()
        stocks[0]["trade_approval"]="YES"
        o=build(s,sectors,stocks,D)
        self.assertNotIn("000001",[r["ticker"] for r in o["stock_research_top5"]])

if __name__=="__main__":
    unittest.main()
