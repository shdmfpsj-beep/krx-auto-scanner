#!/usr/bin/env python3
"""C3 v6.30 independent research capital-quantity gate. Orders ALWAYS disabled.

This module cannot certify price contacts as fills. It calculates *hypothetical*
share capacity under a frozen cash/risk budget, for post-audit shadow ledgers.
Parent v6.29 strategy/ticker are fixed at D; do not reselect after D+1 open.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

SCHEMA="C3_V630_READ_ONLY_CAPITAL_RISK"
RESEARCH_FRICTION_PCT=.65

def affordable_shares(orderable_cash,entry,confirmed_daily_stop,risk_pct=1.0):
    """Shares subject to gross cash and loss-budget; gaps can exceed budget."""
    v=(orderable_cash,entry,confirmed_daily_stop,risk_pct)
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v):
        return 0
    if not(orderable_cash>0 and entry>0 and 0<confirmed_daily_stop<entry
           and 0<risk_pct<=5):return 0
    money_at_risk_per_share=(entry-confirmed_daily_stop)+(
        entry*RESEARCH_FRICTION_PCT/100)
    return max(0,min(math.floor(orderable_cash/entry),
        math.floor(orderable_cash*risk_pct/100/money_at_risk_per_share)))

def research_capacity(cash,entry,stop,risk_pct,cash_snapshot_verified=False):
    """Never bless a live trade; historical/assumed cash gets research status."""
    shares=affordable_shares(cash,entry,stop,risk_pct)
    return dict(schema=SCHEMA,research_qty=shares,
        expected_entry_notional_krw=round(shares*entry) if shares else 0,
        modeled_stop_budget_krw=round(shares*(
            entry-stop+entry*RESEARCH_FRICTION_PCT/100),2) if shares else 0,
        cash_snapshot_verified=bool(cash_snapshot_verified),
        confirmed_broker_fill=False,
        true_stop_slippage_known=False,
        source_krx_regular_session_attested=False,
        verified_overhead_net_2R=False,final_stock_80_verified=False,
        trade_approved=False,orders_enabled=False)

def hypothetical_close_entry_pnl(balance,entry,stop,exit_net_pct,risk_pct):
    """Update closed-trade virtual cash only; no mark-to-market data supplied."""
    if not all(isinstance(x,(int,float)) and math.isfinite(x)
        for x in (balance,entry,stop,exit_net_pct,risk_pct)):
        raise ValueError("INVALID_HYPOTHETICAL_ACCOUNT_VALUE")
    q=affordable_shares(balance,entry,stop,risk_pct)
    if q<=0:
        return dict(shares=0,new_cash=round(balance,2),
            modeled_pnl_krw=0,reason="CASH_MIN_ONE_SHARE_RISK")
    pnl=q*entry*exit_net_pct/100
    return dict(shares=q,new_cash=round(balance+pnl,2),
         modeled_pnl_krw=round(pnl,2),
         reason="RESEARCH_CLOSED_RETURN_NOT_BROKER_FILL")
