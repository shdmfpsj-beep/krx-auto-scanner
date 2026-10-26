import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pandas as pd
import c3_protocol_v638 as p
from c3_research_v637 import sha


class FrozenProtocolTests(unittest.TestCase):
    def fixture(self,root,rows=None):
        root=Path(root);proto=root/'protocol.json';p.create_protocol(proto)
        frame=pd.DataFrame(rows or [],columns=['asof','ticker','pattern','market_trend','LEGACY_D_SCORE','STRUCTURE_D_SCORE'])
        file=root/'D_only_full_market_candidates.csv';frame.to_csv(file,index=False)
        (root/'output_sha256.json').write_text(json.dumps({file.name:sha(file)}))
        (root/'research_status.json').write_text(json.dumps(dict(last='2026-10-23',source_archive_sha256='a'*64)))
        return proto
    def test_protocol_retry_keeps_original_registration_time(self):
        with tempfile.TemporaryDirectory() as root:
            a=p.create_protocol(Path(root)/'p.json');b=p.create_protocol(Path(root)/'p.json')
            self.assertEqual(a,b)
    def test_historical_capture_not_labelled_new_verified(self):
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root);r=p.capture(root,proto,'2026-10-23',Path(root)/'freeze.json')['record']
            self.assertEqual(r['evidence_layer'],'REPEATED_HISTORICAL')
            self.assertFalse(r['independent_verified_future_sample'])
    def test_zero_candidates_is_cash_not_previous_ticker_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root);r=p.capture(root,proto,'2026-10-23',Path(root)/'freeze.json')['record']
            self.assertTrue(all(h['paper_order'] is None for h in r['hypotheses']))
            self.assertEqual(r['production_decision'],'CASH')
    def test_capture_idempotent_timestamp(self):
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root);path=Path(root)/'freeze.json'
            self.assertEqual(p.capture(root,proto,'2026-10-23',path),p.capture(root,proto,'2026-10-23',path))
    def test_capture_rejects_tampered_candidate_file(self):
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root)
            with (Path(root)/'D_only_full_market_candidates.csv').open('a') as w:w.write('tampered')
            with self.assertRaises(ValueError):p.capture(root,proto,'2026-10-23',Path(root)/'f.json')
    def test_asof_must_match_completed_source_status(self):
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root)
            with self.assertRaises(ValueError):p.capture(root,proto,'2026-10-26',Path(root)/'f.json')
    def test_no_orders_or_score80_is_inferred_from_registration(self):
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root);r=p.capture(root,proto,'2026-10-23',Path(root)/'f.json')['record']
            self.assertFalse(r['orders_enabled']);self.assertFalse(r['trade_approved'])
            self.assertFalse(r['final_score80_and_independent_resistance2R_verified'])
    def test_changed_source_code_cannot_silently_reuse_protocol(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root)
            with patch.object(p,'implementation_hashes',return_value={'changed':'bad'}):
                with self.assertRaises(ValueError):p.capture(root,proto,'2026-10-23',Path(root)/'f.json')
    def test_full_exit_and_entry_parameters_are_frozen(self):
        with tempfile.TemporaryDirectory() as root:
            proto=self.fixture(root);data=json.loads(proto.read_text())
            self.assertEqual(data['hypotheses'][0]['full_policy']['retest_atr'],.25)
            self.assertEqual(data['hypotheses'][0]['full_policy']['fixed_exit_sessions'],5)


if __name__=='__main__':unittest.main()
