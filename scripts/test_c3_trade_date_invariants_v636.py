import unittest
from c3_trade_date_invariants_v636 import require_iso,audit_chronology
class TestV636Chronology(unittest.TestCase):
 def test_real_iso(self):self.assertEqual(require_iso('2026-10-26'),'2026-10-26')
 def test_pandas_method_rejected(self):
  with self.assertRaises(ValueError):require_iso('<bound method NDFrame.asof of model=...>')
 def test_invalid_calendar(self):
  with self.assertRaises(ValueError):require_iso('2026-02-30')
 def test_chronological_single_slot(self):
  r=[dict(asof='2026-01-09',exit_date='2026-01-14'),dict(asof='2026-01-02',exit_date='2026-01-08')]
  self.assertEqual(audit_chronology(r)['trades'],2)
 def test_overlap_rejected(self):
  r=[dict(asof='2026-01-02',exit_date='2026-01-09'),dict(asof='2026-01-07',exit_date='2026-01-14')]
  with self.assertRaises(ValueError):audit_chronology(r)
 def test_exit_before_signal_rejected(self):
  with self.assertRaises(ValueError):audit_chronology([dict(asof='2026-01-09',exit_date='2026-01-08')])
 def test_same_day_exit_new_signal_rejected(self):
  r=[dict(asof='2026-01-02',exit_date='2026-01-09'),dict(asof='2026-01-09',exit_date='2026-01-13')]
  with self.assertRaises(ValueError):audit_chronology(r)
 def test_no_orders_even_valid(self):
  r=audit_chronology([dict(asof='2026-01-02',exit_date='2026-01-09')])
  self.assertFalse(r['trade_approved']);self.assertFalse(r['orders_enabled'])
if __name__=='__main__':unittest.main()
