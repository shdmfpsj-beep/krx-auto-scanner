#!/usr/bin/env python3
"""Prewarm a GitHub worker before 15:33-15:39 KST provider query window.

Waiting does NOT attest that date-only provider returns regular-session
market data. Window evidence is checked again on query start and finish.
"""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import time

KST=ZoneInfo("Asia/Seoul")

def seconds_until_capture(now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("TZ_AWARE_TIME_REQUIRED")
    local=now.astimezone(KST)
    if local.weekday()>=5:return None
    start=local.replace(hour=15,minute=33,second=15,microsecond=0)
    end=local.replace(hour=15,minute=40,second=0,microsecond=0)
    if local>=end:return None
    return max(0,(start-local).total_seconds())

def main():
    now=datetime.now(KST)
    remaining=seconds_until_capture(now)
    if remaining is None:
        print("REGULAR_CAPTURE_WINDOW_ALREADY_MISSED_OR_NONTRADING_DAY")
        return
    # Runner/pip install should complete before 15:33. When early, wait
    # until 15:33:15; allow real query to finish before 15:40.
    print("WAIT_SECONDS_TO_153315_KST",round(remaining,2))
    if remaining>0:time.sleep(remaining)
    print("CAPTURE_TRIGGER_KST",datetime.now(KST).isoformat())

if __name__=="__main__":main()
