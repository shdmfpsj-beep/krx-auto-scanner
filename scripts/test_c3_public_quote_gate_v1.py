import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from c3_public_quote_gate_v1 import validate_public_quote

NOW=datetime(2026,11,2,13,30,tzinfo=ZoneInfo("Asia/Seoul"))
def record(**kw):
    r=dict(ticker="271560",source="permitted_public_provider",automated_access_permitted=True,
           price=112000,observed_at=(NOW-timedelta(minutes=5)).isoformat(),market="KRX_REGULAR")
    r.update(kw)
    return r
class TestPublicQuoteGate(unittest.TestCase):
    def test_valid(self): self.assertEqual(validate_public_quote(record(),NOW)[1],"VERIFIED_OBSERVATION")
    def test_stale(self): self.assertEqual(validate_public_quote(record(observed_at=(NOW-timedelta(minutes=30)).isoformat()),NOW)[1],"STALE_OR_FUTURE")
    def test_unlicensed(self): self.assertEqual(validate_public_quote(record(automated_access_permitted=False),NOW)[1],"SOURCE_NOT_ELIGIBLE")
    def test_nxt(self): self.assertEqual(validate_public_quote(record(market="NXT"),NOW)[1],"NOT_KRX_REGULAR")
    def test_missing_timezone(self): self.assertEqual(validate_public_quote(record(observed_at="2026-11-02T13:25:00"),NOW)[1],"MISSING_TIMEZONE")
    def test_other_ticker(self): self.assertEqual(validate_public_quote(record(ticker="005930"),NOW)[1],"SOURCE_NOT_ELIGIBLE")
if __name__=="__main__": unittest.main()
