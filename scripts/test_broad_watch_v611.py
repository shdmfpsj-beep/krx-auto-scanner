"""Offline v6.11 broad market observation gates; tests no broker authority."""
from __future__ import annotations
import csv,json,tempfile,unittest
from pathlib import Path
from forward_ledger_v63 import digest
from broad_watch_v611 import (SCHEMA,WATCH_FIELDS,AUDIT_FIELDS,
    MIN_HISTORY,MIN_TURNOVER_C3,blocked_issuer,num,save,gate_archives)
from full_market_scanner_v68 import SCHEMA as V68
from official_issuer_entry_v610 import SCHEMA as V610,BASIC_SCHEMA
from sector_flow_v69 import SCHEMA as V69

DAY="2026-10-23"
def toy_paths(base):
    root=Path(base);p={t:root/t for t in ("v18","scan","flow","issuer")}
    for folder in p.values():folder.mkdir(parents=True,exist_ok=True)
    daily={}
    for market,ticker in (("KOSPI","005930"),("KOSDAQ","028050")):
        file=p["v18"]/"market/daily_prices"/market/(DAY+".csv")
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text("ticker,Date,Open,High,Low,Close,Volume,TurnoverKRW\n"+
            f"{ticker},{DAY},100,105,90,100,1000,100000\n")
        daily[market]=digest(file.read_bytes())
    details=dict(schema=V68,asof=DAY,
        asof_universe_count=2,
        official_krx_and_v18_latest_all_fields_match=True,
        market_v18_daily_source_sha256=daily,trade_approved=False,
        regular_1530_only_price_certified=False)
    secs=dict(schema=V69,asof=DAY,
        v68_market_sha256=daily,
        ETF_membership_not_independent_PIT=True,
        flow_source_sha256={},trade_approved=False)
    e=dict(schema=V610,asof=DAY,full_market_initial_codes=2,
        v68_market_sha256=daily,v69_flow_sha256={},
        exact_regular_1530_prices_verified=False,trade_approved=False)
    official=dict(schema=BASIC_SCHEMA,asof=DAY,
        official_base_usable=True,market_counts={"KOSPI":1,"KOSDAQ":1})
    stats=dict(asof=DAY,orders_enabled=False)
    for file,value in (
        (p["scan"]/"full_market_v68_status.json",details),
        (p["flow"]/"sector_money_v69_status.json",secs),
        (p["issuer"]/"issuer_entry_v610_status.json",e),
        (p["issuer"]/"basic/krx_basic_v610_status.json",official),
        (p["v18"]/"diagnostics/collection_status.json",stats)):
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(json.dumps(value))
    return p

class BroadWatchV611Test(unittest.TestCase):
    def test_explicit_50억원_and_120_trading_days_are_research_thresholds(self):
        self.assertEqual(MIN_TURNOVER_C3,5_000_000_000)
        self.assertEqual(MIN_HISTORY,120)
        self.assertEqual(SCHEMA,"C3_K100_BROAD_COVERAGE_RISK_FIRST_WATCH_V611")

    def test_user_biotech_exclusion_works_without_name_matching_perfection_claim(self):
        for name in ("동서바이오", "ABC제약", "셀트리온", "일동약품", "전문의약"):
            self.assertTrue(blocked_issuer(name,False),name)
        self.assertTrue(blocked_issuer("정상건설",True))
        self.assertFalse(blocked_issuer("GS건설보통주",False))
        self.assertFalse(blocked_issuer("삼성화재해상보험보통주",False))

    def test_etf_reit_spac_special_names_never_appear_as_common_trade_ideas(self):
        for name in ("ABC스팩", "123 ETF", "삼성리츠", "KRX ETN", "리버스 인버스"):
            self.assertTrue(blocked_issuer(name,False),name)

    def test_nonfinite_and_bool_source_numbers_do_not_enter_rank(self):
        self.assertIsNone(num("NaN"))
        self.assertIsNone(num(float("inf")))
        self.assertIsNone(num("not a price"))
        self.assertIsNone(num(True))
        self.assertEqual(num("-123.4"),-123.4)

    def test_market_and_sector_ancestors_have_same_date_and_digests(self):
        with tempfile.TemporaryDirectory() as temp:
            p=toy_paths(temp)
            manifest=gate_archives(p["v18"],p["scan"],p["flow"],p["issuer"])
            self.assertEqual(len(manifest),4)
            self.assertEqual(manifest[0]["asof"],DAY)

    def test_forged_cross_sector_source_schema_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=toy_paths(temp)
            file=p["flow"]/"sector_money_v69_status.json"
            d=json.loads(file.read_text());d["schema"]="OTHER_FAKE_STOCK_SCORER"
            file.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"V611_ASOF_PROVENANCE"):
                gate_archives(p["v18"],p["scan"],p["flow"],p["issuer"])

    def test_price_snapshot_change_rejected_by_source_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            p=toy_paths(temp)
            with (p["v18"]/"market/daily_prices/KOSPI"/(DAY+".csv")).open("a") as file:
                file.write("x\n")
            with self.assertRaisesRegex(ValueError,"V611_FULL_KRX_DAILY_SOURCE_SHA_CHANGED"):
                gate_archives(p["v18"],p["scan"],p["flow"],p["issuer"])

    def test_parent_asof_drift_never_combines_new_and_old_markets(self):
        with tempfile.TemporaryDirectory() as temp:
            p=toy_paths(temp)
            file=p["issuer"]/"issuer_entry_v610_status.json"
            d=json.loads(file.read_text());d["asof"]="2026-10-22"
            file.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"V611_ASOF_PROVENANCE"):
                gate_archives(p["v18"],p["scan"],p["flow"],p["issuer"])

    def test_fail_closed_when_basic_share_labels_not_approved(self):
        with tempfile.TemporaryDirectory() as temp:
            p=toy_paths(temp)
            file=p["issuer"]/"basic/krx_basic_v610_status.json"
            d=json.loads(file.read_text());d["official_base_usable"]=False
            file.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"V611_ASOF_PROVENANCE"):
                gate_archives(p["v18"],p["scan"],p["flow"],p["issuer"])

    def test_save_three_distinct_groups_and_never_a_buy(self):
        with tempfile.TemporaryDirectory() as temp:
            r=dict(schema=SCHEMA,asof=DAY,full_market_universe=2764,
                official_common_120day_50e8_liquid=328,
                official_common_120day_liquid_5d_positive_FI=116,
                both_investors_5d_net_buy_positive=27,
                strong_proxy_sector_5d_positive_liquid=10,
                strong_proxy_sector_last20day_declining_count=9,
                moderate_trend_no_chase_research_count=10,
                trade_approved=False,orders_enabled=False,decision="CASH")
            groups={g:[] for g in ("strong_sector_watch",
              "broad_flow_watch","two_sided_investors_watch",
              "moderate_trend_watch")}
            out=Path(temp)/"output"
            save(out,r,[],[],groups)
            self.assertEqual(len(list(csv.DictReader(
                 (out/"broad_watch_v611_all.csv").open(encoding="utf-8-sig")))),0)
            text=(out/"broad_watch_v611_mobile.md").read_text(encoding="utf-8")
            self.assertIn("CASH",text)
            self.assertIn("넓은 발굴",text)
            self.assertIn("외국인",text)

if __name__=="__main__":unittest.main()
