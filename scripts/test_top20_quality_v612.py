"""v6.12 100-to-20 quality discovery index, not future win probability."""
from __future__ import annotations
import csv,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from top20_quality_v612 import (
    SCHEMA,WEIGHTS,COHORT_TARGETS,metrics,score,dart_prior,
    validate_source,save,TOP_FIELDS,risk_priority_reason)
from dart_dated_evidence_v610 import SOURCE_FIELDS

DAY="2026-10-23"
DATES=["2026-10-19","2026-10-20","2026-10-21","2026-10-22","2026-10-23"]

def series(close_fn=lambda i:100+.2*i,volume_fn=lambda i:1000):
    dates=[];d=date(2026,10,23)
    while len(dates)<120:
        if d.weekday()<5:dates.append(d)
        d-=timedelta(days=1)
    dates.reverse()
    out=[]
    for i,d in enumerate(dates):
        c=close_fn(i)
        out.append(dict(ticker="005930",date=d.isoformat(),close=c,
          open=c,high=c+2,low=c-2,volume=volume_fn(i),turnover_krw=c*volume_fn(i)))
    return out

def write(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def disclosures(tmp):
    p=Path(tmp)
    (p/"diagnostics").mkdir(parents=True,exist_ok=True)
    (p/"diagnostics/collection_status.json").write_text(json.dumps({
        "asof":DAY,"datasets":{"dart":{"status":"DATE_ONLY_COMPLETE","rows":4,
        "exact_publication_time":"UNAVAILABLE"}}}))
    def item(no,t,day,title):
        return dict(ticker=t,corp_code="00123456",corp_name="SAMSUNG",
          report_name=title,receipt_no=no,receipt_date=day,
          url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+no,
          published_precision="DAY_ONLY_no_intraday_time",
          collected_at="2026-10-23T12:12:00+00:00",source="OPENDART_list")
    items=[
        item("20261022000001","005930","2026-10-22","영업잠정실적"),
        item("20261023000001","005930","2026-10-23","공급계약"),
        item("20260901000001","005930","2026-09-01","영업잠정실적"),
        item("20261020000001","012345","2026-10-20","자기주식 취득")]
    write(p/"catalysts/disclosures.csv",SOURCE_FIELDS,items)
    return p

class Top20V612Tests(unittest.TestCase):
    def test_weights_are_full_hundred_research_only(self):
        self.assertEqual(SCHEMA,"C3_K100_BALANCED_TOP20_FIVE_DAY_MONEY_QUALITY_V612")
        self.assertEqual(sum(WEIGHTS.values()),100)
        self.assertEqual(sum(cap for _,cap in COHORT_TARGETS),20)
        self.assertEqual(len(set(TOP_FIELDS)),len(TOP_FIELDS))

    def test_healthy_trend_stronger_than_broken_trend_when_flows_equal(self):
        a=series()
        b=series(close_fn=lambda i:140-.2*i)
        flows=[(100,100)]*5
        up=metrics(a,DATES,flows)
        down=metrics(b,DATES,flows)
        good=score(up,500,500)
        bad=score(down,500,500)
        self.assertGreater(good["discovery_index_100"],bad["discovery_index_100"])
        self.assertEqual(good["trend_state"],"UPTREND_OBSERVE")
        self.assertIn(bad["trend_state"],("DOWNTREND_WAIT","TRANSITION_WATCH"))

    def test_unilateral_flow_gets_lower_money_component_than_both(self):
        m=metrics(series(),DATES,[(100,100)]*5)
        a=score(m,500,500)
        b=score(m,1000,-200)
        self.assertGreater(a["money_score25"],b["money_score25"])

    def test_consistent_flow_positive_days_counted_not_assumed(self):
        x=metrics(series(),DATES,[(100,100),(-200,-100),(200,-50),
                                (0,0),(500,400)])
        self.assertEqual(x["fi_positive_session_count"],3)
        self.assertEqual(x["fi_day_positive_foreign_count"],3)
        self.assertEqual(x["fi_day_positive_institution_count"],2)

    def test_20day_extreme_return_flags_chase(self):
        candles=series(close_fn=lambda i:100 if i<119 else 160)
        m=metrics(candles,DATES,[(100,100)]*5)
        self.assertTrue(score(m,500,500)["heat_risk"])
        self.assertEqual(score(m,500,500)["trend_state"],"HOT_CHASE_AVOID")

    def test_missing_or_stale_last_five_days_rejected(self):
        candles=series()
        with self.assertRaisesRegex(ValueError,"V612_PRICE_DATES"):
            metrics(candles,["2026-10-20"]*5,[(1,1)]*5)
        with self.assertRaisesRegex(ValueError,"V612_DAILY_FI"):
            metrics(candles,DATES,[(1,1)]*4)

    def test_no_zero_5day_volume_proxy_or_future(self):
        candles=series()
        candles[-1]["close"]=float("nan")
        with self.assertRaisesRegex(ValueError,"V612_NONFINITE_PRICE"):
            metrics(candles,DATES,[(1,1)]*5)

    def test_dart_day_before_is_observation_but_no_same_day_catalyst(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=disclosures(tmp)
            filings,same,sha,count=dart_prior(p,{"005930"},DAY)
            self.assertEqual(count,4)
            self.assertEqual(len(filings["005930"]),1)
            self.assertEqual(same["005930"],1)
            self.assertEqual(filings["005930"][0]["report_name"],"영업잠정실적")
            self.assertEqual(len(sha),64)

    def test_dart_future_receipt_is_hard_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=disclosures(tmp)
            file=p/"catalysts/disclosures.csv"
            with file.open(encoding="utf-8-sig") as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[-1]["receipt_date"]="2026-10-26"
            write(file,fields,rows)
            with self.assertRaisesRegex(ValueError,"V612_DART_FUTURE"):
                dart_prior(p,{"005930"},DAY)

    def test_no_false_80_score_or_buy_in_mobile_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=dict(schema=SCHEMA,asof=DAY,v611_market_watched=100,
                 v611_total_market=2764,queue_actual={"BACKFILL":0},
                 source_original_market_SHA256={},source_original_fi_flow_SHA256={},
                 top20_count=0,top5_risk_watch_only=[],trade_approved=False,
                 orders_enabled=False,decision="CASH")
            save(Path(tmp),r,[],[])
            m=json.loads((Path(tmp)/"top20_quality_v612_status.json").read_text())
            self.assertEqual(m["top20_count"],0)
            self.assertEqual(len(m["output_file_sha256"]),2)
            self.assertIn("CASH",(Path(tmp)/"top20_quality_v612_mobile.md").read_text())

    def test_overheated_high_score_is_not_top5_risk_prechecked(self):
        candidate=dict(heat_risk=True,atr14_pct=2,return_20d_pct=10,
            distance_from_sma20_pct=2,sma20_slope_5d_pct=1)
        self.assertEqual(risk_priority_reason(candidate),"OVERHEATED_MOMENTUM_OR_DISTANCE")
        self.assertEqual(risk_priority_reason({**candidate,"heat_risk":False}),
                         "RISK_PRECHECK_WATCH_NOT_ORDER")
        self.assertEqual(risk_priority_reason({**candidate,"heat_risk":False,
                 "atr14_pct":8.1}),"ATR14_TOO_WIDE_FOR_C3_PRECHECK")

    def test_deep_ma20_overshoot_blocks_top5_without_cutting_top20(self):
        c=dict(heat_risk=False,atr14_pct=4.5,return_20d_pct=7,
            distance_from_sma20_pct=12,sma20_slope_5d_pct=2)
        self.assertEqual(risk_priority_reason(c),"MA20_DISTANCE_EXCESSIVE_OR_BELOW_SUPPORT")
        self.assertEqual(risk_priority_reason({**c,"distance_from_sma20_pct":-6}),
                         "MA20_DISTANCE_EXCESSIVE_OR_BELOW_SUPPORT")
        self.assertEqual(risk_priority_reason({**c,"distance_from_sma20_pct":2,
                         "sma20_slope_5d_pct":-0.1}),"MA20_SLOPE_NOT_POSITIVE")

    def test_missing_or_tampered_upstream_status_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"w";b=Path(tmp)/"i"
            a.mkdir();b.mkdir()
            (a/"broad_watch_v611_status.json").write_text(json.dumps(
                dict(schema=SCHEMA,asof=DAY,trade_approved=True)))
            (b/"issuer_entry_v610_status.json").write_text(json.dumps(dict(
                schema="other",asof=DAY)))
            (b/"basic").mkdir()
            (b/"basic/krx_basic_v610_status.json").write_text("{}")
            with self.assertRaisesRegex(ValueError,"V612_FROZEN_PREDECESSOR"):
                validate_source(a,a,b)

if __name__=="__main__":unittest.main()
