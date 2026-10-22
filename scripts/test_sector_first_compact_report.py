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
        self.assertIn("85점",md)
        self.assertIn("https://example.com/industry",md)
    def test_missing_evidence_does_not_make_up_prices(self):
        md=format_summary({"asof":"2026-10-22","sector_top3":[],"stock_research_top5":[]})
        self.assertIn("최신 섹터 연구 종목 없음",md)
        self.assertIn("해외 원문 출처 없음",md)
        self.assertIn("CASH",md)
    def test_independent_stop_price_takes_precedence_over_research_plan(self):
        row={**BASE["stock_research_top5"][0],"stop_reference":"175000"}
        md=format_summary({**BASE,"stock_research_top5":[row]})
        self.assertIn("203,500원",md)
        self.assertNotIn("175,000원",md)
    def test_markdown_urls_must_be_https_and_clean(self):
        self.assertIsNone(safe_link("javascript:alert(1)"))
        self.assertIsNone(safe_link("https://example.com/a)"))
        self.assertEqual(safe_link("https://example.com/a"),"https://example.com/a")
    def test_nonpositive_or_empty_price_never_becomes_fake_number(self):
        self.assertEqual(krw(""),"—")
        self.assertEqual(krw(None),"—")

if __name__=="__main__":
    unittest.main()
