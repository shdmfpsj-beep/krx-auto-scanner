#!/usr/bin/env python3
"""Capture observations into different immutable session namespaces.

PykRX date-only source is intentionally unscoped. No API-key or trading logic.
"""
import argparse,json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from krx_session_probe import fetch_market
from krx_regular_after_layers import capture,split,window,SOURCE

def load(p):
    try:
        x=json.loads(Path(p).read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else {}
    except (OSError,TypeError,ValueError):return {}

def save(path,obj):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def collect(phase, now):
    if window(phase,now) not in ("POST_REGULAR_PRE_OFFHOURS","AFTERMARKET_FINISHED"):
        return {"schema":"krx_session_observation_unavailable_v1",
                "phase":phase,"asof":now.date().isoformat(),
                "captured_at_kst":now.isoformat(),
                "capture_window":window(phase,now),
                "source":SOURCE,"stocks":{},
                "regular_strategy_eligible":False,
                "trade_approved":False,"orders_enabled":False,
                "separation_blockers":["CAPTURE_WINDOW_NOT_VERIFIED"]}
    try:
        markets=fetch_market(now.date().isoformat())
        out=capture(phase,now,markets,provider_session_scope_verified=False)
        return out
    except Exception:
        return {"schema":"krx_session_observation_unavailable_v1",
                "phase":phase,"asof":now.date().isoformat(),
                "captured_at_kst":now.isoformat(),
                "capture_window":window(phase,now),
                "source":SOURCE,"stocks":{},
                "regular_strategy_eligible":False,
                "trade_approved":False,"orders_enabled":False,
                "separation_blockers":["PUBLIC_MARKET_SOURCE_UNAVAILABLE_OR_INCOMPLETE"]}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--phase",required=True,choices=("regular","after","compare"))
    a.add_argument("--regular",default="")
    a.add_argument("--after",default="")
    a.add_argument("--output",required=True)
    p=a.parse_args()
    if p.phase=="compare":
        result=split(load(p.regular),load(p.after))
    else:
        result=collect(p.phase,datetime.now(ZoneInfo("Asia/Seoul")))
    save(p.output,result)
    print(json.dumps({k:v for k,v in result.items()
                      if k not in ("stocks","comparison")},
                      ensure_ascii=False))
if __name__=="__main__":main()
