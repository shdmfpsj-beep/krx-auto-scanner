"""Fixture tests for research-only D-asof ranking; not a full backtest."""
import unittest
import pandas as pd
from gst_d_only_leader_rank_v633 import score_D,select_D_once,research_output_gate,RANKS

def signal_rows():
    return pd.DataFrame([
        dict(asof="2026-09-21",ticker="083450",model="NEAR60_RISK8",
          signal_score=3.8970033,riskD_pct=6.064,ret5=10.526,rv20=1.051,
          breakout_pct=1.046,rs5=4.559,rs20=2.792,
          turnover_accel=1.121,raw_turnover_bil=6),
        dict(asof="2026-09-21",ticker="074600",model="NEAR60_RISK8",
          signal_score=4.8611584,riskD_pct=6.541,ret5=12.305,rv20=1.203,
          breakout_pct=1.590,rs5=6.338,rs20=4.771,
          turnover_accel=1.304,raw_turnover_bil=8),
        dict(asof="2026-09-22",ticker="123456",model="NEAR60_RISK8",
          signal_score=1.23,riskD_pct=3,ret5=6,rv20=1.20,
          breakout_pct=1,rs5=3,rs20=2,turnover_accel=1,raw_turnover_bil=5)])

class TestV633(unittest.TestCase):
    def test_all_6_defined_ranks(self):self.assertEqual(len(RANKS),6)
    def test_no_buy_from_research(self):
        self.assertFalse(research_output_gate()["orders_enabled"])
        self.assertFalse(research_output_gate()["trade_approved"])
    def test_asof_future_mutation_no_effect(self):
        a=signal_rows();a["next_open"]=999999;a["realized_profit"]=99
        b=a.copy();b["next_open"]=-999;b["realized_profit"]=-99
        for r in RANKS:
            self.assertEqual(select_D_once(score_D(a),r).ticker.tolist(),
                             select_D_once(score_D(b),r).ticker.tolist())
    def test_group_one_stock(self):
        self.assertEqual(len(select_D_once(score_D(signal_rows()),"V632_BASE")),2)
    def test_gst_not_forced_first_in_original_and_major_variants(self):
        x=score_D(signal_rows())
        for r in ("V632_BASE","CONFIRMED_RS","MONEY_FLOW","BALANCED_LEADER"):
            y=select_D_once(x,r)
            self.assertEqual(y[y.asof=="2026-09-21"].ticker.iloc[0],"074600")
    def test_missing_D_feature(self):
        with self.assertRaises(ValueError):score_D(signal_rows().drop(columns=["rs5"]))
    def test_nonfinite_D_feature(self):
        q=signal_rows();q.loc[0,"rs20"]=float("nan")
        with self.assertRaises(ValueError):score_D(q)
    def test_invalid_negative_turnover(self):
        q=signal_rows();q.loc[0,"raw_turnover_bil"]=-1
        with self.assertRaises(ValueError):score_D(q)
    def test_invalid_risk(self):
        q=signal_rows();q.loc[0,"riskD_pct"]=0
        with self.assertRaises(ValueError):score_D(q)
    def test_unknown_rank_cannot_enter(self):
        with self.assertRaises(ValueError):select_D_once(score_D(signal_rows()),"FUTURE_ORACLE")
    def test_ticker_stable_tie(self):
        q=signal_rows();q.loc[0,"signal_score"]=q.loc[1,"signal_score"]
        y=select_D_once(score_D(q),"V632_BASE")
        self.assertEqual(y[y.asof=="2026-09-21"].ticker.iloc[0],"074600")
    def test_duplicate_signal_rejected(self):
        q=pd.concat([signal_rows(),signal_rows().iloc[[0]]],ignore_index=True)
        with self.assertRaises(ValueError):score_D(q)
    def test_empty_signals_rejected(self):
        with self.assertRaises(ValueError):score_D(signal_rows().iloc[:0])

if __name__=="__main__":unittest.main()
