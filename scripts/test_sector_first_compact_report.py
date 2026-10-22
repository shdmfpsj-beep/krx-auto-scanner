#!/usr/bin/env python3
"""Concise mobile report tests: no fabricated approvals, stale links or prices."""
import unittest
from sector_first_compact_report import format_summary,krw,safe_link
BASE={"asof":"2026-10-22","sector_top3":[dict(name="반도체",
       research_priority_index=83.2,flow_proxy_5d_krw=200000000,
       member_turnover_krw=30000000000,
       global_news_observations=[dict(title="Semiconductor capital plan in Taiwan",
           url="https://example.com/industry")])],
      "stock_research_top5":[{"name":"삼성전자","ticker":"005930",
          "independently_collected_daily_stop_reference":"203500",
          "independent_first_entry_reference":"220,000~224,000",
          "independent_second_entry_reference":"214,000~216,000",
          "independent_stop_status":"HISTORICAL_DAILY_REFERENCE_ONLY"}]}

class CompactTests(unittest.TestCase):
    def test_mobile_top3_and_explicit_price_without_buy(self):
        md=format_summary(BASE)
        self.assertIn("반도체",md)
        self.assertIn("203,500원",md)
        self.assertIn("220,000~224,000",md)
        self.assertIn("CASH",md)
        self.assertIn("80점",md)
        self.assertIn("https://example.com/industry",md)
    def test_missing_evidence_does_not_make_up_prices(self):
        md=format_summary({"asof":"2026-10-22","sector_top3":[],"stock_research_top5":[]})
        self.assertIn("최신 섹터 연구 종목 없음",md)
        self.assertIn("해외 원문 출처 없음",md)
        self.assertIn("CASH",md)
    def test_complete_oct22_weak_breadth_reports_cash_without_false_data_gap(self):
        md=format_summary({"asof":"2026-10-22",
             "daily_money_gate":"VERIFIED_NO_QUALIFYING_SECTOR",
             "sector_top3":[],"stock_research_top5":[]})
        self.assertIn("오늘 완료된 KRX 수급자료는 검증됐으나",md)
        self.assertIn("플러스 순매수인 섹터가 없어",md)
        self.assertIn("신규매수: CASH",md)
        self.assertNotIn("해당일 완결되지 않아",md)

    def test_pre_expansion_flow_visible_in_final_report_without_buy(self):
        sector=dict(BASE["sector_top3"][0],name="건설",
                    day_net_flow_1d_incremental_krw=210491705060,
                    day_breadth_up_pct=43.75,flow_phase="NARROW_POSITIVE")
        md=format_summary({**BASE,"sector_top3":[sector]})
        self.assertIn("NARROW_POSITIVE",md)
        self.assertIn("43.75%",md)
        self.assertIn("상승확산 60% 미만도 연구 후보",md)
        self.assertIn("CASH",md)

    def test_independent_stop_price_takes_precedence_over_research_plan(self):
        row={**BASE["stock_research_top5"][0],"stop_reference":"175000"}
        md=format_summary({**BASE,"stock_research_top5":[row]})
        self.assertIn("203,500원",md)
        self.assertNotIn("175,000원",md)
    def test_conflicted_market_close_blocks_all_stale_prices_in_main_table(self):
        row={**BASE["stock_research_top5"][0],
             "stop_reference":"175000",
             "first_reference":"176000",
             "second_reference":"172000",
             "independent_stop_status":"CROSS_SOURCE_CLOSE_CONFLICT"}
        md=format_summary({**BASE,"stock_research_top5":[row],
             "focus_close_conflict_tickers":["005930"]})
        table=md.split("## ②")[1].split("### 섹터별")[0]
        self.assertIn("| 삼성전자 | — | — | — |",table)
        self.assertNotIn("175,000원",table)
        self.assertNotIn("203,500원",table)
        self.assertNotIn("176000",table)
    def test_date_mismatch_never_reuses_research_entry_references(self):
        row={**BASE["stock_research_top5"][0],
             "independent_stop_status":"FOCUS_DATE_MISMATCH",
             "first_reference":"175000"}
        md=format_summary({**BASE,"stock_research_top5":[row]})
        table=md.split("## ②")[1].split("### 섹터별")[0]
        self.assertIn("| 삼성전자 | — | — | — |",table)
    def test_unconflicted_completed_daily_reference_still_rendered(self):
        md=format_summary(BASE)
        self.assertIn("203,500원",md)
        self.assertIn("220,000~224,000",md)
    def test_markdown_urls_must_be_https_and_clean(self):
        self.assertIsNone(safe_link("javascript:alert(1)"))
        self.assertIsNone(safe_link("https://example.com/a)"))
        self.assertEqual(safe_link("https://example.com/a"),"https://example.com/a")
    def test_nonpositive_or_empty_price_never_becomes_fake_number(self):
        self.assertEqual(krw(""),"—")
        self.assertEqual(krw(None),"—")

if __name__=="__main__":
    unittest.main()
