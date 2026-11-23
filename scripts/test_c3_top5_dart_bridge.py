"""Offline DART evidence, insolvency and failure-state regressions."""
import unittest
from datetime import date
from c3_top5_dart_bridge import bridge
from c3_top5_financial_selection import select
from test_c3_top5_financial_selection import candidate

TODAY = date(2026, 11, 20)
BASE = dict(asof='20261120', candidates=[dict(code='111111', name='A')])

def financial(**changes):
    item = dict(ticker='111111', name='A', status='DATED_ANNUAL_RESEARCH_ONLY',
        receipt_date='2026-03-20', latest_periodic_division_comparable=True,
        equity_krw=100, liabilities_krw=100, operating_profit_krw=10,
        financial_quality='ANNUAL_GROWTH_AND_MARGIN_OBSERVED',
        financial_screen_pass=True, annual_plus_interim_growth_pass=True,
        interim_research=dict(status='DATED_INTERIM_YTD_RESEARCH_ONLY',
            quality='INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED',
            filing=dict(receipt_date='2026-11-16')))
    item.update(changes)
    return dict(status='ANNUAL_RESEARCH_READ', researched=[item])

def run(payload, receipt=BASE):
    return bridge(receipt, 'dummy', TODAY, collector=lambda *a, **k: payload)

