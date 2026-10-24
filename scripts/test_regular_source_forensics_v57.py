"""No-network regression tests for v5.7 dated KRX OHLC discrepancy forensics."""
import copy
import unittest
from regular_source_forensics_v57 import analyze, probe_index

ASOF="2026-10-23"

def price(ticker,r,v,market="KOSPI"):
    return dict(ticker=ticker,market=market,recovery_ohlc=r,v18_ohlc=v,
                recovery_close=r[-1],v18_close=v[-1],
                close_equal=(r[-1]==v[-1]),trade_approved=False)

def parity(rows):
    conflicts=[x["ticker"] for x in rows if not x["close_equal"]]
    return dict(schema="free_krx_full_parity_v56",asof=ASOF,
        source_status="CROSS_SOURCE_CLOSE_CONFLICT" if conflicts else
                      "CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY",
        comparison_rows=rows,overlap_tickers=len(rows),
        close_mismatches=len(conflicts),mismatch_tickers=conflicts,
        mismatch_tickers_complete=True,independent_provider_verified=False,
        regular_only_session_certified=False,trade_approved=False,
        invalid_recovery_tickers=["050090"],invalid_v18_tickers=[])

def kis(ticker="005930",day="20261023",price_close=100,verified=True):
    return dict(schema="kis_krx_minute_audit_v1",date=day,
        source="KIS_OFFICIAL_MINUTES_J_KRX",read_only=True,
        regular_reconstructions=[
            dict(asof=day,ticker=ticker,market_code="J",
                 session="KRX_REGULAR_0900_1530",
                 regular_ohlcv_reconstruction_verified=verified,
                 last_minute="153000",minutes_seen=391,
                 duplicate_time_conflicts=0,wrong_date_rows=0,
                 invalid_minute_rows=0,trade_approved=False,
                 extra_validation_issues=[],
                 regular_ohlcv=dict(Open=98,High=110,Low=90,Close=price_close))])

class KRXForensicsV57Test(unittest.TestCase):
    def example(self):
        return [
          price("005930",[98,110,90,100],[98,110,90,100]),
          price("000660",[98,110,90,106],[98,110,90,100]),
          price("035420",[98,120,90,116],[98,110,90,109]),
          price("012330",[99,115,90,108],[98,110,90,103]),
        ]

    def test_diagnostic_categories_only_not_causal_proof(self):
        r=analyze(parity(self.example()),ASOF)
        self.assertTrue(r["diagnosis_valid"])
        self.assertEqual(r["total_rows"],4)
        self.assertEqual(r["mismatches"],3)
        self.assertEqual(r["categories"],dict(
            OHLC_EXACT_MATCH_UNCERTIFIED=1,
            CLOSE_ONLY_SAME_OPEN_HIGH_LOW=1,
            RANGE_MISMATCH_SAME_OPEN=1,
            OPEN_AND_OR_RANGE_MISMATCH=1))
        self.assertEqual(r["recovery_outside_v18_range"],1)
        self.assertEqual(r["v18_outside_recovery_range"],0)
        self.assertFalse(r["regular_only_session_certified"])
        self.assertFalse(r["market_wide_independent_source_verified"])
        self.assertFalse(r["trade_approved"])
        self.assertEqual(r["decision"],"CASH")
        self.assertIn("POSSIBLE_NOT_PROVEN",r["suspicion_not_proof"])

    def test_truncated_conflict_roster_disallowed(self):
        p=parity(self.example())
        p["mismatch_tickers_complete"]=False
        self.assertFalse(analyze(p,ASOF)["diagnosis_valid"])

    def test_unlisted_conflict_detected_without_guessing(self):
        p=parity(self.example())
        p["mismatch_tickers"]=["000660","035420","005930"]
        self.assertFalse(analyze(p,ASOF)["diagnosis_valid"])
        self.assertIn("ROW_ROSTER_CLOSE_MISMATCH",
                      analyze(p,ASOF)["blocking_reasons"])

    def test_different_asof_fails(self):
        p=parity(self.example())
        self.assertFalse(analyze(p,"2026-10-22")["diagnosis_valid"])

    def test_duplicate_ohlc_row_rejected(self):
        rows=self.example()
        p=parity(rows+[copy.deepcopy(rows[0])])
        self.assertFalse(analyze(p,ASOF)["diagnosis_valid"])
        self.assertIn("DUPLICATE_OR_BAD_COMPARISON_TICKER",
                      analyze(p,ASOF)["blocking_reasons"])

    def test_impossible_price_rejected(self):
        rows=self.example()
        rows[0]["recovery_ohlc"]=[98,110,90,130]
        p=parity(rows)
        self.assertIn("NONPOSITIVE_OR_IMPOSSIBLE_OHLC",
                      analyze(p,ASOF)["blocking_reasons"])

    def test_no_minute_proof_must_not_promote_equal_close(self):
        r=analyze(parity(self.example()),ASOF)
        self.assertEqual(r["kis_regular_minute_evidence_count"],0)
        self.assertTrue(all(x["verified_regular_order_price"] is False for x in r["comparisons"]))

    def test_kis_matches_only_v18_and_never_approves_trades(self):
        rows=[price("005930",[98,110,90,106],[98,110,90,100])]
        r=analyze(parity(rows),ASOF,kis())
        self.assertTrue(r["diagnosis_valid"])
        self.assertEqual(r["kis_regular_minute_evidence_count"],1)
        self.assertEqual(r["comparisons"][0]["kis_adjudication"],
                         "KIS_J_MINUTE_CLOSE_MATCHES_V18_ONLY")
        self.assertFalse(r["comparisons"][0]["verified_regular_order_price"])
        self.assertFalse(r["trade_approved"])

    def test_wrong_kis_day_or_market_not_used(self):
        p=parity([price("005930",[98,110,90,106],[98,110,90,100])])
        q=kis(day="20261022")
        self.assertEqual(analyze(p,ASOF,q)["kis_regular_minute_evidence_count"],0)
        q=kis()
        q["regular_reconstructions"][0]["market_code"]="NX"
        self.assertEqual(analyze(p,ASOF,q)["kis_regular_minute_evidence_count"],0)

    def test_kis_missing_closing_auction_or_minute_coverage_rejected(self):
        q=kis()
        q["regular_reconstructions"][0]["last_minute"]="152900"
        self.assertEqual(probe_index(q,ASOF)[0],{})
        q=kis()
        q["regular_reconstructions"][0]["minutes_seen"]=40
        self.assertEqual(probe_index(q,ASOF)[0],{})

    def test_malformed_kis_row_or_unsafe_approval_rejected(self):
        q=kis()
        q["regular_reconstructions"][0]["trade_approved"]=True
        self.assertEqual(probe_index(q,ASOF)[0],{})
        q=kis()
        q["regular_reconstructions"][0]["duplicate_time_conflicts"]=1
        self.assertEqual(probe_index(q,ASOF)[0],{})

    def test_missing_kis_provenance_returns_research_only(self):
        x=parity(self.example())
        r=analyze(x,ASOF,{"date":"20261023","regular_reconstructions":[]})
        self.assertEqual(r["kis_regular_minute_evidence_count"],0)
        self.assertIn("KIS_AUDIT_SCHEMA_UNVERIFIED",r["blocking_reasons"])
        self.assertEqual(r["decision"],"CASH")

if __name__=="__main__":
    unittest.main()
