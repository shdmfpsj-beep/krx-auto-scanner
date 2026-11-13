"""2026-11-13 one-night research handoff from dated FDR prefetch.

Never promotes an unverified cache to an approved trading signal.
No orders, no Telegram, no original ledger writes. Date-gated forever.
"""
import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from c3_early_source_v1 import clock, session_context, write
from c3_morning_source_v1 import normalized_hash
from c3_source_recovery_v1 import validate

TARGET = "2026-11-13"
REPOSITORY = "shdmfpsj-beep/krx-auto-scanner"
UPSTREAM = "C3 post-close price prefetch (RESEARCH / NO SEND)"
ALLOWED_CRONS = {"20 12 * * 1-5", "10 14 * * 1-5", "10 15 * * 5"}
OPEN_AT = datetime.fromisoformat("2026-11-13T21:00:00+09:00")
CLOSE_AT = datetime.fromisoformat("2026-11-14T08:00:00+09:00")


def check_trigger(event, receipt, now):
    """Only the two existing Fri night schedules, not later recurring runs."""
    local = clock(now).astimezone(ZoneInfo("Asia/Seoul"))
    if not OPEN_AT <= local < CLOSE_AT:
        raise ValueError("ONE_NIGHT_WINDOW_CLOSED")
    upstream = event.get("workflow_run") or {}
    if (event.get("repository", {}).get("full_name") != REPOSITORY
            or upstream.get("head_repository", {}).get("full_name") != REPOSITORY
            or upstream.get("head_branch") != "main"
            or upstream.get("name") != UPSTREAM
            or upstream.get("event") != "schedule"
            or upstream.get("status") != "completed"
            or upstream.get("conclusion") != "success"
            or not isinstance(upstream.get("id"), int)):
        raise ValueError("UNTRUSTED_NIGHT_SOURCE_COMPLETION")
    if (receipt.get("event") != "schedule"
            or receipt.get("trusted") is not True
            or receipt.get("cron") not in ALLOWED_CRONS
            or receipt.get("source_sha") != upstream.get("head_sha")):
        raise ValueError("UNTRUSTED_OR_OUT_OF_WINDOW_CRON")
    return upstream["id"]


def check_snapshot(prefetch, market, raw, now):
    """Validate all public-price facts before making a research-only manifest."""
    if (prefetch.get("status") != "PREFETCHED_RESEARCH_ONLY"
            or prefetch.get("asof") != TARGET
            or prefetch.get("provider") != "FDR_DATED_CSV"
            or prefetch.get("regular_only_certified") is not False
            or prefetch.get("buy_approved") is not False
            or prefetch.get("publication", {}).get("status") not in ("ARCHIVED", "ALREADY_RECORDED")):
        raise ValueError("POST_CLOSE_ARCHIVE_NOT_PUBLISHED_FOR_TARGET")
    if (market.get("asof") != TARGET or not isinstance(market.get("rows"), list)
            or not 2000 <= len(market["rows"]) <= 4500):
        raise ValueError("NIGHT_FULL_MARKET_TARGET_INVALID")
    rows = market["rows"]
    if any(r.get("asof") != TARGET for r in rows):
        raise ValueError("NIGHT_ROW_DAY_MISMATCH")
    if (len(rows) != prefetch.get("rows")
            or normalized_hash(rows) != prefetch.get("normalized_rows_sha256")
            or market.get("normalized_rows_sha256") != prefetch["normalized_rows_sha256"]
            or hashlib.sha256(raw).hexdigest() != prefetch.get("raw_sha256")):
        raise ValueError("NIGHT_ARCHIVE_HASH_OR_ROW_CONFLICT")
    if set(Counter(r["market"] for r in rows)) != {"KOSPI", "KOSDAQ"}:
        raise ValueError("NIGHT_BOTH_BOARDS_REQUIRED")
    if clock(prefetch["file_commit_at"]) < clock(session_context(clock(now), TARGET)["reference_close_at"]):
        raise ValueError("NIGHT_FILE_BEFORE_REFERENCE_CLOSE")
    if clock(prefetch["file_commit_at"]) > clock(prefetch["collected_at"]):
        raise ValueError("NIGHT_FUTURE_FILE_COMMIT")
    if clock(prefetch["collected_at"]) > clock(now):
        raise ValueError("NIGHT_FUTURE_COLLECTION")
    validate(rows, TARGET)
    return rows


def prepare(event_file, evidence, out, now=None):
    """Reformat already-encrypted prefetch as *unapproved* same-date research."""
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    evidence = Path(evidence)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    status = dict(schema="C3_NOV13_ONCE_RESEARCH_V1", asof=TARGET,
                  started_at=clock(now).isoformat(), status="HELD",
                  buy_approved=False, orders_enabled=False, telegram_requests=0,
                  original_signals_modified=False, regular_only_certified=False,
                  official_krx_match_verified=False)
    try:
        event = json.loads(Path(event_file).read_text())
        receipt = json.loads((evidence / "trigger.json").read_text())
        source_id = check_trigger(event, receipt, now)
        source = evidence / "live-prefetch"
        prefetch = json.loads((source / "prefetch.json").read_text())
        market = json.loads((source / "normalized_market.json").read_text())
        raw = (source / "original.csv").read_bytes()
        rows = check_snapshot(prefetch, market, raw, now)
        from c3_daily_research_v8 import collect_indices
        indices = collect_indices(out / "indices", TARGET)
        if set(indices.get("series", {})) != {"KOSPI", "KOSDAQ"} or any(
                v.get("end") != TARGET for v in indices["series"].values()):
            raise ValueError("NIGHT_SAME_DAY_BOARD_INDICES_NOT_READY")
        shutil.copyfile(source / "normalized_market.json", out / "normalized_market.json")
        manifest = dict(schema="C3_NOV13_RESEARCH_SOURCE_V1", asof=TARGET,
                        status="POST_CLOSE_FDR_RESEARCH_ONLY",
                        research_ready=True, approved_source_ready=False,
                        indices_ready=True, regular_only_certified=False,
                        price_basis=prefetch["price_basis"],
                        normalized_rows_sha256=prefetch["normalized_rows_sha256"],
                        data_received_at=prefetch["collected_at"],
                        source_run_id=str(source_id), rows=len(rows),
                        markets=dict(Counter(r["market"] for r in rows)),
                        file_commit=prefetch["file_commit"],
                        file_commit_at=prefetch["file_commit_at"],
                        raw_sha256=prefetch["raw_sha256"],
                        official_krx_match_verified=False,
                        buy_approved=False, orders_enabled=False,
                        telegram_requests=0,
                        original_signals_modified=False)
        write(out / "collection.json", manifest)
        status.update(status="READY_FOR_RESEARCH_ONLY", source_run_id=str(source_id),
                      rows=len(rows), markets=manifest["markets"],
                      prefetch_commit=prefetch["file_commit"],
                      price_hash=prefetch["normalized_rows_sha256"],
                      same_day_indices=True)
    except Exception as exc:
        status.update(error_type=type(exc).__name__,
                      reason=str(exc) if isinstance(exc, ValueError) else "RESEARCH_PREPARE_FAILED")
        write(out / "tonight_status.json", status)
        raise
    write(out / "tonight_status.json", status)
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.event, args.evidence, args.out), ensure_ascii=False))
