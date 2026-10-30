"""Regression cases for changing market results and corrupt research outputs."""
import copy
import unittest
from pipeline_result_contract_v1 import validate_broad, validate_dart


def issuer():
    return dict(schema="C3_K100_OFFICIAL_ISSUER_ENTRY_V610", asof="2026-10-29",
                full_market_initial_codes=2, input_v68_candidates=1,
                v68_source_run_id="40868884405", decision="CASH",
                trade_approved=False, orders_enabled=False)


def broad_fixture():
    source=issuer()
    report=dict(schema="C3_K100_BROAD_COVERAGE_RISK_FIRST_WATCH_V611",
        asof=source["asof"], full_market_universe=2,
        official_common_120day_50e8_liquid=1,
        official_common_120day_liquid_5d_positive_FI=1,
        both_investors_5d_net_buy_positive=0,
        strong_proxy_sector_5d_positive_liquid=0,
        broad_radar_universe_untouched_by_old_52_candidate_filter=True,
        final_80_score_verified=False, regular_1530_session_certified=False,
        financial_and_catalyst_verified=False, analyzed_pattern_method_rows=3,
        confirmed_research_trigger_rows=0, both_limit_alternatives_2R_research_rows=0,
        observed_watches={"strong_sector_watch":[]},
        group_counts={"strong_sector_watch":0}, decision="CASH",
        trade_approved=False, orders_enabled=False)
    rows=[dict(ticker="005930", asof=source["asof"],
        two_sided_fi_positive="False", in_strong_sector_proxy="False",
        trade_approved="False", orders_enabled="False")]
    audit=[dict(ticker=t,asof=source["asof"],phase=p,
        trade_approved="False",orders_enabled="False")
        for t,p in [("005930","RESEARCH_WATCH"),("000660","EXCLUDED")]]
    return report,source,rows,audit


def dart_fixture():
    source=issuer()
    report=dict(schema="C3_K100_DART_DATE_ONLY_DISCLOSURE_V6101", asof=source["asof"],
        upstream_v610_candidates=1, v610_v18_source_run_id=source["v68_source_run_id"],
        strict_intraday_PIT_publication_time_available=False, fundamental_growth_checked=False,
        catalyst_effect_and_amount_checked=False, score80_final_checked=False,
        title_keywords_are_not_positive_earnings_verification=True, observation_window_days=30,
        strictly_preceding_receipts_captured=1, date_only_source_receipt_count=1,
        stocks_with_strict_prior_receipt=1, decision="CASH", trade_approved=False,orders_enabled=False)
    stocks=[dict(ticker="005930",asof=source["asof"],trade_approved="False",orders_enabled="False",
                 actual_earnings_direction_verified="False",prior_30_calendar_day_receipts="1")]
    receipts=[dict(ticker="005930",receipt_no="20261028000001",receipt_date="2026-10-28",
                   trade_approved="False",orders_enabled="False",report_content_verified="False")]
    return report,source,stocks,receipts,copy.deepcopy(stocks)


class ResearchOutputContractTest(unittest.TestCase):
    def test_zero_strong_sector_and_zero_triggers_is_success(self):
        self.assertEqual(validate_broad(*broad_fixture())["strong_sector_watch"],0)

    def test_zero_flow_watch_is_valid_without_silent_missing_audit(self):
        r,s,rows,a=broad_fixture()
        r.update(official_common_120day_liquid_5d_positive_FI=0,analyzed_pattern_method_rows=0)
        a[0]["phase"]="EXCLUDED"
        self.assertEqual(validate_broad(r,s,[],a)["flow_watch"],0)

    def test_partial_universe_cannot_be_called_success(self):
        r,s,rows,a=broad_fixture()
        with self.assertRaisesRegex(ValueError,"COVERAGE"):
            validate_broad(r,s,rows,a[:-1])

    def test_unknown_and_boolean_counts_rejected(self):
        for value in [None,True,-1,1.0,"1"]:
            r,s,rows,a=broad_fixture();r["strong_proxy_sector_5d_positive_liquid"]=value
            with self.assertRaisesRegex(ValueError,"INVALID_COUNT"):
                validate_broad(r,s,rows,a)

    def test_impossible_subgroup_does_not_pass(self):
        r,s,rows,a=broad_fixture();r["strong_proxy_sector_5d_positive_liquid"]=2
        with self.assertRaisesRegex(ValueError,"IMPOSSIBLE"):
            validate_broad(r,s,rows,a)

    def test_repeated_ticker_and_wrong_date_rejected(self):
        r,s,rows,a=broad_fixture();a[1]["ticker"]=a[0]["ticker"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            validate_broad(r,s,rows,a)
        r,s,rows,a=broad_fixture();rows[0]["asof"]="2026-10-28"
        with self.assertRaisesRegex(ValueError,"ASOF"):
            validate_broad(r,s,rows,a)

    def test_unapproved_orders_never_enabled_by_empty_sector(self):
        r,s,rows,a=broad_fixture();r["orders_enabled"]=True
        with self.assertRaisesRegex(ValueError,"APPROVAL"):
            validate_broad(r,s,rows,a)

    def test_different_candidate_date_and_count_from_old_52_are_valid(self):
        r,s,rows,docs,parents=dart_fixture()
        self.assertEqual(validate_dart(r,s,rows,docs,parents)["coverage"],1)

    def test_dart_zero_candidates_and_receipts_can_be_complete(self):
        r,s,rows,docs,parents=dart_fixture();s["input_v68_candidates"]=0
        r.update(upstream_v610_candidates=0,strictly_preceding_receipts_captured=0,
                 stocks_with_strict_prior_receipt=0,date_only_source_receipt_count=0)
        self.assertEqual(validate_dart(r,s,[],[],[])["prior_receipts"],0)

    def test_dart_same_day_future_and_stale_receipts_rejected(self):
        for day in ["2026-10-29","2026-10-30","2026-09-28"]:
            r,s,rows,docs,parents=dart_fixture();docs[0]["receipt_date"]=day
            with self.assertRaisesRegex(ValueError,"SAME_DAY_FUTURE_OR_STALE"):
                validate_dart(r,s,rows,docs,parents)

    def test_dart_parent_date_and_ancestor_must_match(self):
        for key,value in [("asof","2026-10-28"),("v610_v18_source_run_id","99999999")]:
            r,s,rows,docs,parents=dart_fixture();r[key]=value
            with self.assertRaisesRegex(ValueError,"MISMATCH"):
                validate_dart(r,s,rows,docs,parents)

    def test_missing_issuer_is_not_zero_receipt_result(self):
        r,s,rows,docs,parents=dart_fixture()
        with self.assertRaisesRegex(ValueError,"CANDIDATE_SET"):
            validate_dart(r,s,rows,docs,[])

    def test_report_title_cannot_be_promoted_to_verified_earnings(self):
        r,s,rows,docs,parents=dart_fixture();rows[0]["actual_earnings_direction_verified"]="True"
        with self.assertRaisesRegex(ValueError,"EARNINGS_VERIFICATION"):
            validate_dart(r,s,rows,docs,parents)


if __name__ == "__main__":
    unittest.main()
