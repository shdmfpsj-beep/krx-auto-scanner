#!/usr/bin/env python3
"""Send one vetted C3 TOP2 Telegram alert per completed KRX trading date.

All messages are research-only/CASH; no broker access. GitHub receipts are
claimed before sending to prevent retry storms. Failed sends require manual
review rather than blindly duplicating potentially delivered messages.
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

REPO = "shdmfpsj-beep/krx-auto-scanner"
BRANCH = "research/c3-ledger-integrity-audit-20261104"
ROOT = "reports/c3_forward_v8"
KST = ZoneInfo("Asia/Seoul")


def now_kst():
    return datetime.now(KST)


def expected_session(day):
    """Only a completed trading-day candidate, not a holiday calendar."""
    if day.weekday() >= 5:
        return None
    d = day.date()
    if day.hour < 16:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d.isoformat()


def github_api(path, token, payload=None):
    url = "https://api.github.com/repos/" + REPO + "/" + path
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "c3-top2-telegram-research",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def read_report(token, filename):
    path = "contents/" + urllib.parse.quote(ROOT + "/" + filename, safe="/") + "?ref=" + urllib.parse.quote(BRANCH, safe="")
    payload = github_api(path, token)
    if payload.get("encoding") != "base64" or not payload.get("content"):
        raise ValueError("INVALID_REPOSITORY_REPORT_ENCODING")
    return json.loads(base64.b64decode(payload["content"]))


def receipt_path(asof):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", asof):
        raise ValueError("INVALID_SESSION_DATE")
    return ROOT + "/telegram_receipts/" + asof + ".json"


def write_receipt(token, asof, receipt, sha=None):
    path = "contents/" + urllib.parse.quote(receipt_path(asof), safe="/")
    data = {
        "branch": BRANCH,
        "message": "research: C3 Telegram delivery receipt for " + asof + " (no orders)",
        "content": base64.b64encode((json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n").encode()).decode(),
    }
    if sha:
        data["sha"] = sha
    return github_api(path, token, data)["content"]["sha"]


def receipt_exists(token, asof):
    path = "contents/" + urllib.parse.quote(receipt_path(asof), safe="/") + "?ref=" + urllib.parse.quote(BRANCH, safe="")
    try:
        github_api(path, token)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def iso_timestamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def report_error(latest, summary, current):
    asof = latest.get("source_price_asof", "")
    if asof != expected_session(current):
        return "NO_NEW_COMPLETED_SESSION"
    if summary.get("source_price_asof") != asof:
        return "SUMMARY_DATE_MISMATCH"
    if summary.get("source_run_id") != latest.get("source_run_id"):
        return "RUN_ID_MISMATCH"
    if summary.get("generated_at") != latest.get("generated_at"):
        return "REPORT_VERSION_MISMATCH"
    if latest.get("data_quality_state") != "OFFICIAL_VERIFIED":
        return "UNVERIFIED_MARKET_DATA"
    if latest.get("source_quality_gate", {}).get("status") != "QUALITY_GATE_PASSED":
        return "SOURCE_QUALITY_GATE_FAILED"
    if latest.get("errors"):
        return "REPORT_HAS_UNRESOLVED_ERRORS"
    if latest.get("source_provider") != "KRX_OFFICIAL_EOD":
        return "UNAPPROVED_PRICE_PROVIDER"
    scope = latest.get("current_scope", {})
    rows = latest.get("source_quality_gate", {}).get("markets", {})
    if scope.get("analysis_eligible", 0) <= 0 or scope.get("price_rows", 0) <= 0:
        return "EMPTY_ANALYSIS_SCOPE"
    if sum(m.get("rows", 0) for m in rows.values()) != scope["price_rows"]:
        return "MARKET_ROW_COUNT_MISMATCH"
    if latest.get("orders_enabled") or latest.get("current_action") != "CASH":
        return "LIVE_ORDER_OR_ACTION_POLICY_VIOLATION"
    try:
        age = current.astimezone(timezone.utc) - iso_timestamp(latest.get("generated_at", ""))
    except (ValueError, TypeError):
        return "INVALID_REPORT_GENERATION_TIME"
    if not timedelta(0) <= age <= timedelta(hours=30):
        return "STALE_OR_FUTURE_REPORT"
    return None


def number(value):
    try:
        return f"{int(value):,}원"
    except (TypeError, ValueError):
        return "미확인"


def build_message(latest, summary):
    asof = latest["source_price_asof"]
    scope = latest["current_scope"]
    received = iso_timestamp(latest["source_received_at"]).astimezone(KST).strftime("%m/%d %H:%M KST")
    registered = int(latest.get("new_registered_signals") or 0)
    is_registered = bool(latest.get("research_top2_registered_for_source_session"))
    header = [
        "📊 C3 TOP2 정규장 연구 보고",
        "원본 거래일: " + asof,
        "",
    ]
    picks = latest.get("research_top2") or []
    if not picks:
        header.append("연구 TOP2: 조건 충족 후보 없음")
    for i, item in enumerate(picks[:2], 1):
        name = str(item.get("name") or "종목명 미확인")[:60]
        ticker = str(item.get("ticker") or "")
        status = "전방 등록" if is_registered else "미등록 미리보기"
        header.extend([f"TOP{i} | {name} ({ticker}) [{status}]",
                       "확인 종가: " + number(item.get("close"))])
        factors = item.get("selection_reasons") or []
        labels = {"CLOSE_GT_MA20_GT_MA50": "종가 > 20일선 > 50일선", "POSITIVE_OWN_BOARD_RS20": "시장 대비 상대강도 우위", "TURNOVER20_RANK": "최근 20일 거래대금 상위권", "OWN_BOARD_RS_IMPROVING_5": "최근 5일 상대강도 개선"}
        header.append("선정 근거:")
        header.extend("• " + labels[f] for f in factors if f in labels)
        for key, label in (("rs20", "20일 상대강도"), ("rs_accel5", "5일 상대강도 개선")):
            value = item.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                header.append(f"• {label} {value:+.1f}%p")
        if not factors and not any(isinstance(item.get(k), (int, float)) for k in ("rs20", "rs_accel5")):
            header.append("• 상세 근거 미확인")
        entry = ((item.get("entry_plans") or {}).get("A_SUPPORT_LIMIT") or {}).get("plan")
        if entry:
            header.append("매수 관찰범위: " + number(entry.get("low")) + " ~ " + number(entry.get("high")))
            header.append("구조손절: " + number(entry.get("stop")))
            header.append("1차 / 2차 저항: " + number(entry.get("resistance")) + " / " + number(entry.get("resistance2")))
        else:
            header.append("매수 타점: 진입 조건 미성립·확인 대기")
        header.append("")
    header.extend([
        "⚪ 실전 판단: CASH (매수 승인이 아닌 연구 정보)",
        "가상매매는 실제 체결이 아닙니다.",
    ])
    text = "\n".join(header)
    if len(text) > 3900:
        raise ValueError("TELEGRAM_MESSAGE_TOO_LONG")
    return text


def telegram_api(bot_token, method, body=None):
    url = "https://api.telegram.org/bot" + bot_token + "/" + method
    data = json.dumps(body or {}, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise ValueError("TELEGRAM_API_REJECTED")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("live", "test"), default="live")
    args = parser.parse_args()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    github_token = os.getenv("GH_TOKEN", "").strip()
    if not bot_token or not chat_id:
        print("NOT_CONFIGURED: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in repository Actions secrets")
        return 2 if args.mode == "test" else 0
    if not re.fullmatch(r"-?\d{4,20}", chat_id):
        print("INVALID_CHAT_ID: numeric private chat/group ID required")
        return 2
    try:
        if args.mode == "test":
            telegram_api(bot_token, "sendMessage", {"chat_id": chat_id,
                         "text": "✅ C3 TOP2 텔레그램 연결 시험 성공\n이 메시지는 연구 신호나 매수 추천이 아닙니다."})
            print("TELEGRAM_TEST_DELIVERED")
            return 0
        if not github_token:
            print("MISSING_GITHUB_TOKEN")
            return 2
        current = now_kst()
        if current.weekday() >= 5:
            print("SKIP_NON_TRADING_WEEKEND")
            return 0
        latest = read_report(github_token, "latest.json")
        summary = read_report(github_token, "mobile/summary.json")
        reason = report_error(latest, summary, current)
        if reason:
            print("SKIP_" + reason)
            return 0
        asof = latest["source_price_asof"]
        if receipt_exists(github_token, asof):
            print("SKIP_DUPLICATE_TRADING_DAY_" + asof)
            return 0
        body = build_message(latest, summary)
        receipt = {"source_date": asof, "source_run_id": latest["source_run_id"],
                   "status": "CLAIMED_BEFORE_SEND", "claimed_at": current.isoformat(),
                   "note": "Do not automatically resend after any uncertain delivery."}
        try:
            sha = write_receipt(github_token, asof, receipt)
        except urllib.error.HTTPError as exc:
            print("SKIP_RECEIPT_CLAIM_FAILED_HTTP_" + str(exc.code))
            return 1
        try:
            sent = telegram_api(bot_token, "sendMessage", {"chat_id": chat_id, "text": body,
                              "link_preview_options": {"is_disabled": True}})
            receipt["status"] = "DELIVERED"
            receipt["delivered_at"] = now_kst().isoformat()
            receipt["telegram_message_id"] = sent.get("result", {}).get("message_id")
            print("TELEGRAM_MESSAGE_ACCEPTED_FOR_SESSION_" + asof)
        except Exception as exc:
            receipt["status"] = "SEND_FAILED_REVIEW_REQUIRED"
            receipt["error_type"] = type(exc).__name__
            print("TELEGRAM_SEND_FAILED_REVIEW_REQUIRED_" + type(exc).__name__)
            result_code = 1
        else:
            result_code = 0
        try:
            write_receipt(github_token, asof, receipt, sha)
        except Exception as exc:
            print("RECEIPT_UPDATE_FAILED_" + type(exc).__name__ + "_CLAIM_REMAINS")
            return 1
        return result_code
    except urllib.error.HTTPError as exc:
        print("EXTERNAL_HTTP_FAILURE_" + str(exc.code))
        return 1
    except Exception as exc:
        # Never log URL/request objects: Bot API URLs contain a private token.
        print("C3_TELEGRAM_ERROR_" + type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
