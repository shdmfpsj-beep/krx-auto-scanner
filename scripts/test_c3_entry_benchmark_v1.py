"""Synthetic regression cases; never a market-performance evidence source."""
import csv
import json
import math
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path

from c3_entry_benchmark_v1 import (read_bars,load_panel,locate_entry,outcome,
    simulate_exit,net_return,make_decision,run_benchmark,variant_plan,sha,TRAIN_END,write_outputs,summarize)
from c3_ict_sequence_research_v1 import detect


def b(day,o=106,h=108,l=102,c=104,v=100):
    return dict(date=day,open=o,high=h,low=l,close=c,volume=v)


PLAN=dict(plan_id="fixture",ticker="TEST",decision_date="2026-06-01",
          watch_low=99,watch_high=100,structure_stop=95,resistance1=120)
ENTRY=dict(status="MODEL_ENTRY",date="2026-06-02",price=100)
DAYS=["2026-06-%02d"%i for i in range(1,10)]


def history(n=320):
    start=date(2025,8,11);days=[]
    while len(days)<n:
        if start.weekday()<5:
            days.append(str(start))
        start+=timedelta(days=1)
    return [b(d,100+i*.25+3*math.sin(i/6)-.3,
              102+i*.25+3*math.sin(i/6),98+i*.25+3*math.sin(i/6),
              100+i*.25+3*math.sin(i/6),1000+100*math.sin(i/7)) for i,d in enumerate(days)]


