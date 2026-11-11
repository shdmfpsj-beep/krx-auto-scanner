#!/usr/bin/env python3
"""User-requested *one-time* correction of 2026-11-11 C3 TOP2 old image album.

A versioned separate receipt preserves the initial real 2-photo delivery and
never silently retries or replaces it. Revision is research-only CASH, one
captionless PNG; it cannot authorize trades or mutate frozen selections.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from PIL import Image,ImageDraw,ImageFont
from c3_telegram_inputs import GitHub
from c3_telegram_notify import ReceiptStore,Telegram,RECEIPT_BRANCH

DATE="2026-11-11"
SOURCE_RUN_ID="43086941571"
SCAN_RUN_ID="43121137444"
OFFICIAL_MATCH_RUN_ID="43119600667"
KST=ZoneInfo("Asia/Seoul")


def validated_summary(path):
    q=json.loads(Path(path).read_text(encoding="utf-8"))
    expected={
        "schema":"C3_NOV11_READONLY_ENTRY_FEASIBILITY_RESELECTION_V1",
        "price_asof":DATE,
        "original_source_run_id":SOURCE_RUN_ID,
        "full_market_price_rows":2769,
        "analysis_eligible":1988,
        "stock_preselector_count":149,
        "original_b_filter_count":50,
        "eligible_entry_feasible_tickers":0,
        "new_research_top2":[],
        "revision_status":"CASH_NO_ENTRY_FEASIBLE",
        "session_regular_only_certified":False,
        "trade_approved":False,
        "orders_enabled":False,
        "decision":"CASH",
        "original_signal_ledger_modified":False,
        "telegram_sent":False,
        "telegram_original_date_resend_forbidden":True,
    }
    if any(q.get(k)!=v for k,v in expected.items()):
        raise ValueError("FROZEN_CORRECTION_RESELECTION_CONTRACT_MISMATCH")
    limits=q.get("thresholds",{})
    if (limits.get("max_entry_gap_below_close_pct")!=8 or
        limits.get("max_structure_stop_risk_pct")!=8 or
        limits.get("minimum_costed_r1_reward_risk")!=1.5):
        raise ValueError("CORRECTION_THRESHOLD_CHANGED")
    return q


def render(q,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    im=Image.new("RGB",(1200,1420),(253,253,252));d=ImageDraw.Draw(im)
    candidates=[
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    ]
    regular=[
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    ]
    b=next((x for x in candidates if Path(x).exists()),None)
    reg=next((x for x in regular if Path(x).exists()),b)
    if not b:raise ValueError("KOREAN_FONT_MISSING")
    fb=lambda n:ImageFont.truetype(b,n)
    fr=lambda n:ImageFont.truetype(reg,n)
    ink=(30,32,36);gold=(166,121,48);mute=(105,109,116);bg=(249,247,241)
    d.rectangle((0,0,1200,20),fill=gold)
    d.text((80,92),"강현AI PRO  |  C3 TOP2",font=fb(42),fill=ink)
    d.text((80,165),"11월 11일 재선별 정정 보고",font=fb(51),fill=ink)
    d.text((80,238),"기존 삼성E&A · 한진칼 이미지의 신규 매수 타점 제시를 정정합니다.",font=fr(26),fill=mute)
    d.rounded_rectangle((80,313,1120,660),radius=30,fill=bg)
    d.text((122,347),"최종 검토 결과",font=fb(34),fill=ink)
    d.text((122,417),"CASH",font=fb(108),fill=gold)
    d.text((535,444),"매수 조건 통과 종목  0개",font=fb(37),fill=ink)
    d.text((126,560),"기존 TOP2 재전송 없음 · 새 종목 임의 대체 없음",font=fr(27),fill=ink)
    d.text((84,741),"11/11 전체시장 재검증",font=fb(39),fill=ink)
    steps=[("일별 가격 수집·공식 수치 대조","2,769종목"),
           ("분석 가능 종목","1,988종목"),
           ("기술적 1차 후보","149종목"),
           ("기존 B 조건 통과","50종목"),
           ("타점 안전성 조건 통과","0종목")]
    y=808
    for name,amount in steps:
        d.line((82,y+57,1118,y+57),fill=(226,224,219),width=2)
        d.text((92,y),name,font=fr(30),fill=ink)
        bb=d.textbbox((0,0),amount,font=fb(32))
        d.text((1110-(bb[2]-bb[0]),y),amount,font=fb(32),fill=gold)
        y+=82
    d.text((88,1260),"기준: 매수 거리 ≤8% · 손절 위험 ≤8% · 순손익비 ≥1.5",font=fr(26),fill=ink)
    d.text((88,1310),"연구 전용 | 정규장 15:30 수치 독립인증 미완료 | 실거래 금지",font=fr(23),fill=mute)
    im.save(path,format="PNG",optimize=True)
    with Image.open(path) as z:
        if z.format!="PNG" or z.size!=(1200,1420):raise ValueError("CORRECTION_IMAGE_INVALID")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deliver(summary,image,gh,bot):
    store=ReceiptStore(gh)
    store.initialize()
    original_key="final/"+DATE+"-"+bot.fingerprint
    oldraw=gh.file("receipts/outcomes/"+original_key+".json",RECEIPT_BRANCH,
                   missing_ok=True)
    if not oldraw:raise ValueError("PREVIOUS_ALBUM_DELIVERY_NOT_PROVEN")
    old=json.loads(oldraw)
    if (old.get("status")!="DELIVERED" or
        old.get("source_date")!=DATE or old.get("message_ids")!=[40,41]):
        raise ValueError("PREVIOUS_DELIVERED_ALBUM_MISMATCH")
    correction_key="correction/"+DATE+"-entry-geometry-v1-"+bot.fingerprint
    if store.exists(correction_key):
        return dict(status="DUPLICATE_BLOCKED",send_attempts=0,key=correction_key)
    bot.verify_group()
    sha=hashlib.sha256(Path(image).read_bytes()).hexdigest()
    claim={
        "schema":"C3_EXPLICIT_REQUEST_NOV11_RESELECTION_CORRECTION_V1",
        "source_date":DATE,"original_source_run_id":SOURCE_RUN_ID,
        "reselection_run_id":SCAN_RUN_ID,
        "official_eod_cache_match_run_id":OFFICIAL_MATCH_RUN_ID,
        "original_message_ids":[40,41],"new_candidate_count":0,
        "correction_only":True,"source_regular_only_certified":False,
        "card_sha256":sha,"recipient_verified":True,
        "status":"CLAIMED_BEFORE_SEND",
        "claimed_at":datetime.now(KST).isoformat(),
        "automatic_resend_allowed":False,"orders_enabled":False,
        "sender_run_id":os.environ.get("GITHUB_RUN_ID")}
    if not store.reserve(correction_key,claim):
        return dict(status="DUPLICATE_BLOCKED",send_attempts=0,key=correction_key)
    try:
        with Path(image).open("rb") as f:
            response=requests.post(
                "https://api.telegram.org/bot"+bot.token+"/sendPhoto",
                data={"chat_id":bot.chat_id},
                files={"photo":(Path(image).name,f,"image/png")},
                timeout=(10,65),allow_redirects=False)
        payload=response.json() if response.status_code==200 else {}
        msg=payload.get("result") or {}
        valid=(payload.get("ok") is True and type(msg.get("message_id")) is int
               and msg["message_id"]>0 and msg.get("photo")
               and str(msg.get("chat",{}).get("id"))==bot.chat_id
               and "caption" not in msg and "text" not in msg)
        if not valid:raise ValueError("TELEGRAM_DELIVERY_RESPONSE_UNCERTAIN")
        outcome=dict(status="DELIVERED",message_ids=[msg["message_id"]],
                     photos=1,text_present=False,captions_present=False,
                     send_attempts=1,key=correction_key,source_date=DATE)
    except Exception as exc:
        outcome=dict(status="REVIEW_REQUIRED_NO_AUTOMATIC_RESEND",
                     error_type=type(exc).__name__,send_attempts=1,
                     key=correction_key,source_date=DATE)
    outcome.update(recorded_at=datetime.now(KST).isoformat(),
                   sender_run_id=os.environ.get("GITHUB_RUN_ID"),
                   correction_of_original_message_ids=[40,41],
                   card_sha256=sha)
    try:store.finish(correction_key,outcome)
    except Exception:outcome["receipt_write_status"]="FAILED_CLAIM_REMAINS_NO_RESEND"
    return outcome


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--summary",required=True)
    p.add_argument("--outdir",required=True)
    args=p.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    summary=validated_summary(args.summary)
    card=out/"C3_20261111_CORRECTION_CASH.png"
    image_sha=render(summary,card)
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        raise ValueError("TELEGRAM_SECRETS_NOT_CONFIGURED")
    gh=GitHub(os.environ.get("GH_TOKEN",""))
    bot=Telegram(os.environ["TELEGRAM_BOT_TOKEN"],os.environ["TELEGRAM_CHAT_ID"])
    result=deliver(summary,card,gh,bot)
    result["image_sha256"]=image_sha
    (out/"correction_delivery_status.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("C3_NOV11_CORRECTION_DELIVERY="+json.dumps(result,ensure_ascii=False),
          flush=True)
    if result["status"] not in ("DELIVERED","DUPLICATE_BLOCKED"):
        raise SystemExit(2)


if __name__=="__main__":main()
