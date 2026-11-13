"""Offline guard tests: Nov13 only, no fictitious certification."""
import hashlib
import unittest
from datetime import datetime
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import json
import sys
import csv
import io
from types import SimpleNamespace

from c3_morning_source_v1 import normalized_hash
from c3_nov13_once_v1 import check_snapshot, check_trigger, prepare_manual, TARGET

NOW = datetime.fromisoformat("2026-11-13T22:30:00+09:00")


def event():
    return {
        "repository": {"full_name": "shdmfpsj-beep/krx-auto-scanner"},
        "workflow_run": {
            "id": 123456, "name": "C3 post-close price prefetch (RESEARCH / NO SEND)",
            "event": "schedule", "status": "completed", "conclusion": "success",
            "head_sha": "a" * 40, "head_branch": "main",
            "head_repository": {"full_name": "shdmfpsj-beep/krx-auto-scanner"},
        },
    }


def receipt():
    return {"event": "schedule", "trusted": True,
            "cron": "20 12 * * 1-5", "source_sha": "a" * 40}


def dataset():
    rows = [
        {"ticker": f"{n:06d}", "name": f"STOCK{n}", "market": "KOSPI" if n < 1100 else "KOSDAQ",
         "asof": TARGET, "open": 100., "high": 110., "low": 90.,
         "close": 101., "volume": 1000., "turnover_krw": 101000.}
        for n in range(2100)
    ]
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=['Code','Name','MarketId','Open','High','Low','Close','Volume','Amount']);writer.writeheader()
    for r in rows:
        writer.writerow(dict(Code=r['ticker'],Name=r['name'],MarketId='STK' if r['market']=='KOSPI' else 'KSQ',Open=r['open'],High=r['high'],Low=r['low'],Close=r['close'],Volume=r['volume'],Amount=r['turnover_krw']))
    raw = stream.getvalue().encode()
    digest = normalized_hash(rows)
    p = {"status": "PREFETCHED_RESEARCH_ONLY", "asof": TARGET,
         "provider": "FDR_DATED_CSV", "regular_only_certified": False,
         "buy_approved": False, "publication": {"status": "ARCHIVED"},
         "rows": 2100, "normalized_rows_sha256": digest,
         "raw_sha256": hashlib.sha256(raw).hexdigest(),
         "file_commit_at": "2026-11-13T13:10:00Z",
         "collected_at": "2026-11-13T13:15:00Z"}
    return p, {"asof": TARGET, "rows": rows, "normalized_rows_sha256": digest}, raw


