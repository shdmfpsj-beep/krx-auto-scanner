#!/usr/bin/env python3
"""Concise mobile report tests: no fabricated approvals, stale links or prices."""
import unittest,json,tempfile,sys
from pathlib import Path
from unittest.mock import patch
from sector_first_compact_report import format_summary,krw,safe_link,main
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
    def test_source_blocked_day_creates_compact_cash_summary_without_price_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            acq=dict(schema="sector_source_acquisition_v1",ready=False,
                status="PENDING_DATA_VALIDATION",
                errors=["ARTIFACT_UNAVAILABLE:sector-evidence-v18-report"],
                trade_approved=False)
            daily=dict(sector_selection_outcome="PENDING_DATA_VALIDATION",
                stock_selection_outcome="PENDING_DATA_VALIDATION",
                decision="CASH",trade_approved=False,approved_buy_count=0,
                sector_top3=[],stock_research_top5=[],asof=None,
                c3_position_state=dict(user_reported=True,closed_ticker="004490",
                                       closed_shares_remaining=0))
            (root/"source_selection_status.json").write_text(json.dumps(acq),encoding="utf-8")
            (root/"sector_first_daily_status.json").write_text(json.dumps(daily),encoding="utf-8")
            with patch.object(sys,"argv",["prog","--root",str(root)]):
                main()
            text=(root/"sector_first_compact_mobile.md").read_text(encoding="utf-8")
            self.assertIn("TOP5 최종 산출 보류",text)
            self.assertIn("최종 판정 보류",text)
            self.assertIn("ARTIFACT_UNAVAILABLE:sector-evidence-v18-report",text)
            self.assertIn("세방전지(004490) 전량 매도",text)
            self.assertIn("CASH",text)
            self.assertNotIn("검증 완료: 적격 섹터 0개",text)

    def test_missing_price_file_is_error_if_source_claims_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"source_selection_status.json").write_text(json.dumps(dict(
                schema="sector_source_acquisition_v1",ready=True,
                status="VERIFIED_SOURCE_SELECTED",trade_approved=False)),encoding="utf-8")
            (root/"sector_first_daily_status.json").write_text(json.dumps(dict(
                sector_selection_outcome="PENDING_DATA_VALIDATION",
                stock_selection_outcome="PENDING_DATA_VALIDATION",
                decision="CASH",trade_approved=False,approved_buy_count=0,
                sector_top3=[],stock_research_top5=[])),encoding="utf-8")
            with patch.object(sys,"argv",["prog","--root",str(root)]):
                with self.assertRaisesRegex(SystemExit,"MISSING_FINAL_SECTOR_PRICE_REPORT"):
                    main()

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
        self.assertIn("TOP5 최종 산출 보류",md)
        self.assertIn("해외 원문 출처 없음",md)
        self.assertIn("CASH",md)
    def test_final_mobile_report_never_labels_missing_data_as_verified_zero(self):
        data={"asof":"2026-10-22","sector_selection_outcome":"PENDING_DATA_VALIDATION",
              "stock_selection_outcome":"PENDING_DATA_VALIDATION",
              "daily_money_gate":"MARKET_OHLC_CONFLICT",
              "sector_top3":[],"stock_research_top5":[],
              "c3_position_state":{"user_reported":True,
                   "closed_ticker":"004490","closed_shares_remaining":0}}
        md=format_summary(data)
        self.assertIn("최종 판정 보류 (데이터 정합성 미충족)",md)
        self.assertIn("TOP5 최종 산출 보류",md)
        self.assertIn("세방전지(004490) 전량 매도",md)
        self.assertIn("BUY 승인만 0건",md)
        self.assertNotIn("적격 섹터 0개",md)

    def test_verified_no_positive_flow_reports_cash_without_false_data_gap(self):
        md=format_summary({"asof":"2026-10-22",
             "daily_money_gate":"VERIFIED_NO_QUALIFYING_SECTOR",
             "sector_selection_outcome":"VERIFIED_NO_QUALIFYING_SECTOR",
             "stock_selection_outcome":"NO_RESEARCH_STOCKS_QUALIFIED",
             "sector_top3":[],"stock_research_top5":[]})
        self.assertIn("당일 KRX 자료가 검증됐으나",md)
        self.assertIn("플러스 순매수인 섹터가 없어",md)
        self.assertIn("신규매수: CASH",md)
        self.assertNotIn("해당일 완결되지 않아",md)

    def test_corrupt_market_ohlc_totals_are_visible_not_invented(self):
        state={"asof":"2026-10-22","sector_selection_outcome":"PENDING_DATA_VALIDATION",
               "stock_selection_outcome":"PENDING_DATA_VALIDATION",
               "sector_top3":[],"stock_research_top5":[],
               "raw_tradable_ohlc_checked":2563,
               "raw_ohlc_conflict_count":657,"raw_ohlc_conflict_pct":25.63}
        md=format_summary(state)
        self.assertIn("657/2563",md)
        self.assertIn("25.63%",md)
        self.assertIn("최종 판정 보류",md)
        self.assertNotIn("검증 완료: 적격 섹터 0개",md)
        self.assertIn("CASH",md)

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
