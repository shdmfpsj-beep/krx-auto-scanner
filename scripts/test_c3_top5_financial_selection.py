"""Offline boundary and ranking regressions; no prices or returns are simulated."""
import copy
import unittest
from c3_top5_financial_selection import (
    select, classify, valid_entry, entry_state, requested_candidates)

ASOF = '20261120'

def candidate(code='111111', status='ENTRY_READY', **changes):
    c = dict(code=code, name=code, status=status, entry_status=status,
             geometry_validated=True, entry_low=9800, entry_high=10000,
             stop_ref=9600, close=9900 if status == 'ENTRY_READY' else 10100,
             risk_pct=4.0, r1_ref=10500, r2_ref=None,
             score=70, opportunity_score=70)
    c.update(changes)
    return c

def record(ticker='111111', **changes):
    r = dict(ticker=ticker, financial_evidence_complete=True,
             annual_status='DATED_ANNUAL_RESEARCH_ONLY',
             interim_status='DATED_INTERIM_YTD_RESEARCH_ONLY',
             filing_date='2026-03-20', interim_filing_date='2026-11-16',
             financial_risk_gate_pass=True, exclusion_reasons=[],
             financial_quality='ANNUAL_POSITIVE_MIXED',
             interim_quality='INTERIM_MIXED', liabilities_to_equity_pct=100)
    r.update(changes)
    return r

def evidence(*rows, status='FINANCIAL_RESEARCH_GATE_PASSED'):
    return dict(asof=ASOF, status=status, researched=list(rows), excluded=[])

class GeometryTests(unittest.TestCase):
    def test_ready_boundaries_and_near_direction(self):
        for close in (9800, 9900, 10000):
            self.assertEqual(entry_state(9800, 10000, close), 'ENTRY_READY')
        self.assertEqual(entry_state(9800, 10000, 10100), 'NEAR_ENTRY')
        self.assertEqual(entry_state(9800, 10000, 9790), 'WATCH')
        self.assertEqual(entry_state(9800, 10000, 10300), 'WATCH')

    def test_invalid_price_orders_and_targets(self):
        for change in (dict(entry_low=10050), dict(entry_low=10000),
                       dict(stop_ref=9800), dict(r1_ref=10000),
                       dict(r2_ref=10400), dict(entry_high=10001),
                       dict(close=float('inf')), dict(risk_pct=True),
                       dict(geometry_validated=False)):
            with self.subTest(change=change):
                self.assertFalse(valid_entry(candidate(**change)))

    def test_exact_risk_is_enforced_before_rounding(self):
        self.assertTrue(valid_entry(candidate(stop_ref=9500, risk_pct=5)))
        # 5.004% rounds to the displayed 5.00%, but must still fail.
        self.assertFalse(valid_entry(candidate(entry_low=980000000, entry_high=1000000000,
            stop_ref=949960000, close=990000000, r1_ref=1010000000, risk_pct=5)))
        self.assertFalse(valid_entry(candidate(risk_pct=3)))

    def test_status_must_match_executable_zone(self):
        self.assertFalse(valid_entry(candidate('111111', 'NEAR_ENTRY', close=9790)))
        self.assertFalse(valid_entry(candidate('111111', 'NEAR_ENTRY', close=10300)))
        self.assertFalse(valid_entry(candidate('111111', 'ENTRY_READY', close=10100)))

    def test_risk_reward_below_two_is_allowed(self):
        self.assertTrue(valid_entry(candidate(r1_ref=10100)))

