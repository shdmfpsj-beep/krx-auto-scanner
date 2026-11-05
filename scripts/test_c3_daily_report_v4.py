import unittest
import tempfile
import json
import hashlib
from pathlib import Path
from c3_daily_report_v4 import known_by,forward_audit


class DailyReportTests(unittest.TestCase):
    def test_evidence_retrieved_later_cannot_be_backdated(self):
        self.assertFalse(known_by('2026-11-05T03:50:00Z','2026-11-04T23:00:00Z'))
        self.assertTrue(known_by('2026-11-05T03:50:00Z','2026-11-05T04:00:00Z'))

    def test_offsets_use_actual_time_not_lexicographic_date(self):
        self.assertTrue(known_by('2026-11-05T12:50:00+09:00','2026-11-05T04:00:00Z'))

    def test_naive_timestamps_cannot_silently_pass(self):
        with self.assertRaisesRegex(ValueError,'TIMEZONE_REQUIRED'):
            known_by('2026-11-05T12:00:00','2026-11-05T04:00:00Z')

    def test_source_known_time_guard_runs_before_any_ranking(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'latest').mkdir();(p/'basic').mkdir()
            (p/'audit.json').write_text('{}')
            (p/'latest/krx_v65_collect_status.json').write_text(json.dumps(dict(retrieval_utc='2026-11-05T03:50:00Z')))
            (p/'basic/krx_basic_v610_status.json').write_text(json.dumps(dict(received_utc='2026-11-05T00:30:00Z')))
            with self.assertRaisesRegex(ValueError,'SOURCE_NOT_YET_KNOWN'):
                forward_audit(p/'not-used',p/'audit.json',p/'latest',p/'basic',p/'not-used','2026-11-04T23:59:00Z',p/'out')


if __name__=='__main__':unittest.main()