class TonightTests(unittest.TestCase):
    def test_watch_output_retains_quality_rank_even_when_a_name_is_also_entry_fit(self):
        from c3_watch_card_v1 import watch_rows
        pool=[dict(ticker='000001',name='FIRST',close=100),dict(ticker='000002',name='SECOND',close=200)]
        result=watch_rows(pool,[pool[0]])
        self.assertEqual([r['ticker'] for r in result],['000001','000002'])
        self.assertEqual([r['rank'] for r in result],[1,2]);self.assertTrue(result[0]['entry_fit_selected'])
        self.assertIsNone(result[0]['score']);self.assertFalse(result[0]['buy_approved'])
    def test_both_real_research_jobs_receive_existing_readonly_financial_key(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/c3_nov13_once.yml').read_text()
        for name in ('one-night-research','manual-retrospective-research'):
            block=text.split('\n  '+name+':',1)[1].split('\n  manual-retrospective-research:',1)[0]
            self.assertIn('OPENDART_API_KEY: ${{ secrets.OPENDART_API_KEY }}',block)

    def test_trusted_2120_and_2310(self):
        self.assertEqual(check_trigger(event(), receipt(), NOW), 123456)
        r = receipt(); r["cron"] = "10 14 * * 1-5"
        self.assertEqual(check_trigger(event(), r, NOW), 123456)

    def test_no_other_day_or_recurring_execution(self):
        for time in ("2026-11-13T20:59:59+09:00", "2026-11-14T08:00:00+09:00",
                     "2026-11-20T22:00:00+09:00"):
            with self.assertRaisesRegex(ValueError, "ONE_NIGHT_WINDOW_CLOSED"):
                check_trigger(event(), receipt(), datetime.fromisoformat(time))

    def test_no_dawn_or_manual_approval(self):
        r = receipt(); r["cron"] = "10 22 * * 1-5"
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_OR_OUT_OF_WINDOW_CRON"):
            check_trigger(event(), r, NOW)
        e = event(); e["workflow_run"]["event"] = "workflow_dispatch"
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_NIGHT_SOURCE_COMPLETION"):
            check_trigger(e, receipt(), NOW)

    def test_no_fork_or_foreign_repo(self):
        e = event(); e["workflow_run"]["head_repository"]["full_name"] = "attacker/repo"
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_NIGHT_SOURCE_COMPLETION"):
            check_trigger(e, receipt(), NOW)

    def test_manual_dispatch_rejects_untrusted_context(self):
        with TemporaryDirectory() as d:
            with patch.dict("os.environ", {"GITHUB_EVENT_NAME":"push", "GITHUB_REPOSITORY":"shdmfpsj-beep/krx-auto-scanner", "GITHUB_REF":"refs/heads/main", "GITHUB_WORKFLOW":"C3 Nov13 one-night full-market research (NO ORDER / NO SEND)"}):
                with self.assertRaisesRegex(ValueError, "UNTRUSTED_MANUAL_DISPATCH"):
                    prepare_manual(Path(d)/"source", Path(d)/"out", NOW)

    def test_manual_dispatch_validates_snapshot_and_records_lookahead(self):
        with TemporaryDirectory() as d:
            root=Path(d);src=root/"source";src.mkdir()
            p,m,raw=dataset();p["price_basis"]="UNADJUSTED_AS_REPORTED_FDR";p["file_commit"]="a"*40
            (src/"prefetch.json").write_text(json.dumps(p))
            (src/"normalized_market.json").write_text(json.dumps(m))
            (src/"original.csv").write_bytes(raw)
            env={"GITHUB_EVENT_NAME":"workflow_dispatch","GITHUB_REPOSITORY":"shdmfpsj-beep/krx-auto-scanner","GITHUB_REF":"refs/heads/main","GITHUB_WORKFLOW":"C3 Nov13 one-night full-market research (NO ORDER / NO SEND)","GITHUB_RUN_ID":"98765"}
            with patch.dict("os.environ",env), patch("c3_nov13_once_v1.validate"), patch("c3_nov13_once_v1.session_context",return_value={"reference_close_at":"2026-11-13T06:30:00Z"}), patch.dict(sys.modules,{"c3_daily_research_v8":SimpleNamespace(collect_indices=lambda *a: {"series":{"KOSPI":{"end":TARGET},"KOSDAQ":{"end":TARGET}}})}):
                result=prepare_manual(src,root/"out",NOW)
            self.assertEqual(result["rows"],2100)
            self.assertTrue(result["lookahead_relative_to_target_close"])
            self.assertFalse(result["official_krx_match_verified"])
            self.assertFalse(result["buy_approved"])

    @patch("c3_nov13_once_v1.validate")
    @patch("c3_nov13_once_v1.session_context")
    def test_snapshot_hash_and_date(self, context, validate):
        context.return_value = {"reference_close_at": "2026-11-13T06:30:00Z"}
        p, m, raw = dataset()
        self.assertEqual(len(check_snapshot(p, m, raw, NOW)), 2100)
        validate.assert_called_once()

    @patch("c3_nov13_once_v1.validate")
    @patch("c3_nov13_once_v1.session_context")
    def test_rejects_changed_price_and_unverified_publication(self, context, validate):
        context.return_value = {"reference_close_at": "2026-11-13T06:30:00Z"}
        p, m, raw = dataset()
        m["rows"][0]["close"] = 99.
        with self.assertRaisesRegex(ValueError, "NIGHT_ARCHIVE_HASH_OR_ROW_CONFLICT"):
            check_snapshot(p, m, raw, NOW)
        p, m, raw = dataset()
        p["publication"]["status"] = "NOT_ARCHIVED"
        with self.assertRaisesRegex(ValueError, "POST_CLOSE_ARCHIVE_NOT_PUBLISHED"):
            check_snapshot(p, m, raw, NOW)

    @patch("c3_nov13_once_v1.validate")
    @patch("c3_nov13_once_v1.session_context")
    def test_rejects_preclose_file(self, context, validate):
        context.return_value = {"reference_close_at": "2026-11-13T06:30:00Z"}
        p, m, raw = dataset()
        p["file_commit_at"] = "2026-11-13T06:00:00Z"
        with self.assertRaisesRegex(ValueError, "NIGHT_FILE_BEFORE_REFERENCE_CLOSE"):
            check_snapshot(p, m, raw, NOW)

    @patch('c3_nov13_once_v1.session_context',return_value={'reference_close_at':'2026-11-13T06:30:00Z'})
    def test_csv_and_normalized_prices_must_agree_even_if_separate_hashes_are_rewritten(self, context):
        p,m,raw=dataset();raw=raw.replace(b'101.0',b'102.0',1);p['raw_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'FIELD_MISMATCH'):check_snapshot(p,m,raw,NOW)


if __name__ == "__main__":
    unittest.main()
