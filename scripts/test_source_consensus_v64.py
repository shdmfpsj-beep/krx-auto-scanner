"""v6.4 never mistake second-source agreement for regular session proof."""
from __future__ import annotations
import copy,csv,json,tempfile,unittest
from pathlib import Path
from entry_strategy_v58 import METHODS
from forward_ledger_v63 import canonical,digest,SCHEMA as FREEZE_SCHEMA,PROVENANCE
from source_consensus_v64 import (run,records_from_v18,SCHEMA,mobile)

DAY="2026-10-23"
def write_csv(path,headers,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)

def setup(parent):
    root=Path(parent);recovery=root/"recovery";market=root/"market"/DAY
    frozen=root/"freeze"
    for p in (recovery,market,frozen):p.mkdir(parents=True,exist_ok=True)
    rp=recovery/"status.json"
    rp.write_text(json.dumps(dict(market_data_date=DAY,scan_complete=True,
                                  data_date_verified=True)))
    stocks=[
        ("000001","ALPHA",100,100,110,90,100,1000),
        ("000002","BETA",50,0,0,0,50,0),
        ("000003","GAMMA",80,80,85,75,80,300)]
    hist=[]
    cands=[]
    for t,name,close,op,hi,lo,cl,vol in stocks:
        hist.append(dict(ticker=t,date=DAY,open=op,high=hi,low=lo,close=cl,
                         volume=vol,data_source="pykrx"))
        cands.append(dict(ticker=t,name=name,latest_date=DAY,close=close,
                          instrument_type="UNKNOWN",
                          turnover_source="ESTIMATED_CLOSE_X_VOLUME"))
    hp=recovery/"candidate_daily_history_v52.csv"
    cp=recovery/"candidates.csv"
    write_csv(hp,["ticker","date","open","high","low","close","volume","data_source"],hist)
    write_csv(cp,["ticker","name","latest_date","close","instrument_type","turnover_source"],cands)
    slices={
        "KOSPI":[dict(ticker="000001",Date=DAY,Open=99,High=108,Low=92,Close=95,
                      Volume=1300,TurnoverKRW=122000)],
        "KOSDAQ":[dict(ticker="000002",Date=DAY,Open=50,High=51,Low=49,Close=50,
                       Volume=300,TurnoverKRW=15000),
                  dict(ticker="000003",Date=DAY,Open=80,High=85,Low=75,Close=80,
                       Volume=200,TurnoverKRW=16000)]}
    hashes={}
    for ex,rs in slices.items():
        p=market/(ex+".csv")
        write_csv(p,["ticker","Date","Open","High","Low","Close","Volume",
                     "TurnoverKRW"],rs)
        hashes[ex]=digest(p.read_bytes())
    mp=market/"meta.json"
    mp.write_text(json.dumps(dict(schema="C3_K100_FULLMARKET_DAY_SLICE_V63",
        asof=DAY,regular_only_verified=False,source_run_success=True,
        source_completed_utc="2026-10-23T12:00:00+00:00",
        v18_run_id="39948306433",orders_enabled=False,trade_approved=False,
        market_counts={"KOSPI":1,"KOSDAQ":2},total_covered_tickers=3,
        sha256=hashes)))
    plans=[]
    for variant in ("FIRST","SECOND"):
        plans.append(dict(asof=DAY,ticker="000001",method=METHODS[0],
            variant=variant,signal_close_reference=100,
            trade_approved=False,orders_enabled=False))
    (frozen/"frozen_v63_signals.json").write_text(json.dumps(plans))
    manifest=dict(schema=FREEZE_SCHEMA,version=1,
        freeze_status=PROVENANCE,asof=DAY,freeze_utc="2026-10-25T00:00:00+00:00",
        asof_signal_count=1,frozen_alternative_count=2,
        frozen_payload_sha256=digest(canonical(plans)),
        source_sha256=dict(recovery_status=digest(rp.read_bytes()),
                          recovery_history=digest(hp.read_bytes())),
        source_run_ids=dict(v58_run_id="40095818288",recovery_run_id="39923708922"),
        trade_approved=False,orders_enabled=False)
    (frozen/"frozen_v63_manifest.json").write_text(json.dumps(manifest))
    return recovery,market,frozen

