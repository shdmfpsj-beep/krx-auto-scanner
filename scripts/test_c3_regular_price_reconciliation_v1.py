"""Close mismatch safety for C3; CSV declarations are never official certification."""
import csv,tempfile,unittest
from pathlib import Path
from c3_regular_price_reconciliation_v1 import compare,run,reference_records

def row(ticker,close,reference=None):
    return compare(ticker,"2026-10-30",close,reference)

class TestRegularMismatch(unittest.TestCase):
    def test_orion_discrepancy_is_explicit_and_never_moves_stop(self):
        ref=dict(reference_date="2026-10-30",reference_close=114800,
                 reference_url="https://example.org/orion",
                 source_scope="KRX_REGULAR_0900_1530_DECLARED")
        x=row("271560",114200,ref)
        self.assertEqual(x["price_state"],"EXTERNAL_REFERENCE_DECLARATION_MISMATCH")
        self.assertEqual(x["close_difference_krw"],600)
        self.assertFalse(x["buy_approved"])
        self.assertTrue(x["structure_stop_unchanged_until_new_dated_OHLCV"])

    def test_same_close_is_not_automatically_authoritative(self):
        ref=dict(reference_date="2026-10-30",reference_close=114200,
                 reference_url="https://example.org/matching",
                 source_scope="KRX_REGULAR_0900_1530_DECLARED")
        x=row("271560",114200,ref)
        self.assertIn("UNAUDITED",x["price_state"])
        self.assertFalse(x["authenticated_regular_source"])
        self.assertFalse(x["buy_approved"])

    def test_future_reference_never_used_to_change_prior_signal(self):
        ref=dict(reference_date="2026-11-02",reference_close=114800,
                 reference_url="https://example.org/future",
                 source_scope="KRX_REGULAR_0900_1530_DECLARED")
        with self.assertRaisesRegex(ValueError,"DATE_DOES_NOT_MATCH"):
            row("271560",114200,ref)

    def test_missing_regular_price_blocks(self):
        x=row("026960",28400)
        self.assertEqual(x["price_state"],"REGULAR_REFERENCE_NOT_SUPPLIED")
        self.assertIsNone(x["regular_reference_close"])
        self.assertFalse(x["buy_approved"])

    def test_two_stock_declared_mismatch_never_authenticates(self):
        with tempfile.TemporaryDirectory() as p:
            root=Path(p)
            with (root/"rank.csv").open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["ticker","asof","close"])
                w.writeheader()
                w.writerows([dict(ticker="271560",asof="2026-10-30",close=114200),
                             dict(ticker="026960",asof="2026-10-30",close=28400)])
            with (root/"reference.csv").open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=[
                    "ticker","asof","regular_close","source_url","source_scope"])
                w.writeheader()
                w.writerows([
                   dict(ticker="271560",asof="2026-10-30",regular_close=114800,
                        source_url="https://example.org/stock1",
                        source_scope="KRX_REGULAR_0900_1530_DECLARED"),
                   dict(ticker="026960",asof="2026-10-30",regular_close=28450,
                        source_url="https://example.org/stock2",
                        source_scope="KRX_REGULAR_0900_1530_DECLARED")])
            report,audits=run(root/"rank.csv",root/"out",root/"reference.csv")
            self.assertEqual(report["mismatch_tickers"],["271560","026960"])
            self.assertEqual(report["mismatch_count"],2)
            self.assertFalse(report["regular_session_price_authoritatively_certified"])
            self.assertFalse(report["trade_approved"])
            self.assertEqual([x["close_difference_krw"] for x in audits],[600,50])

if __name__=="__main__":unittest.main()
