"""C3 forward paper ledger tests. Synthetic dates/prices are NOT market results."""
import csv,json,tempfile,unittest
from pathlib import Path
from c3_paper_forward_v1 import run

PLAN=dict(plan_id="C3-20261030-271560",ticker="271560",name="오리온",
 selection_date="2026-10-30",registered_day="2026-10-31",
 source_run_id="41051723762",source_close=114200,
 watch_low=110900,watch_high=113700,structure_stop=109600,
 target1=131500,target2=141700,expires_after_sessions=5,
 source_scope="PYKRX_RESEARCH_REGULAR_ONLY_UNCERTIFIED",
 stop_rule="NEXT_OPEN_AFTER_CLOSE_BELOW_STOP")

def mock(ticker,date,open,high,low,close,volume=250000):
    return dict(ticker=ticker,date=date,open=open,high=high,low=low,
                close=close,volume=volume)

class ForwardTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.plans=self.root/"plans.csv";self.prices=self.root/"prices.csv"
        self.ledger=self.root/"paper.json"
        with self.plans.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(PLAN));w.writeheader();w.writerow(PLAN)

    def tick(self,today,bars,scan_day=None):
        with self.prices.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=["ticker","date","open","high","low","close","volume"])
            w.writeheader();w.writerows(bars)
        return run(self.plans,self.prices,self.ledger,self.root/"out",
                   today,scan_day if scan_day is not None else today)

    def view(self):
        return json.loads(self.ledger.read_text(encoding="utf-8"))

    def test_five_forward_sessions_are_observed_not_invented(self):
        first=mock("271560","2026-11-02",114000,114500,112000,113500)
        rows=[first]
        self.tick("2026-11-02",rows)
        days=["2026-11-03","2026-11-04","2026-11-05",
              "2026-11-06","2026-11-09"]
        for k,day in enumerate(days):
            rows.append(mock("271560",day,114000+k*100,
                             115500+k*100,112000+k*100,114300+k*100))
            x=self.tick(day,rows)
        p=x["positions"][0]
        self.assertEqual(p["held_sessions"],5)
        self.assertIsNotNone(p["net_return_after_5_sessions_pct"])
        self.assertIsNone(p["net_return_after_10_sessions_pct"])
        self.assertIsNone(p["net_return_after_20_sessions_pct"])
        self.assertEqual(sum(e["event"]=="FORWARD_5_SESSIONS_MARKED_AT_CLOSE"
           for e in self.view()["events"]),1)
        again=self.tick("2026-11-09",rows)
        self.assertEqual(x["events_total"],again["events_total"])

    def test_no_registration_day_hindsight_buy(self):
        b=mock("271560","2026-10-30",112000,115000,110000,114200)
        x=self.tick("2026-10-31",[b],"2026-10-30")
        self.assertEqual(x["positions"][0]["status"],"WAITING")
        self.assertEqual(x["events_total"],0)

    def test_first_future_touch_opens_only_hypothetical_entry(self):
        b=mock("271560","2026-11-02",115000,133000,112900,127000)
        x=self.tick("2026-11-02",[b])
        self.assertEqual(x["positions"][0]["sim_entry_price"],113700)
        self.assertEqual(x["positions"][0]["status"],"OPEN")
        kinds=[e["event"] for e in self.view()["events"]]
        self.assertIn("PAPER_ENTRY_ASSUMED_ON_DAILY_OHLC",kinds)
        self.assertIn("ENTRY_BAR_TARGET_ORDER_UNKNOWN",kinds)
        self.assertNotIn("FIRST_TARGET_HALF_UNIT_ASSUMED",kinds)
        self.assertFalse(x["buy_approved"])

    def test_one_T1_and_T2_on_later_session_with_fractional_book(self):
        prev=mock("271560","2026-11-02",114000,115000,112000,113500)
        x=self.tick("2026-11-02",[prev])
        nxt=mock("271560","2026-11-03",135000,144000,130000,140000)
        y=self.tick("2026-11-03",[prev,nxt])
        self.assertEqual(y["positions"][0]["status"],"CLOSED_T2")
        self.assertEqual(y["positions"][0]["remaining_fraction"],0)
        self.assertEqual(y["positions"][0]["target1_date"],"2026-11-03")
        self.assertEqual(y["positions"][0]["target2_date"],"2026-11-03")
        kinds=[e["event"] for e in self.view()["events"]]
        self.assertIn("SECOND_TARGET_REST_UNIT_ASSUMED",kinds)

    def test_close_stop_requires_next_real_observed_open(self):
        first=mock("271560","2026-11-02",114000,114000,108000,109000)
        x=self.tick("2026-11-02",[first])
        self.assertEqual(x["positions"][0]["status"],"STOP_PENDING")
        self.assertIsNone(x["positions"][0]["stop_exit_date"])
        nxt=mock("271560","2026-11-03",104000,106000,100000,103000)
        y=self.tick("2026-11-03",[first,nxt])
        self.assertEqual(y["positions"][0]["status"],"CLOSED_STOP")
        self.assertEqual(y["positions"][0]["stop_exit_date"],"2026-11-03")
        self.assertEqual(self.view()["positions"][PLAN["plan_id"]]["exit_price"],104000)

    def test_missed_target_before_band_entry_cancels_new_buy(self):
        # A rally that does not descend into the pre-registered buy band
        # is a missed opportunity, never rewritten as a filled winner.
        b=mock("271560","2026-11-02",126000,134000,124000,132000)
        x=self.tick("2026-11-02",[b])
        self.assertEqual(x["positions"][0]["status"],"CANCELLED_TARGET_BEFORE_ENTRY")
        self.assertIsNone(x["positions"][0]["sim_entry_date"])
        self.assertIn("MISSED_NO_FILL_FIRST_RESISTANCE_VISITED",
                      [e["event"] for e in self.view()["events"]])

    def test_stop_breached_before_first_buy_cancels_plan(self):
        b=mock("271560","2026-11-02",108000,109000,107000,108000)
        x=self.tick("2026-11-02",[b])
        self.assertEqual(x["positions"][0]["status"],"CANCELLED_STOP_BEFORE_ENTRY")
        self.assertIsNone(x["positions"][0]["sim_entry_date"])

    def test_gap_below_band_skips_even_if_high_reaches_band(self):
        b=mock("271560","2026-11-02",108000,112000,106000,111000)
        x=self.tick("2026-11-02",[b])
        self.assertEqual(x["positions"][0]["status"],"WAITING")
        self.assertIn("GAP_OPEN_BELOW_BAND_SKIPPED",
                      [e["event"] for e in self.view()["events"]])

    def test_missing_daily_full_market_scan_never_creates_fill(self):
        b=mock("271560","2026-11-02",114000,114200,112000,113500)
        x=self.tick("2026-11-02",[b],"2026-10-30")
        self.assertEqual(x["positions"][0]["status"],"WAITING")
        self.assertEqual(x["events_total"],0)

    def test_idempotent_same_source_session(self):
        b=mock("271560","2026-11-02",114000,114200,112000,113500)
        x=self.tick("2026-11-02",[b])
        y=self.tick("2026-11-02",[b])
        self.assertEqual(x["events_total"],y["events_total"])
        self.assertEqual(y["positions"][0]["status"],"OPEN")

    def test_immutable_plan_does_not_change_past_fill(self):
        b=mock("271560","2026-11-02",114000,114200,112000,113500)
        self.tick("2026-11-02",[b])
        edited=dict(PLAN,watch_high=113600)
        with self.plans.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(edited));w.writeheader();w.writerow(edited)
        with self.assertRaisesRegex(ValueError,"IMMUTABLE_REGISTERED_PLAN_MODIFIED"):
            self.tick("2026-11-03",[b],"2026-11-03")

    def test_no_backfilled_missing_session_after_stop(self):
        first=mock("271560","2026-11-02",114000,114000,108000,109000)
        self.tick("2026-11-02",[first])
        missing=mock("271560","2026-11-03",105000,108000,100000,102000)
        future=mock("271560","2026-11-04",120000,140000,111000,135000)
        # The 11/03 bar is present in the later historical fetch but was not
        # observed on 11/03; reject using the favorable 11/04 open instead.
        x=self.tick("2026-11-04",[first,missing,future])
        self.assertEqual(x["positions"][0]["status"],"STOP_OPEN_MISSED_UNVERIFIABLE")
        self.assertIsNone(x["positions"][0]["stop_exit_date"])

    def test_no_new_weekend_trading_session_replayed(self):
        first=mock("271560","2026-11-02",114000,114500,112000,113500)
        x=self.tick("2026-11-02",[first])
        nxt=self.tick("2026-11-07",[first],"2026-11-06")
        self.assertEqual(x["events_total"],nxt["events_total"])
        self.assertEqual(nxt["positions"][0]["status"],"OPEN")

if __name__=="__main__":unittest.main()
