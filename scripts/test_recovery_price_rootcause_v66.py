"""v6.6: provider-path discrepancy audit, never approve a one-day patch."""
from __future__ import annotations
import csv,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from entry_strategy_v58 import METHODS,evaluate
from forward_ledger_v63 import canonical,digest,SCHEMA as FROZEN,PROVENANCE
from recovery_price_rootcause_v66 import analysis,num,diffpct,class_bar,mobile,SCHEMA
from krx_official_eod_v65 import COLLECT_SCHEMA,SCHEMA as V65,MARKET_FIELDS

ASOF=date(2026,10,23)
CODE="005930"

def write(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def fixture(tmp):
    root=Path(tmp)
    dirs={name:root/name for name in (
        "recovery","freeze","v58","v64","v65","official")}
    for p in dirs.values():p.mkdir(parents=True,exist_ok=True)
    rec,freeze,v58,v64,v65,official=[
        dirs[k] for k in ("recovery","freeze","v58","v64","v65","official")]
    ds=[]
    d=ASOF
    while len(ds)<120:
        if d.weekday()<5:ds.append(d)
        d-=timedelta(days=1)
    ds.reverse()
    bars=[dict(ticker=CODE,date=str(x),open=100,high=105,low=98,
               close=100,volume=1000,data_source="pykrx") for x in ds]
    bars[-1].update(open=100,high=110,low=90,close=100,volume=1000)
    official_price=dict(open=100,high=112,low=90,close=105,
                        volume=1100,turnover_krw=115500)
    rs=rec/"status.json";hs=rec/"candidate_daily_history_v52.csv"
    candidate=dict(ticker=CODE,name="TEST_COMPANY",latest_date=str(ASOF),
                   close=100,instrument_type="UNKNOWN",
                   turnover_source="ESTIMATED_CLOSE_X_VOLUME",data_source="pykrx")
    rs.write_text(json.dumps(dict(market_data_date=str(ASOF),
        scan_complete=True,data_date_verified=True)))
    write(hs,list(bars[0]),bars)
    write(rec/"candidates.csv",list(candidate),[candidate])
    plans=[]
    fm=dict(schema=FROZEN,version=1,asof=str(ASOF),
        freeze_status=PROVENANCE,asof_signal_count=0,
        frozen_alternative_count=0,trade_approved=False,orders_enabled=False,
        freeze_utc="2026-10-25T00:01:00+00:00",
        frozen_payload_sha256=digest(canonical(plans)),
        source_run_ids=dict(recovery_run_id="39923708922",v58_run_id="40095818288"),
        source_sha256=dict(recovery_status=digest(rs.read_bytes()),
                           recovery_history=digest(hs.read_bytes())))
    (freeze/"frozen_v63_manifest.json").write_text(json.dumps(fm))
    (freeze/"frozen_v63_signals.json").write_text(json.dumps(plans))
    os=[]
    for method in METHODS:
        r=evaluate(candidate,bars,ASOF,method,
                   dict(category="OHLC_EXACT_MATCH_UNCERTIFIED",
                        close_equal=False))
        os.append({**r,"blocking_reasons":str(r["blocking_reasons"])})
    write(v58/"entry_strategy_v58_all.csv",list(os[0]),os)
    (v58/"entry_strategy_v58_status.json").write_text(json.dumps(
        dict(asof=str(ASOF),trade_approved=False,orders_enabled=False,
             evaluated_method_rows=3)))
    vr=dict(schema="C3_K100_SOURCE_CONSENSUS_V64",asof=str(ASOF),
        manifest_sha256=fm["frozen_payload_sha256"],
        trade_approved=False,orders_enabled=False,candidate_count=1)
    (v64/"source_consensus_v64_status.json").write_text(json.dumps(vr))
    prev=dict(ticker=CODE,asof=str(ASOF),
        **{"recovery_"+k:bars[-1][k] for k in
           ("open","high","low","close","volume")},
        **{"v18_"+k:official_price[k] for k in
           ("open","high","low","close","volume")})
    write(v64/"source_consensus_v64_all.csv",list(prev),[prev])
    st=dict(schema=V65,asof=str(ASOF),
        official_api_connected=True,candidates_evaluated=1,
        v64_frozen_manifest_sha256=fm["frozen_payload_sha256"],
        official_evidence_classes=dict(OFFICIAL_EOD_EQUALS_V18_ONLY=1))
    (v65/"krx_v65_source_comparison_status.json").write_text(json.dumps(st))
    manifest=dict(schema=COLLECT_SCHEMA,asof=str(ASOF),
         official_dataset_usable=True,
         independent_1530_regular_session_certified=False,
         trade_approved=False,orders_enabled=False,official_market_rows=2,
         retrieval_utc="2026-10-25T03:01:00+00:00",market_file_sha256={})
    for market,t,price in (
         ("KOSPI",CODE,official_price),
         ("KOSDAQ","123456",dict(open=25,high=27,low=23,close=24,
                             volume=1000,turnover_krw=24000))):
        row=dict(market=market,ticker=t,name=t,asof=str(ASOF),**price,
                 valid_daily_bar=True)
        p=official/(market+"_official.csv")
        write(p,MARKET_FIELDS,[row])
        manifest["market_file_sha256"][market]=digest(p.read_bytes())
    (official/"krx_v65_collect_status.json").write_text(json.dumps(manifest))
    return dirs

class RecoveryV66Test(unittest.TestCase):
    def test_classify_disjoint_sources_and_invalid_day(self):
        a=dict(open=100,high=102,low=98,close=101,volume=100)
        self.assertEqual(class_bar(a,a),"ALL_FIVE_FIELDS_MATCH")
        self.assertEqual(class_bar(a,{**a,"close":102,"volume":125}),
                         "OHL_EQUAL_CLOSE_DIVERGENT")
        self.assertEqual(class_bar(a,{**a,"high":104,"close":102}),
                         "MULTIPLE_OHLC_FIELDS_DIVERGENT")
        self.assertEqual(class_bar(a,{**a,"volume":200}),
                         "CLOSE_EQUAL_OTHER_FIELDS_DIVERGENT")
        self.assertEqual(class_bar({**a,"high":0},a),"RECOVERY_OHLCV_INVALID")
        self.assertEqual(class_bar(a,{**a,"volume":0}),"OFFICIAL_OHLCV_INVALID")

    def test_percent_delta_missing_denominator_never_infinite(self):
        self.assertIsNone(diffpct(0,100))
        self.assertIsNone(diffpct(None,90))
        self.assertEqual(diffpct(100,105),5)
        self.assertIsNone(num(float("nan")))

    def test_full_historic_same_setup_replay_and_one_bar_atr_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            report,rr=analysis(*(q[x] for x in
                  ("recovery","freeze","v58","v64","v65","official")))
            self.assertEqual(report["schema"],SCHEMA)
            self.assertEqual(report["candidates"],1)
            self.assertEqual(report["evaluated_method_rows"],3)
            self.assertEqual(report["recovery_mismatch_counts"],{
                "open":0,"high":1,"low":0,"close":1,"volume":1})
            self.assertEqual(report["official_equals_v18_all_five_fields_for_all_candidates"],True)
            self.assertTrue(report["original_v58_setup_reproduced_for_all_evaluations"])
            self.assertEqual(rr[0]["difference_classification"],
                             "MULTIPLE_OHLC_FIELDS_DIVERGENT")
            self.assertNotEqual(rr[0]["baseline_atr14"],
                                rr[0]["single_last_bar_atr14"])
            self.assertTrue(all(x["replayed_original_setup"]==x["archived_setup"] for x in rr))
            self.assertTrue(all(x["trade_approved"] is False for x in rr))
            self.assertTrue(all(x["regular_1530_verified"] is False for x in rr))
            self.assertFalse(report["adjusted_close_vs_market_endpoint_causation_proven"])
            self.assertEqual(report["decision"],"CASH")
            self.assertIn("CASH",mobile(report))

    def test_tampered_recovery_history_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            with (q["recovery"]/"candidate_daily_history_v52.csv").open("a") as f:
                f.write("\n")
            with self.assertRaisesRegex(ValueError,"ASOF_OR_SOURCE_CHAIN"):
                analysis(*(q[x] for x in
                           ("recovery","freeze","v58","v64","v65","official")))

    def test_tampered_official_market_file_sha_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            with (q["official"]/"KOSPI_official.csv").open("a") as f:
                f.write("\n")
            with self.assertRaisesRegex(ValueError,"OFFICIAL_FILE_SHA256_MISMATCH"):
                analysis(*(q[x] for x in
                           ("recovery","freeze","v58","v64","v65","official")))

    def test_prior_stored_signal_must_reproduce_identically(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            p=q["v58"]/"entry_strategy_v58_all.csv"
            data=list(csv.DictReader(p.open(encoding="utf-8-sig")))
            data[0]["setup"]="RESEARCH_TRIGGER_CONFIRMED_ASOF"
            write(p,list(data[0]),data)
            with self.assertRaisesRegex(ValueError,"V58_REPLAY_NOT_IDENTICAL"):
                analysis(*(q[x] for x in
                           ("recovery","freeze","v58","v64","v65","official")))

    def test_official_and_v18_mismatch_for_any_field_blocks_data_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            p=q["v64"]/"source_consensus_v64_all.csv"
            rows=list(csv.DictReader(p.open(encoding="utf-8-sig")))
            rows[0]["v18_volume"]="1500"
            write(p,list(rows[0]),rows)
            with self.assertRaisesRegex(ValueError,"MARKET_V18_OFFICIAL"):
                analysis(*(q[x] for x in
                           ("recovery","freeze","v58","v64","v65","official")))

    def test_forged_regular_1530_official_eod_flag_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            p=q["official"]/"krx_v65_collect_status.json"
            d=json.loads(p.read_text())
            d["independent_1530_regular_session_certified"]=True
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"ASOF_OR_SOURCE_CHAIN"):
                analysis(*(q[x] for x in
                           ("recovery","freeze","v58","v64","v65","official")))

    def test_changing_frozen_asof_hash_or_v64_status_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            p=q["v64"]/"source_consensus_v64_status.json"
            d=json.loads(p.read_text());d["manifest_sha256"]="tampered"
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"ASOF_OR_SOURCE_CHAIN"):
                analysis(*(q[x] for x in
                           ("recovery","freeze","v58","v64","v65","official")))

    def test_missing_or_duplicate_recovery_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=fixture(tmp)
            p=q["recovery"]/"candidates.csv"
            data=list(csv.DictReader(p.open(encoding="utf-8-sig")))
            write(p,list(data[0]),data+data)
            with self.assertRaisesRegex(ValueError,"ASOF_OR_SOURCE_CHAIN|DUPLICATE"):
                analysis(*(q[x] for x in
                           ("recovery","freeze","v58","v64","v65","official")))

if __name__=="__main__":
    unittest.main()