class BridgeTests(unittest.TestCase):
    def test_official_alphanumeric_code_reaches_collector_unchanged(self):
        def collector(day, stocks, key, today):
            self.assertEqual(stocks[0]['ticker'], '0220W0')
            payload=financial()
            payload['researched'][0]['ticker']='0220W0'
            return payload
        r=bridge({**BASE,'candidates':[dict(code='0220W0',name='한화머시너리앤서비스홀딩스')]},
                 'dummy',TODAY,collector)
        self.assertEqual(r['status'],'FINANCIAL_RESEARCH_GATE_PASSED')
    def test_valid_evidence_never_authorizes_or_claims_pit(self):
        r = run(financial())
        self.assertTrue(r['financial_verified'])
        self.assertFalse(r['point_in_time_snapshot_verified'])
        self.assertFalse(r['trade_approved'])
        self.assertEqual(len(r['researched']), 1)

    def test_historical_observation_is_explicitly_dated(self):
        r = run(financial(), {**BASE, 'asof':'20261119'})
        self.assertEqual(r['status'], 'HISTORICAL_DISCLOSURE_DATE_FILTERED_RESEARCH_ONLY')
        self.assertEqual(r['financial_observed_on'], '2026-11-20')
        self.assertFalse(r['financial_verified'])
        self.assertFalse(r['point_in_time_snapshot_verified'])

    def test_known_financial_risk_can_produce_normal_cash(self):
        for change in (dict(liabilities_krw=301), dict(operating_profit_krw=-10),
                       dict(equity_krw=0)):
            with self.subTest(change=change):
                r = run(financial(**change))
                self.assertEqual(r['status'], 'PARTIAL_OR_FAILED_FINANCIAL_GATE')
                x = select(dict(asof=BASE['asof'], candidates=[candidate()]), r)
                self.assertEqual(x['decision'], 'CASH')

    def test_recent_slowdown_is_flagged_not_insolvency(self):
        payload = financial(recent_financial_weakening_veto=True)
        payload['researched'][0]['interim_research']['quality'] = 'INTERIM_PROFIT_OR_SALES_WEAKENING'
        r = run(payload)
        self.assertTrue(r['researched'][0]['financial_risk_gate_pass'])
        self.assertTrue(r['researched'][0]['recent_slowdown_flag'])

    def test_failed_leverage_keeps_actual_metrics_for_audit(self):
        r = run(financial(liabilities_krw=301))
        item = r['excluded'][0]
        self.assertEqual(item['liabilities_to_equity_pct'], 301)
        self.assertEqual(item['equity_krw'], 100)
        self.assertEqual(item['liabilities_krw'], 301)
        self.assertEqual(item['operating_profit_krw'], 10)

    def test_insufficient_and_api_failed_evidence_are_distinct(self):
        for annual, expected in [('NO_LISTED_CORP_CODE', 'INSUFFICIENT_DATA'),
                                 ('FINANCIAL_API_UNAVAILABLE', 'API_ERROR'),
                                 ('BALANCE_SHEET_INCONSISTENT', 'VALIDATION_ERROR')]:
            with self.subTest(annual=annual):
                r = run(financial(status=annual))
                self.assertEqual(r['excluded'][0]['financial_evidence_state'], expected)
                self.assertEqual(r['status'], 'FAILED_FINANCIAL_EVIDENCE')

    def test_no_data_api_limit_and_nonfinite_values_are_distinct(self):
        for change, expected in ((dict(status='FINANCIAL_API_UNAVAILABLE',source_api_status='013'),
                                  'INSUFFICIENT_DATA'),
                                 (dict(status='FINANCIAL_API_UNAVAILABLE',source_api_status='020'),
                                  'API_ERROR'),
                                 (dict(operating_profit_krw=float('inf')), 'VALIDATION_ERROR')):
            with self.subTest(change=change):
                r = run(financial(**change))
                self.assertEqual(r['excluded'][0]['financial_evidence_state'], expected)
                self.assertFalse(r['financial_data_complete'])
        r = run(financial())
        self.assertTrue(r['financial_data_complete'])
        self.assertFalse(r['point_in_time_snapshot_verified'])
        self.assertIn('SECTOR_SPECIFIC_MODELS',r['unverified_checks'])

    def test_unavailable_or_late_statements_are_not_normal_cash(self):
        for change in (dict(status='DART_REQUEST_FAILED_TimeoutError'),
                       dict(operating_profit_krw=float('inf')),
                       dict(interim_research=dict(status='INTERIM_API_UNAVAILABLE')),
                       dict(receipt_date='2026-11-21'),
                       dict(latest_periodic_division_comparable=False)):
            with self.subTest(change=change):
                r = run(financial(**change))
                self.assertEqual(r['status'], 'FAILED_FINANCIAL_EVIDENCE')
                self.assertEqual(select(dict(asof=BASE['asof'], candidates=[candidate()]), r)['decision'], 'ERROR')

    def test_collector_exception_is_recorded_without_credentials(self):
        def broken(*a, **k): raise TimeoutError('secret')
        r = bridge(BASE, 'dummy', TODAY, broken)
        self.assertEqual(r['status'], 'DART_COLLECTION_FAILED_TimeoutError')
        self.assertNotIn('secret', str(r))

    def test_invalid_dates_key_and_duplicates_do_not_call_api(self):
        def forbidden(*a, **k): self.fail('API called')
        for receipt, key, expected in (({**BASE, 'asof':'20261199'}, 'dummy', 'INVALID_ASOF'),
            ({**BASE, 'asof':'20261121'}, 'dummy', 'FUTURE_ASOF_NOT_ALLOWED'),
            (BASE, None, 'MISSING_DART_KEY'),
            ({**BASE, 'candidates':BASE['candidates']*2}, 'dummy', 'DUPLICATE_TICKER'),
            ({**BASE, 'candidates':[dict(code='INVALID')]}, 'dummy', 'INVALID_TICKER'),
            ({**BASE, 'candidates':[]}, None, 'NO_CANDIDATES')):
            self.assertEqual(bridge(receipt, key, TODAY, forbidden)['status'], expected)

    def test_incomplete_and_duplicate_response_fail_closed(self):
        self.assertEqual(run(dict(researched=[]))['status'], 'INCOMPLETE_FINANCIAL_COVERAGE')
        p = financial()
        p['researched'] *= 2
        self.assertEqual(run(p)['status'], 'INVALID_FINANCIAL_COVERAGE')

if __name__ == '__main__': unittest.main()
