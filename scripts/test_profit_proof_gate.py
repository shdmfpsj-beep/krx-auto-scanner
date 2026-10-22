#!/usr/bin/env python3
"""C3 profit research: show winners only after audit; never create live BUY."""
import copy,datetime,unittest
from profit_proof_gate import audit,lineage,check_account,markdown
from shadow_trade_audit import VERSION

def synthetic(n=32,losing_last=0):
    signal=[];results=[];trades=[]
    cash=1_000_000.0
    start=datetime.date(2026,1,5)
    for i in range(n):
        d=start+datetime.timedelta(days=4*i)
        day=d.isoformat()
        entry_d=(d+datetime.timedelta(days=1)).isoformat()
        ticker=f"{i:06d}"
        reference=dict(signal_date=day,ticker=ticker,plan_version=VERSION,
           signal_close=100.,signal_atr14=5.,stop_reference=90.,
           no_chase_reference=105.,prior_high=130.,research_proxy_index=90)
        sell=96 if i>=n-losing_last else 112
        ret=round(100*(sell/100-1)-0.4,3)
        signal.append(reference)
        results.append({**reference,"status":"CLOSED",
            "next_open_entry":100.,"exit_price":sell,"hold_sessions":1,
            "exit_reason":"HORIZON_5D_CLOSE",
            "net_return_pct":ret,"net_r":round(ret/10,3)})
        count=10;fee=0.2
        gain=round(count*(sell*(1-fee/100)-100*(1+fee/100)),2)
        trades.append(dict(signal_date=day,ticker=ticker,
            entry_date=entry_d,exit_date=entry_d,
            entry_krw=100.,exit_krw=sell,
            shares=count,entry_cash_before_krw=round(cash,2),
            simulated_cost_each_side_pct=fee,
            realized_pnl_krw=gain,planned_risk_krw=105))
        cash=round(cash+gain,2)
    account=dict(account_type="SYNTHETIC_PAPER_ACCOUNT_NOT_USER_BALANCE",
        integrity="OK",research_valid=True,
        starting_capital_krw=1_000_000.,
        ending_realised_equity_krw=cash,
        mark_to_market_mdd_pct=5.2,
        risk_budget_per_trade_pct=2.0,
        traded_positions=n,trades=trades)
    return signal,results,account

