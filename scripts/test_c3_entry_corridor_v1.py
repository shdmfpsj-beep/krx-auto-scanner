"""Deterministic offline tests for research-only entry corridors."""
import unittest
from c3_entry_corridor_v1 import build_corridors
from practical_entry_quotes_v619 import tick

COMMON = dict(
    asof='2026-10-30', close=10000, atr14=350,
    confirmed_support=9600, structural_stop=9250,
    verified_first_resistance=11800,
    support_confirmed_at='2026-10-28',
    resistance_source='prior_pivot_high')


def build(**changes):
    return build_corridors(**dict(COMMON, **changes))


class TestCorridor(unittest.TestCase):
    def test_research_levels_exclude_buy_and_orders(self):
        x = build()
        self.assertEqual(x['status'], 'WATCH_CORRIDORS_RESEARCH_ONLY')
        self.assertFalse(x['buy_approved'])
        self.assertFalse(x['orders_enabled'])
        self.assertTrue(x['corridors'])
        self.assertEqual(x['reason'], 'REGULAR_SESSION_UNVERIFIED')
        for c in x['corridors']:
            self.assertGreaterEqual(c['first_resistance_net_r_at_high'], 2)
            self.assertLessEqual(c['risk_at_high_pct'], 8)
            self.assertLess(c['stop_krw'], c['low_krw'])
            self.assertLess(c['high_krw'], c['first_resistance_krw'])

    def test_alternative_not_splitting(self):
        x = build()
        self.assertEqual({c['mode'] for c in x['corridors']},
                         {'SUPPORT_RETEST', 'STRENGTH_CONFIRMATION'})
        self.assertTrue(x['alternative_modes_not_split_orders'])

    def test_primary_and_flexible_are_nonoverlapping(self):
        x = build()
        pull = [c for c in x['corridors'] if c['mode'] == 'SUPPORT_RETEST']
        self.assertEqual(len(pull), 2)
        self.assertLess(pull[0]['high_krw'], pull[1]['low_krw'])
        self.assertEqual(pull[0]['tier'], 'PRIMARY_UP_TO_5PCT')
        self.assertEqual(pull[1]['tier'], 'FLEX_UP_TO_8PCT')

    def test_resistance_must_be_overhead(self):
        self.assertEqual(build(verified_first_resistance=10000)['status'],
                         'NO_CORRIDOR')

    def test_distant_stop_not_auto_vetoed_by_old_3pct_rule(self):
        x = build(confirmed_support=9000, structural_stop=8500,
                  close=10000, atr14=700,
                  verified_first_resistance=12500)
        self.assertEqual(x['status'], 'WATCH_CORRIDORS_RESEARCH_ONLY')

    def test_2r_includes_friction(self):
        self.assertEqual(build(verified_first_resistance=10020)['status'],
                         'NO_CORRIDOR')

    def test_future_support_confirmation_is_rejected(self):
        self.assertEqual(build(support_confirmed_at='2026-11-02')['reason'],
                         'UNCONFIRMED_SUPPORT_OR_RESISTANCE_PROVENANCE')

    def test_nan_cannot_become_a_level(self):
        self.assertEqual(build(atr14=float('nan'))['status'],
                         'NO_CORRIDOR')

    def test_regular_data_flag_alone_is_not_buy_approval(self):
        x = build(regular_only_certified=True)
        self.assertFalse(x['buy_approved'])
        self.assertFalse(x['orders_enabled'])

    def test_krx_quote_grid(self):
        x = build(close=21000, atr14=900, confirmed_support=20000,
                  structural_stop=19300, verified_first_resistance=25000)
        for c in x['corridors']:
            self.assertEqual(c['low_krw'] % tick(c['low_krw']), 0)
            self.assertEqual(c['high_krw'] % tick(c['high_krw']), 0)


if __name__ == '__main__':
    unittest.main()
