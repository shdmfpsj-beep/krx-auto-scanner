"""v6.8.1 exact dated source-report liquidity screen and SHA tests."""
from __future__ import annotations
import csv,json,tempfile,unittest
from pathlib import Path
from test_full_market_scanner_v68 import fixture,write
from full_market_scanner_v68 import (build,write_outputs,CAND_FIELDS,
    DIAGNOSTIC_FIELDS,RESEARCH_FIELDS)
from liquidity_watch_v68 import run,write_outputs as save_liquid,SCHEMA
from forward_ledger_v63 import digest

def scan_fixture(work):
    v18,official,_=fixture(work)
    report,candidates,diag,histories,methods=build(v18,official)
    p=Path(work)/"scan"
    write_outputs(p,report,candidates,diag,histories,methods)
    return p

def csvrows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        return reader.fieldnames,list(reader)

def synthetic_turnover(scan,ticker,day,average):
    cp=scan/"full_market_v68_candidates.csv"
    hp=scan/"full_market_v68_candidate_120bars.csv"
    cols,candidates=csvrows(cp)
    histcols,bars=csvrows(hp)
    target=[r for r in bars if r["ticker"]==ticker]
    assert len(target)==120
    for r in target[-21:-1]:r["turnover_krw"]=str(average)
    target[-1]["turnover_krw"]=str(day)
    actual={r["date"]:r for r in target}
    for row in bars:
        if row["ticker"]==ticker:row["turnover_krw"]=actual[row["date"]]["turnover_krw"]
    parsed=[dict(ticker=ticker,date=r["date"],
                 **{k:float(r[k]) for k in ("open","high","low",
                                           "close","volume","turnover_krw")},
                 data_source=r["data_source"]) for r in target]
    sig=digest(json.dumps(parsed,ensure_ascii=False,sort_keys=True).encode("utf-8"))
    for c in candidates:
        if c["ticker"]==ticker:
            c["turnover_krw"]=str(day)
            c["history_last_120_sha256"]=sig
    write(cp,cols,candidates)
    write(hp,histcols,bars)
    reseal(scan)

def reseal(scan):
    f=scan/"full_market_v68_status.json"
    manifest=json.loads(f.read_text(encoding="utf-8"))
    for name in manifest["artifact_file_sha256"]:
        manifest["artifact_file_sha256"][name]=digest((scan/name).read_bytes())
    f.write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf-8")

class FullMarketLiquidityTests(unittest.TestCase):
    def test_raw_unbiased_candidates_kept_but_not_treated_as_inflows(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            report,rows,c3,k100=run(scan)
            self.assertEqual(report["schema"],SCHEMA)
            self.assertEqual(report["full_market_asof_universe"],210)
            self.assertEqual(report["candidates_observed"],3)
            self.assertEqual(report["c3_liquid_count"],0)
            self.assertEqual(len(c3),0)
            self.assertTrue(all(not r["trade_approved"] for r in rows))
            self.assertFalse(report["regular_1530_verified"])

    def test_liquid_c3_and_k100_rank_distinguishes_rising_money_activity(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            synthetic_turnover(scan,"010000",15_000_000_000,7_500_000_000)
            synthetic_turnover(scan,"010001",4_000_000_000,5_000_000_000)
            report,rows,c3,k100=run(scan)
            self.assertEqual(report["c3_liquid_count"],1)
            self.assertEqual(report["k100_liquid_count"],2)
            self.assertEqual(report["c3_research_ticker_top5"],["010000"])
            self.assertEqual(report["k100_research_ticker_top5"][0],"010000")
            self.assertEqual(report["k100_research_ticker_top5"][1],"010001")
            self.assertEqual(c3[0]["turnover_expansion_vs_previous20"],2.0)
            self.assertFalse(report["final_80point_score_verified"])
            out=Path(temp)/"out"
            save_liquid(out,report,rows,c3,k100)
            self.assertIn("CASH",(out/"liquid_watch_v681_mobile.md").read_text())
            self.assertIn("15000000000.0",(out/"liquid_watch_v681_all.csv").read_text())

    def test_stale_or_tampered_candidate_table_fails_full_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            (scan/"full_market_v68_candidates.csv").write_text("CORRUPT")
            with self.assertRaisesRegex(ValueError,"SHA256_MISMATCH"):
                run(scan)

    def test_mutated_history_with_all_file_sha_resealed_still_fails_per_stock_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            p=scan/"full_market_v68_candidate_120bars.csv"
            cols,bars=csvrows(p)
            bars[15]["turnover_krw"]="12345"
            write(p,cols,bars);reseal(scan)
            with self.assertRaisesRegex(ValueError,"120BAR_CONTENT_HASH_MISMATCH"):
                run(scan)

    def test_any_120bar_future_date_cannot_be_used_for_money_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            p=scan/"full_market_v68_candidate_120bars.csv"
            cols,bars=csvrows(p)
            bars[5]["date"]="2026-10-26"
            write(p,cols,bars);reseal(scan)
            with self.assertRaisesRegex(ValueError,"LOOKAHEAD_OR_DUPLICATE_DATE"):
                run(scan)

    def test_invented_80point_final_certification_does_not_promote_buy(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            p=scan/"full_market_v68_status.json"
            obj=json.loads(p.read_text(encoding="utf-8"))
            obj["trade_approved"]=True
            p.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,"AUDITED_RAW_CANDIDATES_MISSING"):
                run(scan)

    def test_no_fake_foreign_institution_buy_from_high_turnover(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            synthetic_turnover(scan,"010000",20_000_000_000,2_000_000_000)
            s,r,c,k=run(scan)
            self.assertTrue(c)
            self.assertTrue(s["liquid_money_expansion_is_not_foreign_or_institution_net_buy"])
            self.assertFalse(s["final_80point_score_verified"])
            self.assertTrue(all(not x["sector_flow_institution_foreign_verified"] for x in r))
            self.assertTrue(all(not x["common_stock_confirmed"] for x in r))

    def test_ratio_cooling_filter_bars_low_quality_high_turnover(self):
        with tempfile.TemporaryDirectory() as temp:
            scan=scan_fixture(temp)
            synthetic_turnover(scan,"010000",6_000_000_000,20_000_000_000)
            s,r,c,k=run(scan)
            self.assertEqual(s["c3_liquid_count"],0)
            self.assertFalse(any(x["ticker"]=="010000" for x in c))
            self.assertEqual(next(x for x in r if x["ticker"]=="010000")["turnover_observation"],
                             "TURNOVER_PRESENT_NOT_RISING_150PCT")

if __name__=="__main__":unittest.main()