class ProfitProofTests(unittest.TestCase):
    def test_no_signals_is_cash_without_fabricated_return(self):
        x=audit([],[],{})
        self.assertEqual(x["profit_proof_status"],"AUDIT_INTEGRITY_FAILURE")
        self.assertIsNone(x["paper_mean_net_return_pct"])
        self.assertEqual(x["decision"],"CASH")
        self.assertFalse(x["trade_approved"])
        self.assertIn("CASH",markdown(x))
    def test_robust_synthetic_returns_are_paper_only_never_buy(self):
        s,r,a=synthetic()
        x=audit(s,r,a)
        self.assertTrue(x["integrity_pass"])
        self.assertTrue(x["sample_sufficiency_met"])
        self.assertEqual(x["completed_shadow_trades"],32)
        self.assertEqual(x["profit_proof_status"],
            "PROVISIONAL_PAPER_EDGE_NOT_LIVE_OR_OOS_PROVEN")
        self.assertGreater(x["date_cluster_bootstrap_5pct_lower_mean_stressed_pct"],0)
        self.assertGreater(x["last_quarter_chronological_trade_mean_stressed_pct"],0)
        self.assertFalse(x["real_account_profit_verified"])
        self.assertFalse(x["trade_approved"])
    def test_recent_holdout_losses_reject_in_sample_success(self):
        s,r,a=synthetic(losing_last=8)
        x=audit(s,r,a)
        self.assertEqual(x["profit_proof_status"],"PAPER_EDGE_NOT_ROBUST")
        self.assertLess(x["last_quarter_chronological_trade_mean_stressed_pct"],0)
        self.assertFalse(x["trade_approved"])
    def test_insufficient_completed_sample_cannot_prove_profit(self):
        s,r,a=synthetic(n=12)
        x=audit(s,r,a)
        self.assertEqual(x["profit_proof_status"],"INSUFFICIENT_PROSPECTIVE_EVIDENCE")
        self.assertFalse(x["sample_sufficiency_met"])
        self.assertIsNone(x["date_cluster_bootstrap_5pct_lower_mean_stressed_pct"])
    def test_duplicate_result_not_double_counted(self):
        s,r,a=synthetic()
        x=audit(s,r+[r[0]],a)
        self.assertEqual(x["completed_shadow_trades"],32)
        self.assertEqual(x["profit_proof_status"],"AUDIT_INTEGRITY_FAILURE")
        self.assertIn("DUPLICATE_OUTCOME_ID",x["blockers"])
    def test_unregistered_hindsight_result_cannot_inflate_win_rate(self):
        s,r,a=synthetic()
        r.append({**r[0],"ticker":"999999","net_return_pct":1000})
        x=audit(s,r,a)
        self.assertEqual(x["completed_shadow_trades"],32)
        self.assertIn("RESULT_NOT_IN_LOCKED_SIGNAL_LEDGER",x["blockers"])
    def test_changed_stop_after_signal_is_integrity_error(self):
        s,r,a=synthetic()
        r[0]["stop_reference"]=80
        x=audit(s,r,a)
        self.assertIn("RESULT_CHANGED_LOCKED_SIGNAL_PARAMETERS",x["blockers"])
        self.assertFalse(x["integrity_pass"])
    def test_forged_closed_return_fails_arithmetic(self):
        s,r,a=synthetic()
        r[0]["net_return_pct"]=99.
        x=audit(s,r,a)
        self.assertIn("CLOSED_RESULT_NET_ARITHMETIC_MISMATCH",x["blockers"])
    def test_paper_account_fake_profit_is_rejected(self):
        s,r,a=synthetic()
        a["trades"][0]["realized_pnl_krw"]+=500000
        x=audit(s,r,a)
        self.assertIn("ACCOUNT_REALISED_PNL_ARITHMETIC_MISMATCH",x["blockers"])
        self.assertIn("ACCOUNT_CASH_CHAIN_BROKEN",x["blockers"])
    def test_account_overleveraged_trade_blocks_edge_claim(self):
        s,r,a=synthetic()
        a["trades"][0]["shares"]=200000
        x=audit(s,r,a)
        self.assertIn("ACCOUNT_CAPITAL_OVERSPEND",x["blockers"])
    def test_account_missing_research_integrity_blocks_profit_claim(self):
        s,r,a=synthetic()
        a["integrity"]="MISSING_INTERMEDIATE_SESSION_PRICE"
        a["research_valid"]=False
        x=audit(s,r,a)
        self.assertIn("ACCOUNT_SESSION_OR_PRICE_INTEGRITY_UNVERIFIED",x["blockers"])
    def test_high_mdd_fails_quality_gate_without_data_error(self):
        s,r,a=synthetic()
        a["mark_to_market_mdd_pct"]=17
        x=audit(s,r,a)
        self.assertTrue(x["integrity_pass"])
        self.assertEqual(x["profit_proof_status"],"PAPER_EDGE_NOT_ROBUST")
    def test_closed_missing_entry_is_not_a_profitable_trade(self):
        s,r,a=synthetic()
        r[0]["next_open_entry"]=None
        x=audit(s,r,a)
        self.assertEqual(x["completed_shadow_trades"],31)
        self.assertIn("CLOSED_RESULT_MISSING_EXECUTION",x["blockers"])
    def test_missing_result_is_pending_not_backfilled(self):
        s,r,a=synthetic()
        closed,report=lineage(s,r[:-2])
        self.assertEqual(len(closed),30)
        self.assertEqual(report["pending_or_missing"],2)
    def test_only_one_month_of_good_signals_fails_calendar_span(self):
        s,r,a=synthetic(n=32)
        for i in range(32):
            date_=(datetime.date(2026,10,1)+datetime.timedelta(days=i))
            s[i]["signal_date"]=str(date_)
            r[i]["signal_date"]=str(date_)
            a["trades"][i]["signal_date"]=str(date_)
            a["trades"][i]["entry_date"]=str(date_+datetime.timedelta(days=1))
            a["trades"][i]["exit_date"]=str(date_+datetime.timedelta(days=1))
        x=audit(s,r,a)
        self.assertFalse(x["sample_sufficiency_met"])
        self.assertIn("MIN_SAMPLE_OR_SPAN_NOT_MET",x["blockers"])

if __name__=="__main__":unittest.main()
