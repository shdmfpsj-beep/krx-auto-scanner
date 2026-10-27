import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

import c3_candidate_evidence_v1 as m

NOW = '2026-10-28T07:30:00+09:00'
ASOF = '2026-10-27'


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reports = self.root / 'reports'
        self.reports.mkdir()
        self.basic = self.root / 'basic'
        self.basic.mkdir()
        self.scope = self.root / 'scope.json'
        self.eod = self.root / 'eod'
        self.eod.mkdir()
        self.raw = dict(ticker='011200', name='HMM', latest_date=ASOF,
            c3_preliminary_score='84', instrument_type='UNKNOWN',
            turnover_krw='1000000', turnover_source='ESTIMATED_CLOSE_X_VOLUME',
            close_reference='22400')
        self.status = dict(scan_complete=True, data_date_verified=True,
                           market_data_date=ASOF, universe=2625, valid_ohlcv=2604)
        self.json(self.reports / 'status.json', self.status)
        self.csv(self.reports / 'c3_preliminary.csv', [self.raw])

    def json(self, path, obj):
        path.write_text(json.dumps(obj, ensure_ascii=False))

    def csv(self, path, rows, fields=None):
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    def basics(self, asof=ASOF, group='주권', kind='보통주'):
        meta = dict(schema=m.BASIC_SCHEMA, asof=asof,
            received_utc='2026-10-27T21:00:00Z', official_base_usable=True,
            official_base_approved=True, market_counts={}, source_file_sha256={})
        for market in m.MARKETS:
            row = dict(ticker='011200' if market == 'KOSPI' else '064400',
                market=market, asof_requested=asof, security_group=group,
                share_kind=kind, listed_date='20250101', source_endpoint=m.MARKETS[market])
            p = self.basic / (market + '_basic_v610.csv')
            self.csv(p, [row])
            meta['market_counts'][market] = 1
            meta['source_file_sha256'][market] = m.sha(p)
        self.json(self.basic / 'krx_basic_v610_status.json', meta)
        return meta

    def review(self, status='BUSINESS_REVIEWED_NON_PHARMA', reviewed_at=NOW):
        row = dict(ticker='011200', status=status, reviewed_at=reviewed_at,
            identity_verified=True, reason='Primary business review only',
            source_url='https://example.test/primary')
        obj = dict(schema=m.SCOPE_SCHEMA, reviews=[row])
        self.json(self.scope, obj)
        return obj

    def official_eod(self, asof=ASOF, turnover='987654', valid='True'):
        meta = dict(schema=m.EOD_SCHEMA, asof=asof,
            retrieval_utc='2026-10-27T21:00:00Z', official_dataset_usable=True,
            krx_eod_authenticated=True, official_market_rows=2,
            independent_1530_regular_session_certified=True,
            market_file_sha256={})
        for market in m.MARKETS:
            row = dict(ticker='011200' if market == 'KOSPI' else '064400',
                market=market, asof=asof, open='22300', high='22500', low='22000',
                close='22400', volume='100', turnover_krw=turnover, valid_daily_bar=valid)
            p = self.eod / (market + '_official.csv')
            self.csv(p, [row])
            meta['market_file_sha256'][market] = m.sha(p)
        self.json(self.eod / 'krx_v65_collect_status.json', meta)
        return meta

    def run_gate(self):
        return m.calculate(self.reports, self.basic, self.scope, self.eod, NOW)

    def test_missing_optional_evidence_never_promoted(self):
        rows, meta = self.run_gate()
        self.assertEqual(rows[0]['review_status'], 'EVIDENCE_PENDING')
        self.assertIsNone(rows[0]['actual_source_turnover_krw'])
        self.assertEqual(meta['approved_buy_count'], 0)

    def test_old_basic_is_labelled_old_not_current(self):
        self.basics('2026-10-23')
        rows, _ = self.run_gate()
        self.assertEqual(rows[0]['instrument_review'], 'COMMON_IN_PRIOR_SNAPSHOT')
        self.assertIn('CURRENT_COMMON_SHARE_PROOF_MISSING', rows[0]['blocking_reasons'])

    def test_current_common_does_not_imply_full_approval(self):
        self.basics()
        self.review()
        self.official_eod()
        rows, meta = self.run_gate()
        self.assertEqual(rows[0]['instrument_review'], 'COMMON_IN_CURRENT_SNAPSHOT')
        self.assertFalse(rows[0]['regular_session_certified'])
        self.assertFalse(rows[0]['trade_approved'])
        self.assertEqual(meta['decision'], 'CASH')

    def test_spac_common_share_label_cannot_override_exclusion(self):
        self.basics()
        self.raw.update(name='가상제1호스팩', instrument_type='COMMON_STOCK')
        self.csv(self.reports / 'c3_preliminary.csv', [self.raw])
        self.assertEqual(self.run_gate()[0][0]['instrument_review'], 'EXCLUDE_SPECIAL')

    def test_preexisting_special_exclusion_survives_common_label(self):
        self.basics()
        self.raw['instrument_type'] = 'NON_COMMON_OR_SPECIAL'
        self.csv(self.reports / 'c3_preliminary.csv', [self.raw])
        self.assertEqual(self.run_gate()[0][0]['review_status'], 'EXCLUDE_FROM_C3')

    def test_foreign_common_not_domestic_common(self):
        self.basics(group='외국주권')
        self.assertEqual(self.run_gate()[0][0]['instrument_review'], 'EXCLUDE_NON_DOMESTIC_COMMON')

    def test_preferred_and_reit_excluded(self):
        for group, kind in [('주권', '구형우선주'), ('부동산투자회사', '보통주')]:
            with self.subTest(group=group):
                self.basics(group=group, kind=kind)
                self.assertEqual(self.run_gate()[0][0]['review_status'], 'EXCLUDE_FROM_C3')

    def test_high_raw_score_pharma_still_excluded(self):
        self.basics()
        self.review('EXCLUDE_PHARMA_BIOTECH')
        row = self.run_gate()[0][0]
        self.assertEqual(row['review_status'], 'EXCLUDE_FROM_C3')
        self.assertEqual(row['raw_c3_preliminary_score'], '84')
        self.assertIsNone(row['final_score80'])

    def test_name_bio_alone_does_not_prove_pharma(self):
        self.raw['name'] = '전진바이오팜'
        self.csv(self.reports / 'c3_preliminary.csv', [self.raw])
        self.assertEqual(self.run_gate()[0][0]['business_scope_status'], 'UNREVIEWED_BUSINESS')

    def test_boundary_review_not_false_clear(self):
        self.review('BOUNDARY_REVIEW_REQUIRED')
        row = self.run_gate()[0][0]
        self.assertIn('BUSINESS_SCOPE_REVIEW_REQUIRED', row['blocking_reasons'])
        self.assertEqual(row['review_status'], 'EVIDENCE_PENDING')

    def test_future_review_never_used(self):
        self.review('EXCLUDE_PHARMA_BIOTECH', '2026-10-29T09:00:00+09:00')
        self.assertEqual(self.run_gate()[0][0]['business_scope_status'], 'UNREVIEWED_BUSINESS')

    def test_estimated_turnover_never_becomes_actual(self):
        row = self.run_gate()[0][0]
        self.assertEqual(row['raw_turnover_estimate_krw'], 1000000)
        self.assertIsNone(row['actual_source_turnover_krw'])

    def test_actual_value_separate_and_boolean_cannot_certify_session(self):
        self.official_eod()
        row, meta = self.run_gate()
        self.assertEqual(row[0]['actual_source_turnover_krw'], 987654)
        self.assertEqual(row[0]['raw_turnover_estimate_krw'], 1000000)
        self.assertFalse(row[0]['regular_session_certified'])
        self.assertEqual(meta['actual_turnover_observed_count'], 1)

    def test_stale_eod_not_same_day_turnover(self):
        self.official_eod('2026-10-26')
        rows, meta = self.run_gate()
        self.assertIsNone(rows[0]['actual_source_turnover_krw'])
        self.assertEqual(meta['actual_turnover_source']['status'], 'STALE_NOT_SAME_DAY_TURNOVER')

    def test_zero_invalid_or_nonfinite_actual_does_not_pass(self):
        for value in ('0', 'nan', '-1', ''):
            with self.subTest(value=value):
                self.official_eod(turnover=value)
                row = self.run_gate()[0][0]
                self.assertTrue(row['actual_source_turnover_krw'] in (0, None))
                self.assertFalse(row['trade_approved'])

    def test_invalid_official_bar_not_credited(self):
        self.official_eod(valid='False')
        row = self.run_gate()[0][0]
        self.assertIsNone(row['actual_source_turnover_krw'])
        self.assertEqual(row['actual_turnover_status'], 'OFFICIAL_DAILY_ROW_INVALID')

    def test_basic_hash_change_rejected(self):
        self.basics()
        with (self.basic / 'KOSPI_basic_v610.csv').open('a') as f:
            f.write('\n')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            self.run_gate()

    def test_eod_hash_change_rejected(self):
        self.official_eod()
        with (self.eod / 'KOSPI_official.csv').open('a') as f:
            f.write('\n')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            self.run_gate()

    def test_future_basic_and_eod_rejected(self):
        self.basics('2026-10-28')
        with self.assertRaisesRegex(ValueError, 'FUTURE'):
            self.run_gate()
        self.basics()
        self.official_eod('2026-10-28')
        with self.assertRaisesRegex(ValueError, 'FUTURE'):
            self.run_gate()

    def test_duplicate_and_wrong_date_candidates_rejected(self):
        self.csv(self.reports / 'c3_preliminary.csv', [self.raw, self.raw])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            self.run_gate()
        bad = dict(self.raw, latest_date='2026-10-26')
        self.csv(self.reports / 'c3_preliminary.csv', [bad])
        with self.assertRaisesRegex(ValueError, 'WRONG_DATE'):
            self.run_gate()

    def test_incomplete_scan_and_string_boolean_rejected(self):
        for v in (False, 'True'):
            self.json(self.reports / 'status.json', dict(self.status, scan_complete=v))
            with self.assertRaisesRegex(ValueError, 'INCOMPLETE'):
                self.run_gate()

    def test_no_fake_isin_or_naive_clock(self):
        self.raw['ticker'] = 'KR7011200003'
        self.csv(self.reports / 'c3_preliminary.csv', [self.raw])
        with self.assertRaisesRegex(ValueError, 'NO_ISIN'):
            self.run_gate()
        with self.assertRaisesRegex(ValueError, 'TIMEZONE'):
            m.clock('2026-10-28T07:30:00')

    def test_all_rows_and_raw_prices_preserved_deterministically(self):
        before = {p.name: m.sha(p) for p in self.reports.iterdir()}
        rows, meta = self.run_gate()
        self.assertEqual(rows[0]['raw_close_reference'], 22400)
        self.assertEqual(rows[0]['raw_rank'], 1)
        a, b = self.root / 'a', self.root / 'b'
        m.write_outputs(a, rows, copy.deepcopy(meta))
        m.write_outputs(b, rows, copy.deepcopy(meta))
        for p in a.iterdir():
            self.assertEqual(p.read_bytes(), (b / p.name).read_bytes())
        self.assertEqual(before, {p.name: m.sha(p) for p in self.reports.iterdir()})

    def test_empty_successful_candidate_set_kept_empty(self):
        self.csv(self.reports / 'c3_preliminary.csv', [], list(self.raw))
        rows, meta = self.run_gate()
        self.assertEqual(rows, [])
        self.assertEqual(meta['candidate_rows'], 0)
        self.assertEqual(meta['approved_buy_count'], 0)


if __name__ == '__main__':
    unittest.main()