class EntryBenchmarkTests(unittest.TestCase):
    def test_gap_below_band_is_not_a_favorable_assumed_fill(self):
        r=locate_entry(PLAN,[b(DAYS[1],98,105,97,104)],DAYS)
        self.assertEqual(r["status"],"GAP_BELOW_BAND")

    def test_gap_below_stop_cancels(self):
        self.assertEqual(locate_entry(PLAN,[b(DAYS[1],90,105,89,100)],DAYS)["status"],"GAP_BELOW_STOP")

    def test_entry_stop_collision_excluded(self):
        r=locate_entry(PLAN,[b(DAYS[1],104,110,94,105)],DAYS)
        self.assertEqual(r["status"],"ENTRY_STOP_ORDER_UNKNOWN")

    def test_zero_volume_cannot_fill(self):
        r=locate_entry(PLAN,[b(d,100,105,99,104,0) for d in DAYS[1:6]],DAYS)
        self.assertEqual(r["status"],"EXPIRED_NO_TOUCH")

    def test_missing_session_cannot_be_replaced_by_later_touch(self):
        r=locate_entry(PLAN,[b(DAYS[2],100,105,99,104)],DAYS)
        self.assertEqual(r["status"],"DATA_GAP")
        self.assertEqual(r["missing_date"],DAYS[1])

    def test_early_touch_survives_short_watch_window(self):
        rows=[b(DAYS[1],100,105,99,104)]
        entry=locate_entry(PLAN,rows,DAYS[:2])
        self.assertEqual(entry["status"],"MODEL_ENTRY")
        self.assertFalse(outcome(PLAN,entry,rows,DAYS[:2],5)["complete"])

    def test_no_touch_short_window_pending(self):
        self.assertEqual(locate_entry(PLAN,[b(DAYS[1],110,112,109,111)],DAYS[:2])["status"],"PENDING")

    def test_intraday_gap_loss_can_exceed_structure_stop(self):
        rows=[b(d,90,94,88,91) for d in DAYS[2:7]]
        r=simulate_exit(PLAN,ENTRY,rows,DAYS,5,"INTRADAY")
        self.assertEqual(r["exit_reason"],"GAP_STOP")
        self.assertLess(r["hypothetical_net_pct"],-10)

    def test_close_stop_exits_next_exact_open(self):
        rows=[b(DAYS[2],100,102,93,94),b(DAYS[3],89,95,88,94)]+[b(d) for d in DAYS[4:7]]
        r=simulate_exit(PLAN,ENTRY,rows,DAYS,5,"CLOSE")
        self.assertEqual(r["exit_price"],89)
        self.assertEqual(r["exit_date"],DAYS[3])

    def test_untradable_next_open_is_censored_not_deferred_to_better_open(self):
        rows=[b(DAYS[2],100,102,93,94),b(DAYS[3],94,94,94,94,0)]+[b(d,120,122,119,121) for d in DAYS[4:7]]
        r=simulate_exit(PLAN,ENTRY,rows,DAYS,5,"CLOSE")
        self.assertFalse(r["complete"])
        self.assertEqual(r["reason"],"NEXT_OPEN_UNTRADABLE_AFTER_CLOSE_STOP")

    def test_missing_exit_session_is_censored(self):
        rows=[b(d) for d in DAYS[2:7] if d!=DAYS[3]]
        self.assertFalse(simulate_exit(PLAN,ENTRY,rows,DAYS,5)["complete"])

    def test_same_day_stop_target_uses_conservative_order(self):
        rows=[b(DAYS[2],100,112,94,105)]+[b(d) for d in DAYS[3:7]]
        r=simulate_exit(PLAN,ENTRY,rows,DAYS,5,"INTRADAY","TAKE10")
        self.assertEqual(r["exit_price"],95)
        self.assertTrue(r["same_bar_order_conservative"])

    def test_open_above_target_precedes_later_stop(self):
        rows=[b(DAYS[2],112,115,94,105)]+[b(d) for d in DAYS[3:7]]
        r=simulate_exit(PLAN,ENTRY,rows,DAYS,5,"INTRADAY","TAKE10")
        self.assertEqual(r["exit_reason"],"OPEN_ABOVE_TAKE10_CONSERVATIVE")
        self.assertAlmostEqual(r["exit_price"],110)
        self.assertFalse(r["same_bar_order_conservative"])

    def test_entry_day_high_cannot_be_taken_as_post_entry_profit(self):
        rows=[b(DAYS[1],100,125,99,115)]+[b(d,104,105,102,104) for d in DAYS[2:7]]
        r=simulate_exit(PLAN,ENTRY,rows,DAYS,5,"CLOSE","TAKE10")
        self.assertEqual(r["exit_reason"],"HORIZON_CLOSE_MARK")
        self.assertFalse(outcome(PLAN,ENTRY,rows,DAYS,5)["target10"])

    def test_costs_are_charged_on_both_sides(self):
        self.assertAlmostEqual(net_return(100,100),100*(.995/1.0015-1))
        with self.assertRaises(ValueError):
            net_return(100,100,buy_cost=-.1)

    def test_rebound_cannot_read_past_the_frozen_horizon(self):
        rows=[b(d,102,105,100,104) for d in DAYS[2:6]]
        rows.extend([b(DAYS[6],98,100,94,96),b(DAYS[7],105,109,101,108),b(DAYS[8],105,109,101,108)])
        r=outcome(PLAN,ENTRY,rows,DAYS,5)
        self.assertTrue(r["stop_touched"])
        self.assertIsNone(r["stop_rebound_1_2_sessions"])

    def test_market_reference_uses_only_matching_decision_dates(self):
        rows=history(180)
        i=next(i for i in range(65,120) if make_decision("TEST",rows,i,detect(rows)))
        market=[dict(x,open=x["open"]*2,high=x["high"]*2,low=x["low"]*2,close=x["close"]*2) for x in rows]
        p=make_decision("TEST",rows,i,detect(rows),market)
        self.assertAlmostEqual(p["context"]["rs20_pct"],0)
        future_changed=market[:i+1]+[b(x["date"],1000,2000,1,1500) for x in market[i+1:]]
        self.assertEqual(make_decision("TEST",rows,i,detect(rows),future_changed),p)

    def test_favorable_and_adverse_excursions_include_zero_at_entry(self):
        rising=[b(d,110,115,109,112) for d in DAYS[2:7]]
        falling=[b(d,90,94,88,91) for d in DAYS[2:7]]
        self.assertEqual(outcome(PLAN,ENTRY,rising,DAYS,5)["mae_pct"],0)
        self.assertEqual(outcome(PLAN,ENTRY,falling,DAYS,5)["mfe_pct"],0)

    def test_target_after_stop_is_not_a_stop_surviving_winner(self):
        rows=[b(DAYS[2],100,102,94,98),b(DAYS[3],110,121,109,119)]+[b(d) for d in DAYS[4:7]]
        r=outcome(PLAN,ENTRY,rows,DAYS,5)
        self.assertTrue(r["target10"])
        self.assertFalse(r["target10_before_stop"])
        self.assertFalse(r["target10_order_unknown"])

    def test_daily_stop_target_collision_cannot_be_a_verified_target_first(self):
        rows=[b(DAYS[2],100,112,94,105)]+[b(d) for d in DAYS[3:7]]
        r=outcome(PLAN,ENTRY,rows,DAYS,5)
        self.assertFalse(r["target10_before_stop"])
        self.assertTrue(r["target10_order_unknown"])

    def test_observed_open_can_resolve_target_before_later_stop(self):
        rows=[b(DAYS[2],112,115,94,105)]+[b(d) for d in DAYS[3:7]]
        r=outcome(PLAN,ENTRY,rows,DAYS,5)
        self.assertTrue(r["target10_before_stop"])
        self.assertFalse(r["target10_order_unknown"])

    def test_exact_ten_percent_touch_is_not_lost_to_float_rounding(self):
        rows=[b(DAYS[2],100,110,99,108)]+[b(d) for d in DAYS[3:7]]
        self.assertTrue(outcome(PLAN,ENTRY,rows,DAYS,5)["target10_before_stop"])
        self.assertEqual(simulate_exit(PLAN,ENTRY,rows,DAYS,5,"CLOSE","TAKE10")["exit_price"],110)

    def test_intraday_touch_and_actual_close_stop_exit_are_separate_metrics(self):
        rows=[b(d,100,105,94,101) for d in DAYS[2:7]]
        exits={mode+'_'+style:simulate_exit(PLAN,ENTRY,rows,DAYS,5,mode,style)
               for mode in ('CLOSE','INTRADAY') for style in ('HOLD','TAKE10','TREND20')}
        record=dict(fold='HOLDOUT',entry=ENTRY,outcomes={'5':outcome(PLAN,ENTRY,rows,DAYS,5)},exits={'5':exits})
        s=summarize([record],1,5,'HOLDOUT')
        self.assertEqual(s['stop_touch_rate_pct'],100)
        self.assertEqual(s['exit_models']['CLOSE_HOLD']['stop_exit_rate_pct'],0)
        self.assertEqual(s['exit_models']['INTRADAY_HOLD']['stop_exit_rate_pct'],100)

    def test_future_prices_cannot_change_frozen_plan_or_features(self):
        rows=history(180)
        picks=[i for i in range(65,120) if make_decision("TEST",rows,i,detect(rows))]
        self.assertTrue(picks)
        i=picks[0]
        frozen=make_decision("TEST",rows[:i+1],i,detect(rows[:i+1]))
        altered=rows[:i+1]+[b(x["date"],1000,2000,1,1500,999999) for x in rows[i+1:]]
        self.assertEqual(make_decision("TEST",altered,i,detect(altered)),frozen)

    def test_same_stop_used_by_all_entry_variants_without_three_percent_cap(self):
        rows=history(180)
        p=next(p for i in range(65,120) if (p:=make_decision("TEST",rows,i,detect(rows))))
        ma,_=variant_plan(p,"C3_MA20")
        self.assertIsNotNone(ma)
        self.assertEqual(ma["structure_stop"],p["structure_stop"])

    def test_shared_cooldown_and_purged_development_horizons(self):
        rows=history();days=[x["date"] for x in rows]
        r=run_benchmark({"TEST":rows},days)
        self.assertTrue(r["decisions"])
        indices=[days.index(p["decision_date"]) for p in r["decisions"]]
        self.assertTrue(all(y-x>=26 for x,y in zip(indices,indices[1:])))
        for p in r["decisions"]:
            if p["fold"]=="DEVELOPMENT":
                self.assertLessEqual(days[days.index(p["decision_date"])+25],TRAIN_END)
        self.assertFalse(r["strategy_profitability_verified"])

    def test_nonfinite_volume_rejected_at_data_boundary(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"bad.csv"
            with path.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(b(DAYS[1])));w.writeheader();w.writerow(b(DAYS[1],v=float("inf")))
            with self.assertRaisesRegex(ValueError,"INVALID_OHLCV"):
                read_bars(path)

    def test_hash_mismatch_does_not_enter_research_cohort(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/"TEST.csv"
            with p.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(b(DAYS[1])));w.writeheader();w.writerow(b(DAYS[1]))
            manifest=root/"manifest.json";calendar=root/"calendar.json"
            manifest.write_text(json.dumps(dict(records=[dict(ticker="TEST",sha256="bad",bars=1,price_date=DAYS[1])])) )
            calendar.write_text(json.dumps(dict(dates=DAYS)))
            with self.assertRaisesRegex(ValueError,"NO_AUDITABLE_HISTORY"):
                load_panel(root,manifest,calendar)

    def test_report_csv_handles_empty_and_nonempty_cohorts_with_same_columns(self):
        rows=history()
        r=run_benchmark({"TEST":rows},[b["date"] for b in rows])
        with tempfile.TemporaryDirectory() as t:
            write_outputs(r,t)
            with (Path(t)/"strategy_comparison.csv").open() as f:
                summary=list(csv.DictReader(f))
            self.assertEqual(len(summary),72)
            self.assertNotIn(None,summary[0])
            self.assertIn("records",r)


if __name__=="__main__":
    unittest.main()
