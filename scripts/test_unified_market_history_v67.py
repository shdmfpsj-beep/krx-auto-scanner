"""v6.7 tests: all 120 bars same market endpoint, no partial repairs or BUY."""
from __future__ import annotations
import csv,json,tempfile,unittest
from pathlib import Path
from test_recovery_price_rootcause_v66 import fixture,write,ASOF,CODE
from unified_market_history_v67 import (
    SCHEMA,analyze,market_history,mobile)

def setup(tmp):
    q=fixture(tmp)
    p=q["v18"]=Path(tmp)/"v18"
    (p/"diagnostics").mkdir(parents=True)
    (p/"diagnostics/collection_status.json").write_text(
        json.dumps(dict(asof=str(ASOF),orders_enabled=False,
            datasets=dict(prices=dict(status="OK")))))
    target=p/"market/prices"/(CODE+".csv")
    old=list(csv.DictReader((q["recovery"]/"candidate_daily_history_v52.csv").open(
        encoding="utf-8-sig")))
    uniform=[dict(Date=x["date"],Open=x["open"],High=x["high"],
        Low=x["low"],Close=x["close"],Volume=x["volume"],TurnoverKRW=100000)
        for x in old]
    uniform[-1].update(Open="100",High="112",Low="90",Close="105",Volume="1100")
    write(target,["Date","Open","High","Low","Close","Volume","TurnoverKRW"],uniform)
    return q,target

def analyze_fixture(q):
    return analyze(*(q[key] for key in (
        "recovery","v58","freeze","v18","official")))

class UnifiedMarketV67Tests(unittest.TestCase):
    def test_full_120_bar_reconstruction_matches_original_setup_when_only_last_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,_=setup(tmp)
            report,rows=analyze_fixture(q)
            self.assertEqual(report["schema"],SCHEMA)
            self.assertEqual(report["selected_recovery_tickers"],1)
            self.assertEqual(report["analysis_method_rows"],3)
            self.assertEqual(report["full_120_session_valid_stock_count"],1)
            self.assertEqual(report["historic_daily_ohlcv_mismatched_rows"],
              dict(open=0,high=1,low=0,close=1,volume=1))
            self.assertEqual(report["tickers_with_any_120day_field_difference"],1)
            self.assertTrue(report["old_method_replay_matches_archive"])
            self.assertEqual(report["decision"],"CASH")
            self.assertTrue(all(x["trade_approved"] is False for x in rows))
            self.assertTrue(all(x["official_120day_history_authenticated"] is False
                                for x in rows))
            self.assertIn("120일",mobile(report))

    def test_prior_year_price_disagreement_is_counted_not_erased(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            rows=list(csv.DictReader(file.open(encoding="utf-8-sig")))
            rows[50]["Close"]="101"
            write(file,list(rows[0]),rows)
            report,_=analyze_fixture(q)
            self.assertEqual(report["historic_daily_ohlcv_mismatched_rows"]["close"],2)

    def test_bad_historic_market_ohlc_kept_pending_not_fake_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            rows=list(csv.DictReader(file.open(encoding="utf-8-sig")))
            rows[33]["High"]="0"
            write(file,list(rows[0]),rows)
            report,data=analyze_fixture(q)
            self.assertEqual(report["full_120_session_invalid_stock_count"],1)
            self.assertEqual(report["single_source_uniform_trigger_count"],0)
            self.assertTrue(all(x["uniform_120bar_geometry_usable"] is False for x in data))
            self.assertEqual(report["decision"],"CASH")

    def test_missing_old_market_session_blocked_not_silent_short_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            rows=list(csv.DictReader(file.open(encoding="utf-8-sig")))
            write(file,list(rows[0]),rows[:-3])
            with self.assertRaisesRegex(ValueError,"TOTAL_CANDIDATE_MARKET_HISTORY_DATA_MISSING"):
                analyze_fixture(q)

    def test_official_api_final_candle_disagreement_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            rows=list(csv.DictReader(file.open(encoding="utf-8-sig")))
            rows[-1]["Close"]="108"
            write(file,list(rows[0]),rows)
            with self.assertRaisesRegex(ValueError,"LATEST_MARKET_WIDE_BAR_NOT_OFFICIAL"):
                analyze_fixture(q)

    def test_duplicate_market_date_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            rows=list(csv.DictReader(file.open(encoding="utf-8-sig")))
            rows[-2]["Date"]=rows[-1]["Date"]
            write(file,list(rows[0]),rows)
            with self.assertRaisesRegex(ValueError,"UNIFORM_HISTORY_DUPLICATED_DATE"):
                analyze_fixture(q)

    def test_market_data_date_cannot_be_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            rows=list(csv.DictReader(file.open(encoding="utf-8-sig")))
            rows[-2]["Date"]="2026-10-26"
            write(file,list(rows[0]),rows)
            with self.assertRaisesRegex(ValueError,"MARKET_WIDE_CONTAINS_FUTURE_DATE"):
                analyze_fixture(q)

    def test_source_can_never_claim_1530_certification_from_official_eod(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            m=q["official"]/"krx_v65_collect_status.json"
            status=json.loads(m.read_text());status["independent_1530_regular_session_certified"]=True
            m.write_text(json.dumps(status))
            with self.assertRaisesRegex(ValueError,"IMMUTABLE_DATED_MARKET_SOURCE"):
                analyze_fixture(q)

    def test_frozen_price_tamper_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            q,file=setup(tmp)
            p=q["freeze"]/"frozen_v63_manifest.json"
            m=json.loads(p.read_text());m["frozen_payload_sha256"]="WRONG"
            p.write_text(json.dumps(m))
            with self.assertRaises(ValueError):analyze_fixture(q)

if __name__=="__main__":unittest.main()
