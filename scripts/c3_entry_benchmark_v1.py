"""Reproducible, offline C3 v23 entry/exit benchmark. Research only.

This is not a historical TOP2 ranking reconstruction. The manifest-selected
basket is retrospective and survival-biased. No rule is promoted by this tool.
Prices are adjusted research units, not verified historical auction fills.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import gzip
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

from c3_entry_geometry_v23 import geometry
from c3_ict_sequence_research_v1 import detect

HORIZONS=(5,10,20)
WATCH_SESSIONS=5
COOLDOWN=26  # One shared decision schedule; never shorten it after a winner.
TRAIN_END="2026-03-31"
HOLDOUT_START="2026-05-01"
BUY_COST=.0015
SELL_COST=.005
VARIANTS=("C3_BASELINE","C3_ICT","C3_TREND_VOLUME","C3_MA5",
          "C3_MA10","C3_MA20","C3_FIRST_RETEST","C3_VCP_BREAKOUT",
          "C3_HIGH_FLIP","C3_TURN_PULLBACK","C3_COMPOSITE","C3_RS_PRICE_VOLUME")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bars(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        records=list(csv.DictReader(f))
    bars=[]
    for row in records:
        row={k.lower():v for k,v in row.items()}
        day=row["date"]
        if date.fromisoformat(day).isoformat()!=day:
            raise ValueError("NONCANONICAL_DATE")
        b={k:float(row[k]) for k in ("open","high","low","close","volume")}
        if not all(math.isfinite(v) for v in b.values()) or b["volume"]<0:
            raise ValueError("INVALID_OHLCV")
        if not 0<b["low"]<=min(b["open"],b["close"])<=max(b["open"],b["close"])<=b["high"]:
            raise ValueError("INVALID_OHLCV")
        bars.append(dict(b,date=day))
    days=[b["date"] for b in bars]
    if not bars or days!=sorted(set(days)):
        raise ValueError("EMPTY_DUPLICATE_OR_UNSORTED_BARS")
    return bars


def load_panel(history_dir,manifest_path,calendar_path):
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    calendar=json.loads(Path(calendar_path).read_text(encoding="utf-8"))
    sessions=calendar["dates"]
    if not sessions or sessions!=sorted(set(sessions)):
        raise ValueError("INVALID_REFERENCE_CALENDAR")
    for day in sessions:
        if date.fromisoformat(day).isoformat()!=day:
            raise ValueError("INVALID_REFERENCE_CALENDAR")
    panel={};audit=[];seen=set()
    for rec in manifest["records"]:
        ticker=rec["ticker"]
        if ticker in seen:
            raise ValueError("DUPLICATE_MANIFEST_TICKER")
        seen.add(ticker)
        path=Path(history_dir)/(ticker+".csv")
        record=dict(ticker=ticker,source=rec.get("source"),manifest_sha256=rec.get("sha256"))
        try:
            record["actual_sha256"]=sha(path)
            if record["actual_sha256"]!=rec["sha256"]:
                raise ValueError("SOURCE_HASH_MISMATCH")
            bars=read_bars(path)
            days=[b["date"] for b in bars]
            expected=[d for d in sessions if days[0]<=d<=days[-1]]
            if days!=expected:
                raise ValueError("REFERENCE_SESSION_GAP_OR_UNEXPECTED_DATE")
            if len(bars)!=rec["bars"] or days[-1]!=rec["price_date"]:
                raise ValueError("MANIFEST_DATE_OR_COUNT_MISMATCH")
            panel[ticker]=bars
            jumps=[bars[i]["date"] for i in range(1,len(bars))
                   if abs(bars[i]["close"]/bars[i-1]["close"]-1)>.35]
            record.update(status="ACCEPTED_PROVISIONAL",rows=len(bars),
                          start=days[0],end=days[-1],
                          zero_volume_sessions=sum(b["volume"]==0 for b in bars),
                          large_close_jump_dates=jumps)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            record.update(status="REJECTED",reason=str(exc))
        audit.append(record)
    if not panel:
        raise ValueError("NO_AUDITABLE_HISTORY")
    return panel,sessions,dict(files=audit,manifest_sha256=sha(manifest_path),
        reference_calendar_sha256=sha(calendar_path),
        reference_calendar_source=calendar.get("source"),
        official_calendar_verified=False,regular_only_certified=False,
        current_selection_survivorship_bias=True,point_in_time_universe_verified=False,
        source_scope="PYKRX_ADJUSTED_BY_DATE_UNCERTIFIED",
        files_outside_manifest_ignored=len(set(p.stem for p in Path(history_dir).glob("*.csv"))-seen))


def load_archived_panel(history_path,status_path,calendar_path,members_path,basic_dir):
    """Use only hash-matched histories with explicit non-biotech membership.

    The basket was retained by a later stage screen. This is a conditional
    retrospective sensitivity study, never a point-in-time universe test.
    """
    status=json.loads(Path(status_path).read_text())
    if sha(history_path)!=status["output_sha256"][Path(history_path).name]:
        raise ValueError("ARCHIVE_HASH_MISMATCH")
    sessions=json.loads(Path(calendar_path).read_text())["dates"]
    common=set()
    basic_files=sorted(Path(basic_dir).glob("*.csv"))
    for path in basic_files:
        with path.open(encoding="utf-8-sig") as f:
            common.update(r["ticker"] for r in csv.DictReader(f)
                          if r["security_group"]=="주권" and r["share_kind"]=="보통주")
    # Reject every ticker with any healthcare/biotech taxonomy membership,
    # even when another row also maps it to an industrial theme.
    with Path(members_path).open(encoding="utf-8-sig") as f:
        members=list(csv.DictReader(f))
    excluded={m["ticker"] for m in members if any(x in m["investment_sector"] for x in ("바이오","제약","헬스케어"))}
    eligible={m["ticker"] for m in members if m["ticker"] in common}-excluded
    grouped={};all_codes=set();row_count=0
    with gzip.open(history_path,"rt",encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            row_count+=1;all_codes.add(r["ticker"])
            if r["ticker"] in eligible:
                grouped.setdefault(r["ticker"],[]).append(r)
    if row_count!=status["history_rows"]:
        raise ValueError("ARCHIVE_ROW_COUNT_MISMATCH")
    panel={};audit=[]
    for code,records in sorted(grouped.items()):
        bars=[];problem=None
        for r in records:
            b={k:float(r[k]) for k in ("open","high","low","close","volume")}
            if (not all(math.isfinite(x) for x in b.values()) or b["volume"]<0
                    or not 0<b["low"]<=min(b["open"],b["close"])<=max(b["open"],b["close"])<=b["high"]):
                problem="INVALID_OHLCV";break
            bars.append(dict(b,date=r["date"]))
        days=[b["date"] for b in bars]
        if not problem and (not days or days!=[d for d in sessions if days[0]<=d<=days[-1]]):
            problem="REFERENCE_SESSION_GAP_OR_DUPLICATE"
        if problem:
            audit.append(dict(ticker=code,status="REJECTED",reason=problem));continue
        panel[code]=bars
        audit.append(dict(ticker=code,status="ACCEPTED_PROVISIONAL",rows=len(bars),start=days[0],end=days[-1],
                          zero_volume_sessions=sum(b["volume"]==0 for b in bars)))
    if not panel:
        raise ValueError("NO_ELIGIBLE_ARCHIVED_HISTORY")
    return panel,sessions,dict(files=audit,archive_sha256=sha(history_path),status_sha256=sha(status_path),
        reference_calendar_sha256=sha(calendar_path),members_sha256=sha(members_path),
        basic_snapshot_sha256={p.name:sha(p) for p in basic_files},
        archive_source_run=status.get("run_context"),archive_asof=status.get("asof"),
        archive_tickers=len(all_codes),archive_rows=row_count,
        study_scope="CURATED_NON_BIOTECH_COMMON_SHARES_INTERSECT_POST_SCREEN_RETAINED_HISTORY",
        official_calendar_verified=False,regular_only_certified=False,
        current_selection_survivorship_bias=True,point_in_time_universe_verified=False)


def first_retest(past,lookback=20):
    """Frozen earlier breakout level and its first completed retest only."""
    end=len(past)-1
    for j in range(max(lookback,end-10),end):
        level=max(b["high"] for b in past[j-lookback:j])
        if past[j]["close"]<=level or past[j-1]["close"]>level:
            continue
        retests=[k for k in range(j+1,end+1)
                 if past[k]["low"]<=level and past[k]["close"]>=level]
        if retests and retests[0]==end:
            return level
    return None


def context(past,signals):
    """Decision-close information only. Every returned level is frozen."""
    closes=[b["close"] for b in past]
    latest=past[-1]
    mean=lambda n:statistics.mean(closes[-n:])
    vol20=statistics.mean(b["volume"] for b in past[-21:-1])
    ma={n:mean(n) for n in (5,10,20)}
    ict=[s for s in signals if s["event"]=="FVG_RETEST_WATCH" and s["date"]<=latest["date"]]
    indices={b["date"]:i for i,b in enumerate(past)}
    ict=[s for s in ict if 0<=len(past)-1-indices[s["date"]]<=10
         and all(b["close"]>=s["sweep_invalidation_low"] for b in past[indices[s["date"]]+1:])]
    signal=ict[-1] if ict else None
    span=lambda xs:(max(b["high"] for b in xs)-min(b["low"] for b in xs))/statistics.mean(b["close"] for b in xs)
    vcp=(span(past[-6:-1])<span(past[-11:-6])<span(past[-21:-11])
         and latest["close"]>max(b["high"] for b in past[-21:-1]))
    ma20=[statistics.mean(closes[k-19:k+1]) for k in range(19,len(past))]
    turns=[k for k in range(max(1,len(ma20)-15),len(ma20))
           if ma20[k]>ma20[k-1] and k>=2 and ma20[k-1]<=ma20[k-2]]
    first_turn_pullback=False
    if turns:
        turn_index=turns[-1]+19
        touches=[k for k in range(turn_index+1,len(past))
                 if past[k]["low"]<=statistics.mean(closes[k-19:k+1])<=past[k]["close"]]
        first_turn_pullback=bool(touches and touches[0]==len(past)-1)
    reexpand=(vol20>0 and past[-2]["volume"]<.8*vol20
              and latest["volume"]>1.5*past[-2]["volume"]
              and latest["close"]>past[-2]["close"])
    trend_volume=(latest["close"]>ma[20]>statistics.mean(closes[-50:])
                  and latest["volume"]>=1.2*vol20 and vol20>0)
    retest=first_retest(past,20)
    high_flip=first_retest(past,40)
    return dict(ma=ma,ict=signal,trend_volume=trend_volume,
                volume_reexpansion=reexpand,vcp=vcp,retest=retest,high_flip=high_flip,
                turn_pullback=first_turn_pullback,
                relative_strength=None,investor_flows=None)


def make_decision(ticker,rows,index,signals,benchmark=None):
    past=rows[:index+1]
    g=geometry(past)
    if g.get("status")!="RESEARCH_GEOMETRY_ONLY" or g["trend_state"]!="UPTREND":
        return None
    if rows[index]["volume"]==0:
        return None
    stop=g["structural_stop"]
    low,high=g["entry_low"],g["entry_high"]
    if not 0<stop<low<=high:
        return None
    if g["first_resistance"] is not None and high>=g["first_resistance"]:
        return None
    c=context(past,signals)
    c["market_regime"]="UNAVAILABLE"
    c["rs20_pct"]=None
    if benchmark:
        market=[b for b in benchmark if b["date"]<=rows[index]["date"]]
        if (len(market)>=61 and market[-1]["date"]==rows[index]["date"]
                and market[-21]["date"]==past[-21]["date"]):
            m20=statistics.mean(b["close"] for b in market[-20:])
            m60=statistics.mean(b["close"] for b in market[-60:])
            c["market_regime"]=("UP" if market[-1]["close"]>m20>m60 else
                                "DOWN" if market[-1]["close"]<m20<m60 else "SIDEWAYS")
            c["rs20_pct"]=100*((past[-1]["close"]/past[-21]["close"])/(
                market[-1]["close"]/market[-21]["close"])-1)
    return dict(plan_id="C3V23-"+ticker+"-"+rows[index]["date"],ticker=ticker,
                decision_date=rows[index]["date"],structure_stop=stop,
                watch_low=low,watch_high=high,atr14=g["atr14"],
                reference_close=g["reference_close"],
                resistance1=g["first_resistance"],resistance2=g["second_resistance"],
                context=c,geometry=g)


def variant_plan(plan,variant):
    c=plan["context"]
    enabled={"C3_BASELINE":True,"C3_ICT":bool(c["ict"]),
             "C3_TREND_VOLUME":c["trend_volume"] or c["volume_reexpansion"],
             "C3_FIRST_RETEST":c["retest"] is not None,
             "C3_VCP_BREAKOUT":c["vcp"],"C3_HIGH_FLIP":c["high_flip"] is not None,
             "C3_TURN_PULLBACK":c["turn_pullback"],
             "C3_COMPOSITE":bool(c["ict"] and c["trend_volume"]),
             "C3_RS_PRICE_VOLUME":c.get("rs20_pct") is not None and c["rs20_pct"]>0 and c["trend_volume"]}
    band=(plan["watch_low"],plan["watch_high"])
    if variant.startswith("C3_MA"):
        n=int(variant[5:])
        anchor=c["ma"][n]
        enabled[variant]=plan["reference_close"]>=anchor
        band=(anchor-.25*plan["atr14"],anchor+.25*plan["atr14"])
    elif variant=="C3_ICT" and c["ict"]:
        band=(c["ict"]["fvg_lower"],c["ict"]["fvg_upper"])
    elif variant in ("C3_FIRST_RETEST","C3_HIGH_FLIP") and enabled[variant]:
        anchor=c["retest"] if variant=="C3_FIRST_RETEST" else c["high_flip"]
        band=(anchor-.25*plan["atr14"],anchor+.25*plan["atr14"])
    if not enabled.get(variant,False):
        return None,"FILTERED"
    p=copy.deepcopy(plan)
    # One structural invalidation level for all timing comparisons.
    # No stop+3% constraint and no invented higher support.
    p["watch_low"]=max(band[0],p["structure_stop"]+.1*p["atr14"])
    p["watch_high"]=band[1]
    if p["resistance1"] is not None:
        p["watch_high"]=min(p["watch_high"],p["resistance1"]-.1*p["atr14"])
    if p["watch_low"]>p["watch_high"] or p["watch_high"]<=p["structure_stop"]:
        return None,"NO_USABLE_BAND"
    p["variant"]=variant
    return p,None


def locate_entry(plan,rows,sessions):
    by_day={b["date"]:b for b in rows}
    future=[d for d in sessions if d>plan["decision_date"]][:WATCH_SESSIONS]
    low,high,stop=plan["watch_low"],plan["watch_high"],plan["structure_stop"]
    for day in future:
        if day not in by_day:
            return dict(status="DATA_GAP",missing_date=day)
        b=by_day[day]
        if b["volume"]==0:
            continue  # A stationary zero-volume bar cannot fill a limit order.
        if b["open"]<=stop:
            return dict(status="GAP_BELOW_STOP",date=day)
        if b["open"]<low:
            return dict(status="GAP_BELOW_BAND",date=day)
        touch=b["low"]<=high and b["high"]>=low
        if touch:
            if b["low"]<=stop:
                return dict(status="ENTRY_STOP_ORDER_UNKNOWN",date=day)
            return dict(status="MODEL_ENTRY",date=day,
                        price=min(b["open"],high),
                        entry_day_target_order_unknown=(
                            plan["resistance1"] is not None and b["high"]>=plan["resistance1"]),
                        actual_fill_verified=False)
        if b["close"]<stop:
            return dict(status="INVALIDATED_BEFORE_ENTRY",date=day)
        if plan["resistance1"] is not None and b["high"]>=plan["resistance1"]:
            return dict(status="MISSED_RESISTANCE_WITHOUT_ENTRY",date=day)
    return dict(status="EXPIRED_NO_TOUCH" if len(future)==WATCH_SESSIONS else "PENDING")


def net_return(entry,exit_price,buy_cost=BUY_COST,sell_cost=SELL_COST):
    if (not all(math.isfinite(x) for x in (entry,exit_price,buy_cost,sell_cost))
            or min(entry,exit_price)<=0 or not 0<=buy_cost<1 or not 0<=sell_cost<1):
        raise ValueError("INVALID_PRICE_OR_COST")
    return 100*(exit_price*(1-sell_cost)/(entry*(1+buy_cost))-1)


def target_price(entry,pct):
    # Source research geometry has sub-won precision; avoid 100*1.1 being
    # slightly above an observed 110 boundary. This is not exchange tick rounding.
    return round(entry*(100+pct)/100,8)


def outcome(plan,entry,rows,sessions,horizon):
    by_day={b["date"]:b for b in rows}
    days=[d for d in sessions if d>entry["date"]][:horizon]
    complete=len(days)==horizon and all(d in by_day for d in days)
    result=dict(complete=complete,horizon=horizon)
    if not complete:
        return result
    bars=[by_day[d] for d in days]
    price=entry["price"]
    stop_days=[d for d,b in zip(days,bars) if b["volume"]>0 and b["low"]<=plan["structure_stop"]]
    first_stop=stop_days[0] if stop_days else None
    rebound=None
    if first_stop:
        j=days.index(first_stop)
        after=days[j+1:j+3]
        if len(after)==2 and all(d in by_day for d in after):
            rebound=any(by_day[d]["close"]>=plan["watch_low"] for d in after)
    resistance=plan["resistance1"]
    breaks=[d for d,b in zip(days,bars) if resistance is not None and b["close"]>resistance]
    continuation=None
    if breaks:
        j=days.index(breaks[0])
        if len(days)-j-1>=5:
            continuation=bars[j+5]["close"]>bars[j]["close"]
    result.update(close_change_pct=100*(bars[-1]["close"]/price-1),
        mfe_pct=max(0,100*(max(b["high"] for b in bars)/price-1)),
        mae_pct=min(0,100*(min(b["low"] for b in bars)/price-1)),
        target10=any(b["volume"]>0 and b["high"]>=target_price(price,10) for b in bars),
        target15=any(b["volume"]>0 and b["high"]>=target_price(price,15) for b in bars),
        target20=any(b["volume"]>0 and b["high"]>=target_price(price,20) for b in bars),
        stop_touched=bool(first_stop),stop_rebound_1_2_sessions=rebound,
        resistance_break_then_5_session_continuation=continuation,
        excursions_continue_after_model_stop=True,
        observation_reference="HYPOTHETICAL_ENTRY_EXCLUDES_ENTRY_DAY_EXTREMES")
    for target_pct in (10,15,20):
        level=target_price(price,target_pct)
        targets=[d for d,b in zip(days,bars) if b["volume"]>0 and b["high"]>=level]
        first_target=targets[0] if targets else None
        if first_stop and first_stop==first_target:
            opening=by_day[first_stop]["open"]
            order=("STOP_FIRST" if opening<=plan["structure_stop"] else
                   "TARGET_FIRST" if opening>=level else "SAME_DAY_ORDER_UNKNOWN")
        else:
            order=("TARGET_FIRST" if first_target and (not first_stop or first_target<first_stop) else
                   "STOP_FIRST" if first_stop else "NO_TARGET_OR_STOP")
        result["target"+str(target_pct)+"_before_stop"]=order=="TARGET_FIRST"
        result["target"+str(target_pct)+"_order_unknown"]=order=="SAME_DAY_ORDER_UNKNOWN"
    return result


def simulate_exit(plan,entry,rows,sessions,horizon,stop_mode="CLOSE",exit_mode="HOLD",
                  buy_cost=BUY_COST,sell_cost=SELL_COST):
    if stop_mode not in ("CLOSE","INTRADAY") or exit_mode not in ("HOLD","TAKE10","TREND20"):
        raise ValueError("INVALID_EXIT_RULE")
    by_day={b["date"]:b for b in rows}
    days=[d for d in sessions if d>entry["date"]][:horizon]
    if len(days)<horizon or any(d not in by_day for d in days):
        return dict(complete=False,reason="INCOMPLETE_HORIZON_OR_GAP")
    pending=False;ambiguous=False;exit_day=days[-1];exit_price=by_day[exit_day]["close"]
    reason="HORIZON_CLOSE_MARK";pending_at_horizon=False
    for day in days:
        b=by_day[day]
        if pending and b["volume"]==0:
            return dict(complete=False,reason="NEXT_OPEN_UNTRADABLE_AFTER_CLOSE_STOP",
                        missing_execution_date=day)
        if b["volume"]==0:
            continue
        if pending:
            exit_day,exit_price,reason=day,b["open"],"CLOSE_STOP_NEXT_OPEN"
            break
        stop=plan["structure_stop"]
        target=target_price(entry["price"],10)
        # Opening auction precedes subsequent daily extremes.
        if stop_mode=="INTRADAY" and b["open"]<=stop:
            exit_day,exit_price,reason=day,b["open"],"GAP_STOP"
            break
        if exit_mode=="TAKE10" and b["open"]>=target:
            exit_day,exit_price,reason=day,target,"OPEN_ABOVE_TAKE10_CONSERVATIVE"
            break
        if stop_mode=="INTRADAY" and b["low"]<=stop:
            ambiguous=exit_mode=="TAKE10" and b["high"]>=target
            exit_day,exit_price,reason=day,stop,"INTRADAY_STOP"
            break
        if exit_mode=="TAKE10" and b["high"]>=target:
            exit_day,exit_price,reason=day,target,"TAKE10_AFTER_ENTRY_DAY"
            break
        if exit_mode=="TREND20":
            prior=[x["close"] for x in rows if x["date"]<day][-20:]
            if len(prior)==20:
                stop=max(stop,statistics.mean(prior))
        if (stop_mode=="CLOSE" or exit_mode=="TREND20") and b["close"]<stop:
            pending=True
            pending_at_horizon=day==days[-1]
    return dict(complete=True,hypothetical_net_pct=net_return(entry["price"],exit_price,buy_cost,sell_cost),
                exit_date=exit_day,exit_price=exit_price,exit_reason=reason,
                pending_close_exit_at_horizon=pending_at_horizon,
                same_bar_order_conservative=ambiguous,
                exit_is_mark_only=reason=="HORIZON_CLOSE_MARK",
                actual_fill_verified=False)


def mean_or_none(values):
    return round(statistics.mean(values),4) if values else None


def rate(values):
    return round(100*sum(values)/len(values),3) if values else None


def wilson(positive,n):
    if not n:
        return None
    z=1.95996398454;p=positive/n;d=1+z*z/n
    center=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*(center-half),2),round(100*(center+half),2)]


def summarize(records,total_decisions,horizon,fold):
    selected=[r for r in records if r["fold"]==fold]
    filled=[r for r in selected if r["entry"]["status"]=="MODEL_ENTRY"]
    complete=[r for r in filled if r["outcomes"][str(horizon)]["complete"]]
    observed=[r["outcomes"][str(horizon)] for r in complete]
    exits={}
    for mode in ("CLOSE","INTRADAY"):
        for style in ("HOLD","TAKE10","TREND20"):
            key=mode+"_"+style
            models=[r["exits"][str(horizon)][key] for r in complete]
            values=[m["hypothetical_net_pct"] for m in models if m["complete"]]
            exits[key]=dict(mean_net_pct=mean_or_none(values),median_net_pct=round(statistics.median(values),4) if values else None,
                            positive_rate_pct=rate([v>0 for v in values]),
                            stop_exit_rate_pct=rate([m["exit_reason"] in (
                                "CLOSE_STOP_NEXT_OPEN","INTRADAY_STOP","GAP_STOP") for m in models if m["complete"]]),
                            pending_close_exit_at_horizon_count=sum(m.get("pending_close_exit_at_horizon",False) for m in models),
                            completed_model_results=len(values),censored_model_results=len(models)-len(values))
    statuses=Counter(r["entry"]["status"] for r in selected)
    return dict(decisions=total_decisions,eligible_after_filter=len(selected),
        filtered_decisions=total_decisions-len(selected),
        opportunity_retention_pct=round(100*len(selected)/total_decisions,3) if total_decisions else None,
        model_entries=len(filled),entry_statuses=dict(statuses),completed_horizons=len(complete),
        positive_close_rate_pct=rate([o["close_change_pct"]>0 for o in observed]),
        positive_close_wilson95_descriptive=wilson(sum(o["close_change_pct"]>0 for o in observed),len(observed)),
        mean_mfe_pct=mean_or_none([o["mfe_pct"] for o in observed]),
        mean_mae_pct=mean_or_none([o["mae_pct"] for o in observed]),
        target10_rate_pct=rate([o["target10"] for o in observed]),
        target15_rate_pct=rate([o["target15"] for o in observed]),
        target20_rate_pct=rate([o["target20"] for o in observed]),
        target10_before_stop_rate_pct=rate([o["target10_before_stop"] for o in observed]),
        target15_before_stop_rate_pct=rate([o["target15_before_stop"] for o in observed]),
        target20_before_stop_rate_pct=rate([o["target20_before_stop"] for o in observed]),
        target10_order_unknown_rate_pct=rate([o["target10_order_unknown"] for o in observed]),
        target15_order_unknown_rate_pct=rate([o["target15_order_unknown"] for o in observed]),
        target20_order_unknown_rate_pct=rate([o["target20_order_unknown"] for o in observed]),
        stop_touch_rate_pct=rate([o["stop_touched"] for o in observed]),
        stop_rebound_1_2_session_rate_pct=rate([o["stop_rebound_1_2_sessions"] for o in observed if o["stop_rebound_1_2_sessions"] is not None]),
        stop_rebound_evaluable_count=sum(o["stop_rebound_1_2_sessions"] is not None for o in observed),
        resistance_continuation_rate_pct=rate([o["resistance_break_then_5_session_continuation"] for o in observed if o["resistance_break_then_5_session_continuation"] is not None]),
        resistance_continuation_evaluable_count=sum(o["resistance_break_then_5_session_continuation"] is not None for o in observed),
        exit_models=exits,portfolio_max_drawdown_pct=None,
        portfolio_not_simulated=True,inferential_independence_verified=False)


def run_benchmark(panel,sessions,benchmark=None):
    records={v:[] for v in VARIANTS};decisions=[]
    raw_candidates=0;embargoed=0
    for ticker,rows in sorted(panel.items()):
        signals=detect(rows)
        next_index=65
        for i in range(65,len(rows)):
            p=make_decision(ticker,rows,i,signals,benchmark)
            if p is None:
                continue
            raw_candidates+=1
            if i<next_index:
                continue
            # A fold is fixed by date; outcomes cannot cross the development
            # boundary. April is an embargo, not a tuning/selection sample.
            day=p["decision_date"]
            if day<=TRAIN_END:
                fold="DEVELOPMENT"
                future=[d for d in sessions if d>day][:WATCH_SESSIONS+max(HORIZONS)]
                if len(future)<WATCH_SESSIONS+max(HORIZONS) or future[-1]>TRAIN_END:
                    embargoed+=1
                    continue
            elif day>=HOLDOUT_START:
                fold="HOLDOUT"
            else:
                embargoed+=1
                continue
            next_index=i+COOLDOWN
            p["fold"]=fold
            decisions.append(p)
            for variant in VARIANTS:
                vp,rejection=variant_plan(p,variant)
                if vp is None:
                    continue
                entry=locate_entry(vp,rows,sessions)
                record=dict(plan_id=p["plan_id"],ticker=ticker,fold=fold,
                            decision_date=day,watch_low=vp["watch_low"],watch_high=vp["watch_high"],
                            structure_stop=vp["structure_stop"],resistance1=vp["resistance1"],
                            market_regime=p["context"]["market_regime"],
                            entry=entry,outcomes={},exits={})
                if entry["status"]=="MODEL_ENTRY":
                    for h in HORIZONS:
                        record["outcomes"][str(h)]=outcome(vp,entry,rows,sessions,h)
                        record["exits"][str(h)]={mode+"_"+style:simulate_exit(vp,entry,rows,sessions,h,mode,style)
                            for mode in ("CLOSE","INTRADAY") for style in ("HOLD","TAKE10","TREND20")}
                records[variant].append(record)
    stats={}
    for v in VARIANTS:
        stats[v]={fold:{str(h):summarize(records[v],sum(p["fold"]==fold for p in decisions),h,fold)
                        for h in HORIZONS} for fold in ("DEVELOPMENT","HOLDOUT")}
    paired={}
    for v in VARIANTS[1:]:
        paired[v]={}
        for fold in ("DEVELOPMENT","HOLDOUT"):
            baseline={r["plan_id"]:r for r in records["C3_BASELINE"] if r["fold"]==fold}
            deltas=[]
            for r in records[v]:
                b=baseline.get(r["plan_id"])
                if (r["fold"]!=fold or not b or r["entry"]["status"]!="MODEL_ENTRY"
                        or b["entry"]["status"]!="MODEL_ENTRY"):
                    continue
                a=r["exits"]["20"]["CLOSE_HOLD"];bb=b["exits"]["20"]["CLOSE_HOLD"]
                if a["complete"] and bb["complete"]:
                    deltas.append(a["hypothetical_net_pct"]-bb["hypothetical_net_pct"])
            paired[v][fold]=dict(paired_complete20=len(deltas),
                                mean_paired_advantage_pct=mean_or_none(deltas),
                                improvement_established=False)
    regime_stats={fold:{regime:{str(h):summarize(
        [r for r in records["C3_BASELINE"] if r["market_regime"]==regime],
        sum(p["fold"]==fold and p["context"]["market_regime"]==regime for p in decisions),h,fold)
        for h in HORIZONS} for regime in ("UP","DOWN","SIDEWAYS","UNAVAILABLE")}
        for fold in ("DEVELOPMENT","HOLDOUT")}
    return dict(schema="C3_ENTRY_BENCHMARK_RESEARCH_V1",statistics=stats,
                baseline_market_regime_statistics=regime_stats,
                market_reference_used=benchmark is not None,
                paired_same_decision_comparisons=paired,raw_candidate_days=raw_candidates,
                frozen_decision_count=len(decisions),embargoed_candidate_days=embargoed,
                decisions=decisions,records=records,trade_approved=False,orders_enabled=False,
                strategy_profitability_verified=False,decision="CASH",
                rules=dict(baseline="C3_V23_GEOMETRY_UPTREND_WITH_RESISTANCE_BAND_GUARD",
                           structural_stop_frozen_first=True,fixed_stop_plus_3pct_gate=False,
                           shared_decision_cooldown_sessions=COOLDOWN,watch_sessions=WATCH_SESSIONS,
                           development_end=TRAIN_END,holdout_start=HOLDOUT_START,
                           development_outcomes_purged=True,parameters_optimized=False,
                           buy_cost=BUY_COST,sell_cost=SELL_COST,
                           gap_below_band="CANCEL",entry_stop_collision="EXCLUDE_AMBIGUOUS_ENTRY",
                           exit_stop_target_collision="STOP_FIRST_UNLESS_OPEN_PROVES_ORDER",
                           entry_day_profit_targets="NEVER_EXECUTED_FROM_DAILY_HIGH"),
                untested=["FULL_MARKET_POINT_IN_TIME_TOP2_RANKING","OFFICIAL_REGULAR_ONLY_OHLCV",
                          "INDEPENDENT_EXCHANGE_CALENDAR","MARKET_REGIME_BENCHMARK",
                          "RELATIVE_STRENGTH_WITH_POINT_IN_TIME_FLOWS","PORTFOLIO_MAX_DRAWDOWN",
                          "TICK_SIZE_QUEUE_LIQUIDITY_AND_SLIPPAGE","POINT_IN_TIME_CORPORATE_ACTIONS"],
                limitations=["RETROSPECTIVELY_SELECTED_SMALL_BASKET_SURVIVORSHIP_BIAS",
                             "ADJUSTED_PRICE_UNITS_ARE_NOT_HISTORICAL_EXECUTABLE_PRICES",
                             "MULTIPLE_EXPLORATORY_VARIANTS_NO_STATISTICAL_PROMOTION",
                             "CALENDAR_AND_PRICE_SESSION_SCOPE_REMAIN_UNCERTIFIED",
                             "DESCRIPTIVE_HOLDOUT_NOT_UNBIASED_UNIVERSE_OUT_OF_SAMPLE"])


def write_outputs(result,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    # Detailed ledger stays separate from the mobile summary.
    detailed={k:result[k] for k in ("records","decisions")}
    summary={k:v for k,v in result.items() if k not in detailed}
    (root/"decision_ledger.json").write_text(json.dumps(detailed,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    (root/"benchmark_report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    compact={k:v for k,v in summary.items() if k not in ("statistics","baseline_market_regime_statistics")}
    (root/"study_manifest.json").write_text(json.dumps(compact,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    if detailed["decisions"]:
        frozen=[dict(plan_id=d["plan_id"],ticker=d["ticker"],decision_date=d["decision_date"],fold=d["fold"],
            watch_low=d["watch_low"],watch_high=d["watch_high"],structure_stop=d["structure_stop"],
            resistance1=d["resistance1"],resistance2=d["resistance2"],
            market_regime=d["context"]["market_regime"],rs20_pct=d["context"]["rs20_pct"],
            ict_signal_date=d["context"]["ict"]["date"] if d["context"]["ict"] else None)
            for d in detailed["decisions"]]
        with (root/"frozen_decisions.csv").open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(frozen[0]),lineterminator="\n");w.writeheader();w.writerows(frozen)
    table=[]
    for variant,folds in result["statistics"].items():
        for fold,horizons in folds.items():
            for h,s in horizons.items():
                table.append(dict(variant=variant,fold=fold,horizon=int(h),
                    **{k:v for k,v in s.items() if k not in (
                        "entry_statuses","exit_models","positive_close_wilson95_descriptive")},
                    close_hold_net_mean_pct=s["exit_models"]["CLOSE_HOLD"]["mean_net_pct"],
                    close_stop_exit_rate_pct=s["exit_models"]["CLOSE_HOLD"]["stop_exit_rate_pct"],
                    intraday_stop_exit_rate_pct=s["exit_models"]["INTRADAY_HOLD"]["stop_exit_rate_pct"],
                    close_hold_model_results=s["exit_models"]["CLOSE_HOLD"]["completed_model_results"],
                    close_hold_censored_results=s["exit_models"]["CLOSE_HOLD"]["censored_model_results"],
                    intraday_hold_net_mean_pct=s["exit_models"]["INTRADAY_HOLD"]["mean_net_pct"],
                    close_take10_net_mean_pct=s["exit_models"]["CLOSE_TAKE10"]["mean_net_pct"],
                    close_trend20_net_mean_pct=s["exit_models"]["CLOSE_TREND20"]["mean_net_pct"]))
    with (root/"strategy_comparison.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]),lineterminator="\n");w.writeheader();w.writerows(table)
    fmt=lambda v:"대기" if v is None else f"{v:.2f}"
    lines=["# C3 매수 타점·손절 비교 — 탐색적 연구", "",
        "최종 행동: **CASH**. 현재 TOP2 추천·실제 체결·검증된 수익모델을 뜻하지 않습니다.", "",
        "동일한 C3 v23 구조·날짜에서 손절을 먼저 고정하고 진입 방식과 추가 조건을 비교했습니다.",
        "개발 종료 2026-03-31, 4월 격리, 관찰 검증 시작 2026-05-01. 결과를 보고 매개변수를 최적화하지 않았습니다.", "",
        "현재 선정 종목의 과거 자료를 사용했으므로 생존자 편향이 남습니다. 표본 수·정규장·기업행위 검증이 불충분해 개선 모델을 승인하지 않습니다.", "",
        "| 방식 | 기간 | 완료 표본 5/10/20일 | 20일 평균 모형손익 % | 20일 +10/+15/+20% 도달률 | 20일 손절 접촉률 |", "|---|---|---|---:|---|---:|"]
    for v in VARIANTS:
        for fold,label in (("DEVELOPMENT","개발"),("HOLDOUT","관찰 검증")):
            s=result["statistics"][v][fold];r=s["20"]
            lines.append(f"| {v} | {label} | "+"/".join(str(s[str(h)]["completed_horizons"]) for h in HORIZONS)+
                " | "+fmt(r["exit_models"]["CLOSE_HOLD"]["mean_net_pct"])+" | "+
                "/".join(fmt(r[k]) for k in ("target10_rate_pct","target15_rate_pct","target20_rate_pct"))+" | "+fmt(r["stop_touch_rate_pct"])+" |")
    lines.extend(["", "모형손익은 매수 0.15%·매도 0.50%의 연구 비용을 차감한 가상 결과입니다. 실제 체결·세율·슬리피지를 인증하지 않습니다.",
        "MFE·MAE·목표 도달률은 진입일 이후의 실제 관측 봉으로 계산합니다. 진입일 고가를 사후 익절로 처리하지 않습니다.",
        "MFE·MAE와 원시 목표 도달률은 모형 손절 이후의 가격도 포함합니다. 손절 전에 목표에 먼저 도달한 비율과 같은 날 순서 불명 비율은 CSV에 별도로 기록합니다.",
        "영(0) 거래량 봉에서는 체결을 가정하지 않습니다. 종가 손절의 다음 관측 시가, 갭 손실과 미완료 관찰을 별도로 기록합니다.",
        "시장 강약·수급·뉴스의 시점 검증과 포트폴리오 최대낙폭은 미완료이며 수치를 만들지 않았습니다."])
    (root/"BENCHMARK.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history-dir");p.add_argument("--manifest")
    p.add_argument("--archive");p.add_argument("--archive-status")
    p.add_argument("--members");p.add_argument("--basic-dir")
    p.add_argument("--market-csv",help="Optional observed 069500 market reference; never certifies session scope")
    p.add_argument("--calendar",required=True);p.add_argument("--outdir",required=True)
    a=p.parse_args()
    if a.archive:
        if not all((a.archive_status,a.members,a.basic_dir)):
            p.error("--archive needs --archive-status, --members and --basic-dir")
        panel,sessions,audit=load_archived_panel(a.archive,a.archive_status,a.calendar,a.members,a.basic_dir)
    else:
        if not a.history_dir or not a.manifest:
            p.error("provide --history-dir and --manifest, or --archive inputs")
        panel,sessions,audit=load_panel(a.history_dir,a.manifest,a.calendar)
    benchmark=read_bars(a.market_csv) if a.market_csv else None
    result=run_benchmark(panel,sessions,benchmark)
    if benchmark:
        result["market_reference_sha256"]=sha(a.market_csv)
        result["untested"].remove("MARKET_REGIME_BENCHMARK")
    result["data_audit"]=audit
    result["data_summary"]=dict(tickers=sorted(panel),ticker_count=len(panel),
        bars=sum(len(x) for x in panel.values()),start=min(x[0]["date"] for x in panel.values()),
        end=max(x[-1]["date"] for x in panel.values()),full_market_tested=False)
    result["code_sha256"]={name:sha(Path(__file__).parent/name) for name in
        ("c3_entry_benchmark_v1.py","c3_entry_geometry_v23.py","c3_ict_sequence_research_v1.py")}
    write_outputs(result,a.outdir)
    print(json.dumps(dict(data=result["data_summary"],decisions=result["frozen_decision_count"],
                          decision="CASH",strategy_profitability_verified=False)))


if __name__=="__main__":
    main()
