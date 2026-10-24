"""v6.3 no-profit-until-observed, hashed snapshot and provenance tests."""
from __future__ import annotations
import copy,csv,json,tempfile,unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

from forward_ledger_v63 import (
    SCHEMA,PROVENANCE,canonical,digest,freeze,verify_snapshot,
    load_daily,evaluate,save,parse_utc,parse_date)
from entry_strategy_v58 import METHODS

ASOF="2026-10-23"
FROZEN="2026-10-25T00:00:00+00:00"
TICKER="005930"

def fixture():
    signals=[]
    for v,entry in (("FIRST",100.0),("SECOND",94.0)):
        signals.append(dict(asof=ASOF,ticker=TICKER,name="TEST",
            method=METHODS[2],variant=v,
            research_entry_reference=entry,daily_structure_stop_reference=90.,
            nearest_target_repriced_reference=120.,
            signal_close_reference=110.,
            geometry_gate_pass=False,trade_approved=False,orders_enabled=False,
            source_blockers=[],stock_exclusion_reasons=[],result_status="PENDING_FUTURE_SESSIONS"))
    m=dict(schema=SCHEMA,version=1,asof=ASOF,freeze_utc=FROZEN,
        freeze_status=PROVENANCE,asof_signal_count=1,
        frozen_alternative_count=2,frozen_payload_sha256=digest(canonical(signals)),
        trade_approved=False,orders_enabled=False)
    return m,signals

def market_day(parent,day,offset=0,completed="2026-11-03T12:00:00+00:00",
               k_open=110.,k_high=112.,k_low=105.,k_close=108.):
    root=Path(parent)/day
    root.mkdir(parents=True)
    hashes={}
    for market,ticker in (("KOSPI",TICKER),("KOSDAQ","123456")):
        f=root/(market+".csv")
        with f.open("w",encoding="utf-8-sig",newline="") as w:
            writer=csv.DictWriter(w,fieldnames=["ticker","Date","Open",
                "High","Low","Close","Volume","TurnoverKRW"])
            writer.writeheader()
            writer.writerow(dict(ticker=ticker,Date=day,Open=k_open,
                High=k_high,Low=k_low,Close=k_close,Volume=1000,
                TurnoverKRW=100000))
        hashes[market]=digest(f.read_bytes())
    (root/"meta.json").write_text(json.dumps(dict(asof=day,
        v18_run_id=str(90000000+offset),
        source_completed_utc=completed,source_run_success=True,
        regular_only_verified=False,sha256=hashes)),encoding="utf-8")
    return root

