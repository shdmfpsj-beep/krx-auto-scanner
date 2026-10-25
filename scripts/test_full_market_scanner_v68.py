"""All-market, all-asof strict market-wide v6.8 scanner regressions."""
from __future__ import annotations
import csv,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from full_market_scanner_v68 import (
    SCHEMA,DAY_FIELDS,REQUIRED_WARMUP,build,write_outputs,parse_days,
    candidate_features,source_name)
from forward_ledger_v63 import digest
from krx_official_eod_v65 import MARKET_FIELDS,COLLECT_SCHEMA

ASOF=date(2026,10,23)
def write(path,headers,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=headers,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def fixture(root):
    root=Path(root);v18=root/"market_archive";official=root/"krx"
    names={}
    dates=[];d=ASOF
    while len(dates)<175:
        if d.weekday()<5:dates.append(d)
        d-=timedelta(days=1)
    dates.reverse()
    markets={}
    offfiles={}
    for market,start in (("KOSPI",10000),("KOSDAQ",20000)):
        marketrows=[];officialrows=[]
        for i in range(105):
            t=str(start+i).zfill(6)
            name=("FIRST_BREAKOUT" if i==0 else
                  "SECOND_BREAKOUT" if i==1 and market=="KOSPI" else
                  "ABC바이오" if i==2 else
                  "TEST_ETF" if i==3 else
                  "BETA_NORMAL_"+str(i))
            trend=(i==0 or (i==1 and market=="KOSPI") or i==2)
            bars=[]
            for j,day in enumerate(dates):
                close=100+.25*j if trend else 100.
                volume=1000.
                if day==ASOF and trend:
                    close+=20;volume=3500
                if day==ASOF and i==4:
                    volume=0
                values=dict(Date=str(day),Open=round(close,3),
                    High=round(close+2,3),Low=round(close-2,3),
                    Close=round(close,3),Volume=volume,
                    TurnoverKRW=round(close*volume,3))
                bars.append(values)
            if i==5:
                bars=bars[-120:] # no 160bar warmup
            write(v18/"market/prices"/(t+".csv"),
                  ("Date","Open","High","Low","Close","Volume","TurnoverKRW"),bars)
            last=bars[-1]
            marketrows.append(dict(ticker=t,**last))
            officialrows.append(dict(market=market,ticker=t,name=name,
                asof=str(ASOF),open=last["Open"],high=last["High"],
                low=last["Low"],close=last["Close"],
                volume=last["Volume"],turnover_krw=last["TurnoverKRW"],
                valid_daily_bar=bool(last["Volume"])))
            names[t]=name
        write(v18/"market/daily_prices"/market/(str(ASOF)+".csv"),
              DAY_FIELDS,marketrows)
        p=official/(market+"_official.csv")
        write(p,MARKET_FIELDS,officialrows)
        offfiles[market]=digest(p.read_bytes())
        markets[market]=len(marketrows)
    (v18/"diagnostics").mkdir(parents=True,exist_ok=True)
    (v18/"diagnostics/collection_status.json").write_text(json.dumps(dict(
        asof=str(ASOF),orders_enabled=False,
        datasets=dict(
            prices=dict(status="OK"),
            krx_preflight=dict(status="OK",asof=str(ASOF)))))
        )
    official_manifest=dict(schema=COLLECT_SCHEMA,asof=str(ASOF),
        retrieval_utc="2026-10-25T03:20:00+00:00",
        official_dataset_usable=True,krx_eod_authenticated=True,
        independent_1530_regular_session_certified=False,
        source_price_authorized_for_trading=False,
        official_market_rows=sum(markets.values()),
        market_file_sha256=offfiles,
        raw_response_sha256={"KOSPI":"fixture","KOSDAQ":"fixture"},
        trade_approved=False,orders_enabled=False)
    (official/"krx_v65_collect_status.json").write_text(
        json.dumps(official_manifest))
    return v18,official,names

class V68ScannerTests(unittest.TestCase):
    def test_full_universe_without_legacy_82_anchors_and_candidate_120bars(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,names=fixture(temp)
            report,cands,audit,history,methods=build(v18,official)
            self.assertEqual(report["schema"],SCHEMA)
            self.assertEqual(report["asof_universe_count"],210)
            self.assertEqual(report["market_counts"],{"KOSPI":105,"KOSDAQ":105})
            self.assertEqual(len(audit),210)
            self.assertEqual(len(cands),3)
            self.assertEqual(len(methods),9)
            self.assertEqual(len(history),3*120)
            self.assertEqual(report["rejected_and_nontrigger_universe_rows"],207)
            self.assertTrue(all(c["turnover_source"]=="SOURCE_REPORTED" for c in cands))
            self.assertTrue(all(c["instrument_type"]=="UNKNOWN" for c in cands))
            self.assertEqual(report["decision"],"CASH")
            self.assertFalse(report["regular_1530_only_price_certified"])
            self.assertTrue(all(not r["trade_approved"] for r in methods))

    def test_name_based_special_ETF_SPAC_biotech_exclusion_not_common_certification(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,names=fixture(temp)
            report,cands,audit,*_=build(v18,official)
            self.assertTrue(any(x["reason"]=="SUSPECTED_NON_COMMON_SPECIAL_NAME_EXCLUDED"
                                for x in audit))
            self.assertTrue(all("바이오" not in c["name"] for c in cands))
            self.assertFalse(report["instrument_common_share_type_verified"])

    def test_source_disagreement_for_official_close_blocks_entire_research(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,_=fixture(temp)
            p=v18/"market/daily_prices/KOSPI"/(str(ASOF)+".csv")
            rows=list(csv.DictReader(p.open(encoding="utf-8-sig")))
            rows[0]["Close"]="1"
            write(p,DAY_FIELDS,rows)
            with self.assertRaisesRegex(ValueError,"KRX_OFFICIAL_V18"):
                build(v18,official)

    def test_official_csv_tamper_refused_by_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,_=fixture(temp)
            with (official/"KOSPI_official.csv").open("a") as f:f.write("TAMPER")
            with self.assertRaisesRegex(ValueError,"OFFICIAL_FILE_SHA256_MISMATCH"):
                build(v18,official)

    def test_date_stale_complete_market_does_not_reuse_today(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,_=fixture(temp)
            p=v18/"diagnostics/collection_status.json"
            s=json.loads(p.read_text());s["asof"]="2026-10-22";p.write_text(json.dumps(s))
            with self.assertRaisesRegex(ValueError,"V18_DATE_OR_MARKET_COMPLETENESS"):
                build(v18,official)

    def test_market_day_alphanumeric_stock_code_kept(self):
        # Not all six-character KRX IDs are numeric; strict code mapping
        # must not automatically truncate, cast to int or create orders.
        data=[dict(Date="2026-10-22",Open="100",High="101",
              Low="99",Close="100",Volume="1000",TurnoverKRW="100000"),
              dict(Date="2026-10-23",Open="100",High="101",
              Low="99",Close="100",Volume="1000",TurnoverKRW="100000")]
        bars,err=parse_days(data,"00104K",ASOF)
        self.assertIsNone(err)
        self.assertEqual(bars[0]["ticker"],"00104K")

    def test_future_date_in_history_is_rejected(self):
        bars=[dict(Date="2026-10-26",Open=100,High=102,Low=99,
                   Close=100,Volume=1000,TurnoverKRW=100000)]
        _,err=parse_days(bars,"001000",ASOF)
        self.assertEqual(err,"FUTURE_DAILY_BAR_IN_SOURCE")

    def test_unsorted_duplicate_history_dates_are_rejected(self):
        bars=[dict(Date="2026-10-23",Open=100,High=102,Low=99,
                  Close=100,Volume=1000,TurnoverKRW=100000)]*2
        _,err=parse_days(bars,"001000",ASOF)
        self.assertEqual(err,"HISTORY_NOT_STRICTLY_CHRONOLOGICAL")

    def test_invalid_zero_volume_160bar_history_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,_=fixture(temp)
            report,cands,audit,*_=build(v18,official)
            match=[x for x in audit if x["ticker"]=="010004"]
            self.assertEqual(match[0]["reason"],"INVALID_RECENT_160_DAILY_OHLCV")

    def test_no_company_classification_or_certified_80_scores_leak_into_report(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,_=fixture(temp)
            report,cands,audit,history,methods=build(v18,official)
            self.assertFalse(report["final_80point_score_verified"])
            self.assertTrue(report["intermediate_score_out_of_85_only"])
            self.assertTrue(all(c["preliminary_rank_only"] is True for c in cands))
            self.assertTrue(all(c["regular_1530_session_certified"] is False for c in cands))
            self.assertTrue(all(x["ordinary_common_stock_verified"] is False for x in methods))

    def test_writer_outputs_all_universe_audit_and_no_buy_no_orders(self):
        with tempfile.TemporaryDirectory() as temp:
            v18,official,_=fixture(temp)
            report,cands,audit,histories,methods=build(v18,official)
            out=Path(temp)/"out"
            write_outputs(out,report,cands,audit,histories,methods)
            self.assertEqual(len(list(csv.DictReader(
                (out/"full_market_v68_universe_audit.csv").open(encoding="utf-8-sig")))),210)
            self.assertIn("CASH",(out/"full_market_v68_mobile.md").read_text())
            self.assertIn("KRX", (out/"full_market_v68_mobile.md").read_text())
            self.assertTrue(all(row["trade_approved"]=="False" for row in
                csv.DictReader((out/"full_market_v68_method_research.csv").open(encoding="utf-8-sig"))))

if __name__=="__main__":unittest.main()