class V64Tests(unittest.TestCase):
    def test_day_audit_quarantines_malformed_and_mismatched_bar(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            report,rows=run(a,b,c)
            self.assertEqual(report["schema"],SCHEMA)
            self.assertEqual(report["candidate_count"],3)
            self.assertEqual(report["valid_close_conflicts"],1)
            self.assertEqual(report["valid_close_matches"],1)
            self.assertEqual(report["malformed_recovery_ohlc"],1)
            self.assertEqual(report["frozen_ticker_valid_close_conflicts"],1)
            self.assertEqual([r["classification"] for r in rows],[
                "CLOSE_CONFLICT_SESSION_UNKNOWN",
                "RECOVERY_OHLC_INVALID",
                "CLOSE_AGREED_SESSION_UNCERTIFIED"])
            self.assertEqual(rows[0]["close_difference_pct_of_recovery"],-5)
            self.assertEqual(report["decision"],"CASH")

    def test_matching_source_prices_never_certify_regular_close(self):
        with tempfile.TemporaryDirectory() as work:
            report,rows=run(*setup(work))
            self.assertFalse(report["kst_regular_session_0900_1530_independently_certified"])
            self.assertTrue(report["cross_source_agreement_does_not_prove_independent_regular_feed"])
            self.assertFalse(rows[2]["independent_regular_close_certified"])
            self.assertFalse(rows[2]["eligible_for_80point_score"])
            self.assertTrue(all(r["trade_approved"] is False for r in rows))
            self.assertTrue(all(r["orders_enabled"] is False for r in rows))
            self.assertIn("정규장 인증이 아닙니다",mobile(report))

    def test_tampered_market_csv_is_fatal(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            (b/"KOSPI.csv").write_text("CORRUPTED",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"V18_DAILY_SOURCE_SHA256_MISMATCH"):
                run(a,b,c)

    def test_tampered_recovery_full_history_is_fatal(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            with (a/"candidate_daily_history_v52.csv").open("a") as f:
                f.write("\n")
            with self.assertRaisesRegex(ValueError,"RECOVERY_DATED_HASH"):
                run(a,b,c)

    def test_frozen_snapshot_close_must_equal_recovery(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            p=c/"frozen_v63_signals.json"
            rows=json.loads(p.read_text())
            for r in rows:r["signal_close_reference"]=101
            p.write_text(json.dumps(rows))
            m=c/"frozen_v63_manifest.json"
            j=json.loads(m.read_text())
            j["frozen_payload_sha256"]=digest(canonical(rows))
            m.write_text(json.dumps(j))
            with self.assertRaisesRegex(ValueError,"FROZEN_ASOF_CLOSE_DIFFERS"):
                run(a,b,c)

    def test_duplicate_market_issue_detected_even_if_shas_recomputed(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            p=b/"KOSDAQ.csv"
            csv_rows=list(csv.DictReader(p.open(encoding="utf-8-sig")))
            csv_rows[1]["ticker"]="000002"
            write_csv(p,list(csv_rows[0]),csv_rows)
            m=b/"meta.json";meta=json.loads(m.read_text())
            meta["sha256"]["KOSDAQ"]=digest(p.read_bytes())
            m.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"V18_TICKER_DUPLICATED"):
                run(a,b,c)

    def test_wrong_v18_day_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            m=b/"meta.json";meta=json.loads(m.read_text())
            meta["asof"]="2026-10-22";m.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"V18_MARKET_ASOF"):
                run(a,b,c)

    def test_frozen_variant_pair_cannot_be_missing(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            p=c/"frozen_v63_signals.json"
            rr=json.loads(p.read_text())
            rr[1]["variant"]="FIRST"
            p.write_text(json.dumps(rr))
            m=c/"frozen_v63_manifest.json";data=json.loads(m.read_text())
            data["frozen_payload_sha256"]=digest(canonical(rr));m.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"SNAPSHOT_UNSAFE_OR_DUPLICATE_PLAN"):
                run(a,b,c)

    def test_foreign_mixed_six_char_security_retained(self):
        with tempfile.TemporaryDirectory() as work:
            a,b,c=setup(work)
            p=b/"KOSDAQ.csv"
            vals=list(csv.DictReader(p.open(encoding="utf-8-sig")))
            vals[1]["ticker"]="00104K"
            write_csv(p,list(vals[0]),vals)
            m=b/"meta.json";j=json.loads(m.read_text());j["sha256"]["KOSDAQ"]=digest(p.read_bytes());m.write_text(json.dumps(j))
            report,records=run(a,b,c)
            self.assertEqual(report["market_universe_size"],3)
            self.assertEqual(report["candidate_count"],3)
            self.assertEqual(records[2]["classification"],"NO_V18_MARKET_ROW")

if __name__=="__main__":unittest.main()