class ForwardV63Tests(unittest.TestCase):
    def test_frozen_sha256_immutable_and_two_options_not_two_positions(self):
        m,s=fixture()
        self.assertEqual(verify_snapshot(m,s)[0],date(2026,10,23))
        corrupted=copy.deepcopy(s);corrupted[1]["research_entry_reference"]=95
        with self.assertRaisesRegex(ValueError,"IMMUTABLE_SNAPSHOT_HASH"):
            verify_snapshot(m,corrupted)
        self.assertFalse(any(x["trade_approved"] for x in s))

    def test_freeze_before_market_day_or_unzoned_time_fails(self):
        with self.assertRaisesRegex(ValueError,"UTC_TIMESTAMP"):
            parse_utc("2026-10-25T12:00:00")
        self.assertEqual(parse_date(ASOF).isoformat(),ASOF)
        with self.assertRaisesRegex(ValueError,"INVALID_MARKET_DATE"):
            parse_date("2026-10-55")

    def test_without_future_evidence_is_pending_not_zero_percent_loss(self):
        m,s=fixture()
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)/"empty"
            report,out=evaluate(m,s,root)
            self.assertEqual(report["status"],"WAITING_FOR_NEW_DAILY_SOURCES")
            self.assertEqual(report["pending_count"],2)
            self.assertEqual(report["provisional_filled_scenarios"],0)
            self.assertEqual(report["officially_verified_forward_trade_count"],0)
            self.assertTrue(all(x["net_return_pct"] is None for x in out))
            self.assertEqual(report["decision"],"CASH")

    def test_one_future_session_is_not_five_day_outcome(self):
        m,s=fixture()
        with tempfile.TemporaryDirectory() as temp:
            market_day(temp,"2026-10-26")
            report,out=evaluate(m,s,temp)
            self.assertEqual(report["observed_future_distinct_market_dates"],["2026-10-26"])
            self.assertEqual(report["pending_count"],2)
            self.assertFalse(any(x["net_return_pct"] is not None for x in out))

    def test_synthetic_seven_complete_days_are_only_provisional(self):
        m,s=fixture()
        with tempfile.TemporaryDirectory() as temp:
            dates=["2026-10-26","2026-10-27","2026-10-28","2026-10-29",
                   "2026-10-30","2026-11-02","2026-11-03"]
            for i,d in enumerate(dates):
                market_day(temp,d,i,k_low=(99 if i==0 else 104),
                    k_high=121 if i==2 else 112)
            report,out=evaluate(m,s,temp)
            self.assertEqual(report["status"],"PROVISIONAL_NONCERTIFIED_SEVEN_SESSIONS")
            self.assertEqual(report["observed_full_market_snapshot_days"],7)
            self.assertTrue(any(x["result_status"].startswith("PROVISIONAL_") for x in out))
            self.assertEqual(report["officially_verified_forward_trade_count"],0)
            self.assertFalse(report["forward_calendar_complete_officially_verified"])
            self.assertFalse(report["trade_approved"])
            self.assertFalse(report["orders_enabled"])

    def test_stale_or_past_market_source_never_sneaks_into_follow_up(self):
        m,s=fixture()
        with tempfile.TemporaryDirectory() as temp:
            market_day(temp,ASOF)
            with self.assertRaisesRegex(ValueError,"SAME_OR_PAST_DAY"):
                evaluate(m,s,temp)
        with tempfile.TemporaryDirectory() as temp:
            market_day(temp,"2026-10-26",
                completed="2026-10-24T00:00:00+00:00")
            with self.assertRaisesRegex(ValueError,"SOURCE_NOT_FROZEN_FIRST"):
                evaluate(m,s,temp)

    def test_mismatched_csv_digest_refused(self):
        m,s=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=market_day(temp,"2026-10-26")
            (root/"KOSPI.csv").write_text("corruption",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"SHA256_MISMATCH"):
                evaluate(m,s,temp)

    def test_missing_market_or_duplicate_ticker_refused(self):
        m,s=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=market_day(temp,"2026-10-26")
            (root/"KOSDAQ.csv").unlink()
            with self.assertRaisesRegex(ValueError,"SHA256_MISMATCH"):
                evaluate(m,s,temp)
        with tempfile.TemporaryDirectory() as temp:
            root=market_day(temp,"2026-10-26")
            f=root/"KOSDAQ.csv"
            txt=f.read_text(encoding="utf-8-sig")
            f.write_text(txt.replace("123456",TICKER),encoding="utf-8-sig")
            meta=json.loads((root/"meta.json").read_text())
            meta["sha256"]["KOSDAQ"]=digest(f.read_bytes())
            (root/"meta.json").write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"DUPLICATE_STOCK"):
                evaluate(m,s,temp)

    def test_freeze_rejects_an_unverified_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);v=root/"v58";r=root/"recovery"
            v.mkdir();r.mkdir()
            (v/"entry_strategy_v58_status.json").write_text(json.dumps(dict(
                schema="C3_K100_FREE_ENTRY_V58",asof=ASOF,
                evaluated_method_rows=0,candidates=0,source_errors=["BAD"],
                trade_approved=False,orders_enabled=False,
                regular_only_session_certified=False)))
            (v/"entry_strategy_v58_all.csv").write_text("asof,ticker\n")
            (r/"status.json").write_text(json.dumps(dict(
                market_data_date=ASOF,scan_complete=True,
                data_date_verified=True)))
            (r/"candidate_daily_history_v52.csv").write_text("ticker,date\n")
            with self.assertRaisesRegex(ValueError,"V58_RECOVERY_DATED_COMPLETENESS_FAILED"):
                freeze(v,r,{"v58_run_id":"12345678",
                            "recovery_run_id":"87654321"},FROZEN)

    def test_complete_snapshot_preserves_invalid_alternative_price(self):
        m,s=fixture()
        s[1]["research_entry_reference"]=None
        m["frozen_payload_sha256"]=digest(canonical(s))
        with tempfile.TemporaryDirectory() as tmp:
            report,out=evaluate(m,s,Path(tmp)/"not-present")
            self.assertEqual(out[1]["result_status"],"REFERENCE_INVALID_NO_ORDER")
            self.assertEqual(report["pending_count"],1)
            self.assertEqual(report["decision"],"CASH")

    def test_saved_report_has_empty_roi_and_correct_signals(self):
        m,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/"out"
            save(dst,m,s)
            m2=json.loads((dst/"frozen_v63_manifest.json").read_text())
            signal=json.loads((dst/"frozen_v63_signals.json").read_text())
            self.assertEqual(m2["frozen_payload_sha256"],digest(canonical(signal)))
            report,out=evaluate(m2,signal,Path(tmp)/"none")
            save(dst,out,report=report)
            rr=list(csv.DictReader((dst/"forward_v63_all.csv").open(encoding="utf-8-sig")))
            self.assertEqual(len(rr),2)
            self.assertEqual(rr[0]["net_return_pct"],"")
            self.assertEqual(rr[0]["trade_approved"],"False")

if __name__=="__main__":unittest.main()
