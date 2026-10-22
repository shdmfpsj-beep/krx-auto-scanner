"""One source of truth for explicit user-reported C3 position changes.

No brokerage reconciliation is implied; unknown fills, cash and P&L stay unknown.
"""
import json
from pathlib import Path

DEFAULT_FILE=Path("config/c3_position_state.json")

def load_c3_position(path=DEFAULT_FILE):
    try:
        raw=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError):
        return {"status":"POSITION_UNVERIFIED","user_reported":False}
    closed=raw.get("closed_position") or {}
    if (raw.get("schema")!="c3_user_reported_position_v1" or
        raw.get("source")!="USER_EXPLICIT_REPORT" or
        closed.get("ticker")!="004490" or
        closed.get("action")!="SELL_ALL" or
        closed.get("remaining_shares")!=0 or
        closed.get("prior_thesis")!="RETIRED"):
        return {"status":"POSITION_UNVERIFIED","user_reported":False}
    return {"status":"CASH_USER_REPORTED_NOT_BROKER_VERIFIED",
            "user_reported":True,
            "reported_date":str(raw.get("reported_date","")),
            "closed_ticker":"004490","closed_name":"세방전지",
            "closed_shares_remaining":0,"prior_thesis_active":False,
            "reported_current_positions":[],
            "exit_price_krw":None,"realized_profit_krw":None,
            "orderable_cash_krw":None,
            "trade_approved":False}

def c3_mobile_line(state):
    if state.get("user_reported") is True and state.get("closed_ticker")=="004490":
        return ("**C3 사용자 보고:** 세방전지(004490) 전량 매도·기존 관점 폐기. "
                "C3 무보유(CASH, 사용자 보고 기준); 매도단가·실현손익·실제 주문가능현금 미확인. "
                "과거 세방전지 관점으로 후보를 우대하거나 보유종목으로 취급하지 않음.")
    return "**C3 포지션:** 최신 사용자 보고/계좌 확인 자료 미확보."
