#!/usr/bin/env python3
"""Sector-first dynamic OHLC research contract: no stale/no pharma/no BUY."""
import unittest,csv,tempfile
from pathlib import Path
from datetime import date,timedelta
from sector_dynamic_structure import select,generate,reuse_v18_daily_bars

ASOF=date(2026,10,22)
STATUS={"asof":str(ASOF),"scan_date":str(ASOF),"core_data_verified":True,
        "evidence_scan_dates_aligned":True,"research_top3_sector_ids":["SEMICON","POWER","SHIP"]}
def row(ticker,sid,score="88",asof=str(ASOF),name="성장주"):
    return dict(ticker=ticker,sector_id=sid,name=name,research_proxy_index=score,
                asof=asof,price_flow_ready="YES",trade_approval="NO")

class DynamicSectorTests(unittest.TestCase):
    def test_research_sectors_only_and_sector_balance(self):
        samples=[row(f"{i:06d}","SEMICON",str(100-i)) for i in range(1,9)]
        samples += [row("010120","POWER","75"),row("267260","POWER","74"),
                    row("012450","SHIP","73"),row("999999","OTHER","999")]
        selected,issues=select(STATUS,samples,ASOF,max_total=6,per_sector=2)
        self.assertEqual(len(selected),6)
        self.assertIn("010120",selected)
        self.assertIn("012450",selected)
        self.assertNotIn("999999",selected)
        self.assertEqual(issues,[])
    def test_stale_run_has_zero_dynamic_prices(self):
        samples=[row("005930","SEMICON")]
        chosen,errors=select(STATUS,samples,ASOF+timedelta(days=1))
        self.assertEqual(chosen,{})
        self.assertIn("MISSING_OR_STALE_VERIFIED_SECTOR_UNIVERSE",errors)
    def test_no_trading_permission_stays_closed(self):
        candidates=[{**row("005930","SEMICON"),"trade_approval":"YES"}]
        chosen,errors=select(STATUS,candidates,ASOF)
        self.assertEqual(chosen,{})
        self.assertIn("NO_FRESH_TOP3_STOCK_RESEARCH_ROWS",errors)
    def test_biotech_and_non_top3_excluded(self):
        samples=[row("123456","SEMICON",name="바이오홀딩스"),
                 row("111111","PHARMA"),row("222222","POWER",name="전력기기")]
        chosen,_=select(STATUS,samples,ASOF)
        self.assertEqual(chosen,{"222222":"전력기기"})
    def test_unverified_stock_flow_not_fabricated(self):
        r={**row("005930","SEMICON"),"price_flow_ready":"NO"}
        self.assertEqual(select(STATUS,[r],ASOF)[0],{})
    def test_collector_exception_does_not_crash_full_scan(self):
        def broken(t,day):
            raise RuntimeError("provider temporary outage")
        out,names,err=generate(STATUS,[row("005930","SEMICON")],ASOF,fetch=broken)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["historical_stop_reference"],"")
        self.assertEqual(out[0]["structure_state"],"DATA_MISSING")
        self.assertIn("COLLECTOR_RuntimeError",out[0]["data_problems"])
        self.assertEqual(names,{"005930":"성장주"})
    def test_missing_summary_is_cash_no_price_requests(self):
        called=[]
        def fetch(t,asof):
            called.append(t)
            return [],"NONE",[]
        out,names,problems=generate({},[row("005930","SEMICON")],ASOF,fetch=fetch)
        self.assertEqual(called,[])
        self.assertEqual(out,[])
        self.assertEqual(names,{})
        self.assertTrue(problems)
    def test_existing_v18_daily_bars_reused_without_network_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/"reports/sector_evidence_v18/market/daily_prices/KOSPI"
            root.mkdir(parents=True)
            # 80 as-of market observations fixture, confirmed low 12 bars back.
            for i in range(80):
                d=ASOF-timedelta(days=79-i)
                with (root/(str(d)+".csv")).open("w",encoding="utf-8",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=[
                      "ticker","Date","Open","High","Low","Close","Volume","TurnoverKRW"])
                    w.writeheader()
                    w.writerow(dict(ticker="005930",Date=str(d),Open="1000",
                      High="1010",Low="920" if i==68 else "990",
                      Close="1000",Volume="10000",TurnoverKRW="1000000"))
            cached=reuse_v18_daily_bars(Path(folder),{"005930":"삼성전자"},ASOF)
            self.assertEqual(cached["005930"][1],"V18_KRX_CACHED")
            called=[]
            def network(t,d):
                called.append(t)
                raise AssertionError("Network collection should not be needed")
            results,names,issues=generate(
                STATUS,[row("005930","SEMICON")],ASOF,
                fetch=network,evidence_root=Path(folder))
            self.assertEqual(called,[])
            self.assertEqual(len(results),1)
            self.assertGreater(results[0]["historical_stop_reference"],0)
            self.assertEqual(results[0]["data_source"],"V18_KRX_CACHED")

    def test_incomplete_v18_cache_requires_independent_free_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/"market/daily_prices/KOSPI"
            root.mkdir(parents=True)
            d=ASOF
            with (root/(str(d)+".csv")).open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=[
                    "ticker","Date","Open","High","Low","Close","Volume","TurnoverKRW"])
                w.writeheader()
                w.writerow(dict(ticker="005930",Date=str(d),Open="1000",
                     High="1010",Low="990",Close="1000",Volume="10",TurnoverKRW="1000"))
            self.assertEqual(reuse_v18_daily_bars(Path(folder),
                             {"005930":"삼성전자"},ASOF),{})
            called=[]
            def fallback(t,d):
                called.append(t)
                return [],"NONE",["FDR_EMPTY","PYKRX_EMPTY"]
            results,_,_=generate(STATUS,[row("005930","SEMICON")],ASOF,
                  fetch=fallback,evidence_root=Path(folder))
            self.assertEqual(called,["005930"])
            self.assertEqual(results[0]["historical_stop_reference"],"")
            self.assertEqual(results[0]["structure_state"],"DATA_MISSING")

    def test_max_twenty(self):
        src=[row(f"{i:06d}","SEMICON",str(100-i)) for i in range(1,40)]
        names,_=select(STATUS,src,ASOF,max_total=20)
        self.assertEqual(len(names),20)

if __name__=="__main__":
    unittest.main()
