import unittest,tempfile,json,csv
from pathlib import Path
from datetime import datetime,timezone,timedelta
from record_screening_times_v1 import record

NOW=datetime(2026,10,27,12,15,tzinfo=timezone.utc)

class ScreeningTimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
        self.status=dict(scan_complete=True,data_date_verified=True,market_data_date='2026-10-27',
            run_kst='2026-10-27T20:20:00+09:00',source_session_scope_certified=False)
        self.write_status()
        for name in ['candidates.csv','c3_preliminary.csv']:
            (self.p/name).write_text('ticker,name,latest_date,close_reference\n011200,HMM,2026-10-27,22400\n',encoding='utf-8')
    def tearDown(self):self.tmp.cleanup()
    def write_status(self):(self.p/'status.json').write_text(json.dumps(self.status))
    def test_actual_recording_clock_is_distinct_from_data_date_and_collection_start(self):
        r=record(self.p,1,1,'abc',NOW);v=r['issuers']['011200']
        self.assertEqual(v['first_recorded_at_kst'],'2026-10-27T21:15:00+09:00')
        e=json.loads((self.p/'screening_observations_v1.jsonl').read_text())
        self.assertEqual(e['collection_started_at_kst'],'2026-10-27T20:20:00+09:00')
        self.assertTrue(e['earlier_discovery_time_unverified']);self.assertFalse(e['trade_approved'])
    def test_first_record_is_preserved_when_later_scan_registers_same_issuer(self):
        record(self.p,1,1,'abc',NOW);r=record(self.p,2,1,'abc',NOW+timedelta(hours=1))
        v=r['issuers']['011200'];self.assertNotEqual(v['first_recorded_at_kst'],v['latest_recorded_at_kst'])
        self.assertEqual(v['first_recorded_at_kst'],'2026-10-27T21:15:00+09:00')
    def test_same_attempt_retry_is_idempotent_and_does_not_retime_history(self):
        record(self.p,1,1,'abc',NOW);before=(self.p/'screening_observations_v1.jsonl').read_bytes()
        r=record(self.p,1,1,'abc',NOW+timedelta(hours=1))
        self.assertEqual(r['new_observations'],0);self.assertEqual(before,(self.p/'screening_observations_v1.jsonl').read_bytes())
    def test_same_attempt_conflict_is_not_silently_overwritten(self):
        record(self.p,1,1,'abc',NOW);p=self.p/'candidates.csv';p.write_text(p.read_text().replace('22400','22500'))
        before=(self.p/'screening_observations_v1.jsonl').read_bytes()
        with self.assertRaises(ValueError):record(self.p,1,1,'abc',NOW+timedelta(hours=1))
        self.assertEqual(before,(self.p/'screening_observations_v1.jsonl').read_bytes())
    def test_incomplete_or_old_row_cannot_register_fresh_detection(self):
        self.status['scan_complete']=False;self.write_status()
        with self.assertRaises(ValueError):record(self.p,1,1,'abc',NOW)
        self.status['scan_complete']=True;self.write_status();p=self.p/'candidates.csv';p.write_text(p.read_text().replace('2026-10-27','2026-10-26'))
        with self.assertRaises(ValueError):record(self.p,1,1,'abc',NOW)
    def test_missing_start_stays_unknown_and_clock_requires_timezone(self):
        self.status.pop('run_kst');self.write_status();record(self.p,1,1,'abc',NOW)
        e=json.loads((self.p/'screening_observations_v1.jsonl').read_text());self.assertIsNone(e['collection_started_at_kst'])
        with self.assertRaises(ValueError):record(self.p,2,1,'abc',NOW.replace(tzinfo=None))
    def test_corrupt_history_is_not_discarded(self):
        ledger=self.p/'screening_observations_v1.jsonl';ledger.write_text('broken JSON\n')
        with self.assertRaises(json.JSONDecodeError):record(self.p,1,1,'abc',NOW)
        self.assertEqual(ledger.read_text(),'broken JSON\n')
    def test_inputs_scores_and_prices_are_not_modified(self):
        before={n:(self.p/n).read_bytes() for n in ['candidates.csv','c3_preliminary.csv','status.json']}
        record(self.p,1,1,'abc',NOW)
        for n,b in before.items():self.assertEqual((self.p/n).read_bytes(),b)
    def test_valid_empty_candidate_snapshot_records_zero_without_fake_detections(self):
        for n in ['candidates.csv','c3_preliminary.csv']:
            (self.p/n).write_text('ticker,name,latest_date,close_reference\n')
        r=record(self.p,1,1,'abc',NOW);self.assertEqual(r['new_observations'],0);self.assertEqual(r['issuers'],{})

if __name__=='__main__':unittest.main()
