import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from kis_regular_minute import (
    summarize_minute_rows,query_end_from_earliest,auth_is_available)
from kis_regular_minute_cli import build_missing,collect_ticker,nominal_krx_regular_asof

D="20261022"
T="005930"

def minute(hh,mm,price=100,vol=10,date=D):
    return {"stck_bsop_date":date,"stck_cntg_hour":f"{hh:02d}{mm:02d}00",
        "stck_oprc":str(price),"stck_hgpr":str(price+1),
        "stck_lwpr":str(price-1),"stck_prpr":str(price),
        "cntg_vol":str(vol),"acml_tr_pbmn":"1000000"}

def regular():
    out=[]
    for minute_index in range(9*60,15*60+31):
        out.append(minute(minute_index//60,minute_index%60))
    return out

class RegularMinuteTests(unittest.TestCase):
    def test_391_timestamped_rows_reconstruct_regular_ohlcv(self):
        rows=regular()
        rows.extend([minute(16,1,price=110,vol=50),
                     minute(19,59,price=92,vol=80),
                     minute(15,40,price=102,vol=90)])
        r=summarize_minute_rows(rows,D,T)
        self.assertTrue(r["regular_ohlcv_reconstruction_verified"])
        self.assertEqual(r["minutes_seen"],391)
        self.assertEqual(r["outside_regular_rows_excluded"],3)
        self.assertEqual(r["regular_ohlcv"]["Close"],100)
        self.assertEqual(r["regular_ohlcv"]["Open"],100)
        self.assertEqual(r["regular_ohlcv"]["High"],101)
        self.assertEqual(r["regular_ohlcv"]["Low"],99)
        self.assertEqual(r["regular_ohlcv"]["Volume"],3910)
        self.assertFalse(r["trade_approved"])

    def test_last_trade_offhours_cannot_redefine_close(self):
        rows=regular()
        rows[-1]["stck_prpr"]="100"
        rows.append(minute(20,0,price=200))
        r=summarize_minute_rows(rows,D,T)
        self.assertEqual(r["regular_ohlcv"]["Close"],100)
        self.assertEqual(r["outside_regular_rows_excluded"],1)

    def test_missing_auction_close_does_not_certify(self):
        r=summarize_minute_rows(regular()[:-1],D,T)
        self.assertFalse(r["regular_ohlcv_reconstruction_verified"])
        self.assertIn("CLOSING_AUCTION_NOT_OBSERVED",r["blockers"])

    def test_wrong_date_cannot_be_silently_used(self):
        rows=regular()
        rows.append(minute(15,30,date="20261021"))
        r=summarize_minute_rows(rows,D,T)
        self.assertFalse(r["regular_ohlcv_reconstruction_verified"])
        self.assertIn("SOURCE_ROW_DATE_MISMATCH",r["blockers"])

    def test_conflicting_duplicate_minute_rejected(self):
        rows=regular()
        rows.append(minute(11,11,price=104))
        r=summarize_minute_rows(rows,D,T)
        self.assertIn("CONFLICTING_DUPLICATE_MINUTE",r["blockers"])
        self.assertFalse(r["regular_ohlcv_reconstruction_verified"])

    def test_identical_overlapping_page_does_not_inflate_volume(self):
        rows=regular()
        rows.append(rows[42].copy())
        r=summarize_minute_rows(rows,D,T)
        self.assertEqual(r["regular_ohlcv"]["Volume"],3910)

    def test_thin_or_halted_stock_not_accepted_as_full_bar(self):
        thin=[minute(14,42),minute(15,30)]
        r=summarize_minute_rows(thin,D,T)
        self.assertIn("INSUFFICIENT_MINUTE_COVERAGE",r["blockers"])
        self.assertIn("REGULAR_OPEN_NOT_OBSERVED",r["blockers"])

    def test_market_J_required_and_cannot_infer_NXT_or_UN(self):
        r=summarize_minute_rows(regular(),D,T,source_market="UN")
        self.assertIn("NON_KRX_MARKET_SOURCE",r["blockers"])
        self.assertFalse(r["regular_ohlcv_reconstruction_verified"])

    def test_page_cursor_moves_backwards(self):
        self.assertEqual(query_end_from_earliest([minute(12,0)]),"115900")
        self.assertIsNone(query_end_from_earliest([minute(9,0)]))

    def test_no_auth_is_safe_cash_not_network(self):
        self.assertFalse(auth_is_available({}))
        x=build_missing(D,[T])
        self.assertEqual(x["data_status"],"PENDING_PROVIDER_CONNECTION")
        self.assertEqual(x["ready_count"],0)
        self.assertFalse(x["trade_approved"])
        self.assertEqual(x["decision"],"CASH")

    def test_output_is_not_investor_net_flow_or_full_sector_universe(self):
        r=summarize_minute_rows(regular(),D,T)
        self.assertFalse(r["investor_net_flow_regular_verified"])
        self.assertFalse(r["sector_universe_verified"])
        self.assertFalse(r["historical_65_days_verified"])

    def test_pagination_loop_fails_closed_and_secret_free(self):
        with patch("kis_regular_minute_cli.fetch_page") as mock:
            # Returns a page whose oldest minute is newer than previous cursor:
            mock.side_effect=[regular()[-120:],regular()[-120:]]
            with patch("kis_regular_minute_cli.time.sleep"):
                r=collect_ticker(D,T,"fake-token","fake-key","fake-secret")
        self.assertIn("PAGINATION_NOT_PROGRESSING",r["blockers"])
        self.assertFalse(r["regular_ohlcv_reconstruction_verified"])

    def test_regular_asof_local_close_date(self):
        tz=ZoneInfo("Asia/Seoul")
        self.assertEqual(nominal_krx_regular_asof(datetime(2026,10,23,18,0,tzinfo=tz)),D.replace("22","23"))
        self.assertEqual(nominal_krx_regular_asof(datetime(2026,10,23,8,0,tzinfo=tz)),D)
        self.assertEqual(nominal_krx_regular_asof(datetime(2026,10,25,18,0,tzinfo=tz)),"20261023")

if __name__=="__main__":unittest.main()
