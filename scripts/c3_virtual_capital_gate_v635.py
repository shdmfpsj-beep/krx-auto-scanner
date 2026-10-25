#!/usr/bin/env python3
"""C3 v6.35 1m KRW RESEARCH-only size calculator. No network or broker client.

A cash example is not an actual broker balance. NEVER use to authorize BUY.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

RESEARCH_START_KRW=1_000_000
RISK_FRACTION_DEFAULT=.01
FRICTION_FRACTION=.0065
STRESS_TOTAL_FRICTION_FRACTION=.0095
SCHEMA="C3_V635_1M_RESEARCH_ONLY_NO_ORDERS"

def paper_whole_share_qty(paper_equity_krw, verified_or_paper_cash_krw,
                          entry_krw, confirmed_daily_stop_krw,
                          account_risk_fraction=RISK_FRACTION_DEFAULT,
                          friction_fraction=FRICTION_FRACTION):
    """Notional bound and equity stop-budget bound; hard min 1 whole share.

    Risk is EQUITY risk, not fixed 1% STOCK price stop. Gaps can lose more.
    Daily pivot validity, PIT eligibility, liquidity and fill must be audited
    elsewhere before any human-assisted trade may even be considered.
    """
    xs=(paper_equity_krw,verified_or_paper_cash_krw,entry_krw,
        confirmed_daily_stop_krw,account_risk_fraction,friction_fraction)
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in xs):
        return 0
    if not(paper_equity_krw>0 and verified_or_paper_cash_krw>0 and
      0<confirmed_daily_stop_krw<entry_krw and 0<account_risk_fraction<=.03
      and 0<=friction_fraction<.03):return 0
    cash_cap=math.floor(verified_or_paper_cash_krw/entry_krw)
    per_share_risk=(entry_krw-confirmed_daily_stop_krw)+entry_krw*friction_fraction
    risk_cap=math.floor(paper_equity_krw*account_risk_fraction/per_share_risk)
    return max(0,min(cash_cap,risk_cap))

def virtual_budget_status(entry_krw,structure_stop_krw,
                          paper_equity_krw=RESEARCH_START_KRW,
                          paper_cash_krw=RESEARCH_START_KRW):
    qty=paper_whole_share_qty(paper_equity_krw,paper_cash_krw,
                               entry_krw,structure_stop_krw)
    projected_loss=qty*(entry_krw-structure_stop_krw+
                        entry_krw*FRICTION_FRACTION) if qty else 0
    return dict(schema=SCHEMA,virtual_starting_principal=RESEARCH_START_KRW,
       hypothetical_equity_krw=paper_equity_krw,
       hypothetical_cash_krw=paper_cash_krw,
       recommended_research_qty=qty,
       initial_risk_budget_krw=paper_equity_krw*RISK_FRACTION_DEFAULT,
       planned_stop_damage_krw=round(projected_loss,2),
       gap_or_unfilled_slippage_may_exceed_budget=True,
       source_krx_regular_only_verified=False,
       actual_Kiwoom_available_cash_verified=False,
       actual_broker_fill=False,actual_account_deposit=False,
       trade_approved=False,orders_enabled=False)