class SelectionTests(unittest.TestCase):
    def test_ready_precedes_financially_stronger_near(self):
        g = dict(asof=ASOF, candidates=[candidate(), candidate('222222', 'NEAR_ENTRY')])
        f = evidence(record(), record('222222', financial_quality='ANNUAL_GROWTH_AND_MARGIN_OBSERVED',
                                      interim_quality='INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED'))
        x = select(g, f)
        self.assertEqual([v['code'] for v in x['selected']], ['111111', '222222'])
        self.assertEqual([v['signal'] for v in x['signals']], ['BUY_CONSIDER', 'WAIT_FOR_ENTRY'])
        self.assertFalse(x['trade_approved'])

    def test_existing_financial_quality_reorders_same_state(self):
        g = dict(asof=ASOF, candidates=[candidate(opportunity_score=95),
                                      candidate('222222', opportunity_score=65)])
        f = evidence(record(), record('222222', financial_quality='ANNUAL_GROWTH_AND_MARGIN_OBSERVED',
                                      interim_quality='INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED'))
        self.assertEqual(select(g, f)['selected'][0]['code'], '222222')
        # Lower leverage is the next priority among equal quality evidence.
        f['researched'][1] = record('222222', liabilities_to_equity_pct=50)
        self.assertEqual(select(g, f)['selected'][0]['code'], '222222')

    def test_financial_risk_exclusion_and_slowdown_are_distinct(self):
        g = dict(asof=ASOF, candidates=[candidate(), candidate('222222')])
        f = evidence(record(recent_slowdown_flag=True,
                            interim_quality='INTERIM_PROFIT_OR_SALES_WEAKENING'),
                     record('222222', financial_risk_gate_pass=False,
                            exclusion_reasons=['BALANCE_SHEET_LEVERAGE_OR_EQUITY_RISK']))
        x = select(g, f)
        self.assertEqual([v['code'] for v in x['selected']], ['111111'])
        self.assertEqual(x['excluded_count'], 1)
        self.assertEqual(x['slowdown_flag_count'], 1)

    def test_invalid_or_missing_financials_are_error_not_cash(self):
        g = dict(asof=ASOF, candidates=[candidate()])
        f = evidence(record())
        variants = [{}, evidence(status='MISSING_DART_KEY'),
                    {**f, 'asof':'20261119'},
                    evidence(record(), record()),
                    evidence(record(interim_quality='UNKNOWN')),
                    evidence(record(interim_filing_date='2026-11-21'))]
        for v in variants:
            with self.subTest(evidence=v):
                x = select(g, v)
                self.assertEqual(x['decision'], 'ERROR')
                self.assertEqual(x['selected_count'], 0)

    def test_claimed_valid_but_unsafe_geometry_is_error(self):
        g = dict(asof=ASOF, candidates=[candidate(stop_ref=9800)])
        x = select(g, evidence(status='NO_CANDIDATES'))
        self.assertEqual(x['status'], 'ERROR_ENTRY_GEOMETRY')

    def test_exclusion_cannot_hide_incomplete_or_late_evidence(self):
        g = dict(asof=ASOF, candidates=[candidate()])
        for change in (dict(financial_evidence_complete=False),
                       dict(annual_status='FINANCIAL_API_UNAVAILABLE'),
                       dict(interim_filing_date='2026-11-21'),
                       dict(financial_quality='FINANCIAL_SECTOR_SPECIAL_MODEL_REQUIRED')):
            with self.subTest(change=change):
                row = record(financial_risk_gate_pass=False,
                             exclusion_reasons=['BALANCE_SHEET_LEVERAGE_OR_EQUITY_RISK'], **change)
                x = select(g, evidence(row))
                self.assertEqual(x['decision'], 'ERROR')
                self.assertEqual(x['financial_classifications']['111111'],
                                 'REVIEW_INSUFFICIENT_EVIDENCE')

    def test_zero_candidates_needs_no_dart_key(self):
        x = select(dict(asof=ASOF, candidates=[]), evidence(status='NO_CANDIDATES'))
        self.assertEqual(x['decision'], 'CASH')
        self.assertTrue(x['coverage_complete'])

    def test_rank_eleven_no_longer_hidden_by_ten_invalid_charts(self):
        invalid = [candidate(str(100000+i), status='WATCH', geometry_validated=False)
                   for i in range(10)]
        g = dict(asof=ASOF, candidates=invalid + [candidate('222222')])
        self.assertEqual([x['code'] for x in requested_candidates(g)], ['222222'])
        self.assertEqual(select(g, evidence(record('222222')))['selected_count'], 1)

    def test_financial_budget_is_bounded_and_top5_is_maximum(self):
        g = dict(asof=ASOF, candidates=[candidate(str(100000+i)) for i in range(35)])
        requested = requested_candidates(g)
        self.assertEqual(len(requested), 30)
        x = select(g, evidence(*(record(c['code']) for c in requested)))
        self.assertEqual(x['selected_count'], 5)
        self.assertEqual(x['financial_budget_deferred_count'], 5)

    def test_historical_disclosure_evidence_does_not_claim_pit(self):
        x = select(dict(asof=ASOF, candidates=[candidate()]),
                   evidence(record(), status='HISTORICAL_DISCLOSURE_DATE_FILTERED_RESEARCH_ONLY'))
        self.assertEqual(x['selected_count'], 1)
        self.assertFalse(x['historical_pit_certified'])

    def test_budget_deferred_unreviewed_candidates_cannot_be_normal_cash(self):
        g = dict(asof=ASOF,candidates=[candidate(str(100000+i)) for i in range(35)])
        rows = [record(c['code'],financial_risk_gate_pass=False,
                       exclusion_reasons=['BALANCE_SHEET_LEVERAGE_OR_EQUITY_RISK'])
                for c in requested_candidates(g)]
        x = select(g,evidence(*rows))
        self.assertEqual(x['decision'],'ERROR')
        self.assertFalse(x['coverage_complete'])
        self.assertEqual(x['financial_evidence_status'],'INCOMPLETE_FINANCIAL_COVERAGE_BUDGET')
        self.assertEqual(x['financial_budget_deferred_count'],5)

if __name__ == '__main__':
    unittest.main()
