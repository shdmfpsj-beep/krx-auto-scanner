import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from c3_krx_asof_issue_type_audit import parse_category,fetch,audit

class IssueTypeTests(unittest.TestCase):
 def test_future_listing_blocked(self):
  r=parse_category({'LIST_DD':'2026/08/04','KIND_STKCERT_TP_NM':'보통주'},'2026-08-03')
  self.assertEqual(r['status'],'BLOCKED_LISTING_DATE_AFTER_SIGNAL')
 def test_common_and_preferred_not_guessed(self):
  c=parse_category({'LIST_DD':'2020/01/03','KIND_STKCERT_TP_NM':'보통주'},'2026-08-03')
  p=parse_category({'LIST_DD':'2020/01/03','KIND_STKCERT_TP_NM':'우선주'},'2026-08-03')
  self.assertTrue(c['common_share_reported'])
  self.assertTrue(p['preferred_share_reported'])
  self.assertFalse(p['common_share_reported'])
 def test_unknown_class_never_common(self):
  r=parse_category({'LIST_DD':'2020/01/03','KIND_STKCERT_TP_NM':''},'2026-08-03')
  self.assertFalse(r['common_share_reported'])
  self.assertTrue(r['status'].startswith('DATED_METADATA_REPORTED'))
 def test_missing_approval_fails_closed(self):
  r=fetch('2026-11-10','KOSDAQ',None)
  self.assertEqual(r['status'],'BLOCKED_NO_AUTH')
 def test_no_events_is_no_live_authorization(self):
  with tempfile.TemporaryDirectory() as d:
   r=audit([],Path(d),None,sleep_seconds=0)
  self.assertEqual(r['event_count'],0)
  self.assertFalse(r['trade_approved'])
  self.assertEqual(r['decision'],'CASH')

if __name__=='__main__':unittest.main()
