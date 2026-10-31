#!/usr/bin/env python3
"""Read only public Telegram HTML previews for C3 news evidence, NOT recommendations.

No Telegram account, api_id, api_hash, bot, login, membership or private content.
The public /s/ preview may return only a subset of messages. Fail closed if it
cannot be read. Neither channel messages nor absence affect buy eligibility.
"""
from __future__ import annotations
import argparse,csv,json,re,time
from datetime import datetime,timedelta,timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

CHANNELS=("Jegalstock","good_trader_x100")
SECTORS={
 "SEMICON":("반도체","하이닉스","메모리","hbm","엔비디아","삼성전자","chip","gpu"),
 "ROBOT":("로봇","휴머노이드","피지컬ai","보스턴다이내믹스","robot"),
 "POWER":("전력","변압기","전력반도체","송전","grid"),
 "AUTO":("자동차","현대차","기아","자율주행","테슬라","electric vehicle"),
 "SHIP":("조선","lng선","선박","shipbuilding"),
 "DEFENSE":("방산","미사일","무기","defense"),
 "BATTERY":("2차전지","배터리","리튬","ess","battery"),
 "SECURITIES":("증권","코스피","코스닥","기관","외국인","주식","지수"),
 "IT":("ai","데이터센터","빅테크","클라우드","capex"),
}
FIELDS=("channel","post_id","post_url","published_at_utc","age_hours",
        "content_excerpt","sector_ids","external_urls","source_verification")
SCHEMA="C3_PUBLIC_TELEGRAM_PREVIEW_RESEARCH_V1"

def attrs_dict(attrs):
    return {k:v for k,v in attrs}

class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0;self.message=None;self.message_depth=None
        self.text_depth=None;self.messages=[];self.links=[]
        self.preview_detected=False
    def handle_starttag(self,tag,attrs):
        a=attrs_dict(attrs)
        cls=set((a.get("class") or "").split())
        if tag=="div":
            self.depth+=1
            if "tgme_widget_message" in cls and a.get("data-post"):
                self.preview_detected=True
                if self.message is not None: self._finish()
                self.message={"data_post":a["data-post"],"published_at":None,"pieces":[],"urls":[]}
                self.message_depth=self.depth
            elif self.message is not None and "tgme_widget_message_text" in cls:
                self.text_depth=self.depth
        if self.message is not None:
            if tag=="time" and a.get("datetime"):
                self.message["published_at"]=a["datetime"]
            if tag=="a" and self.text_depth is not None:
                href=(a.get("href") or "").strip()
                if href.startswith(("https://","http://")) and len(href)<1000:
                    if not href.startswith(("https://t.me/","http://t.me/")):
                        self.message["urls"].append(href)
            if tag=="br" and self.text_depth is not None:
                self.message["pieces"].append("\n")
    def handle_endtag(self,tag):
        if tag!="div":return
        if self.message is not None and self.text_depth==self.depth:
            self.text_depth=None
        if self.message is not None and self.message_depth==self.depth:
            self._finish()
        self.depth=max(0,self.depth-1)
    def handle_data(self,data):
        if self.message is not None and self.text_depth is not None:
            self.message["pieces"].append(data)
    def close(self):
        super().close()
        if self.message is not None:self._finish()
    def _finish(self):
        if self.message:self.messages.append(self.message)
        self.message=None;self.message_depth=None;self.text_depth=None

def parse_preview(html,channel,now=None,hours=72):
    now=now or datetime.now(timezone.utc)
    if now.utcoffset() is None:raise ValueError("AWARE_UTC_NOW_REQUIRED")
    parser=PreviewParser()
    parser.feed(html);parser.close()
    out=[];invalid_date=0;old=0;future=0
    seen=set()
    for m in parser.messages:
        identifier=m["data_post"]
        prefix=channel+"/"
        if not identifier.lower().startswith(prefix.lower()):continue
        suffix=identifier[len(prefix):]
        if not suffix.isdigit() or identifier in seen:continue
        seen.add(identifier)
        try:
            date=datetime.fromisoformat(str(m["published_at"]).replace("Z","+00:00"))
            if date.tzinfo is None:raise ValueError("NAIVE_POST_TIME")
            date=date.astimezone(timezone.utc)
        except (ValueError,TypeError):
            invalid_date+=1;continue
        age=(now-date).total_seconds()/3600
        if age < -0.08333:
            future+=1;continue
        if age>hours:
            old+=1;continue
        text=re.sub(r"[ \t]+"," ","".join(m["pieces"]))
        text=re.sub(r"\n{3,}","\n\n",text).strip()
        if not text:continue
        tokens=text.lower()
        sectors=[key for key,terms in SECTORS.items() if any(t in tokens for t in terms)]
        out.append(dict(channel=channel,post_id=suffix,
            post_url="https://t.me/"+identifier,published_at_utc=date.isoformat(),
            age_hours=round(max(0,age),1),content_excerpt=text[:700],
            sector_ids=";".join(sectors) or "UNCLASSIFIED",
            external_urls=";".join(dict.fromkeys(m["urls"]))[:1500],
            source_verification="PUBLIC_HTML_POST_DATE_ONLY_NOT_FACT_CHECKED"))
    out.sort(key=lambda x:x["published_at_utc"],reverse=True)
    return out,dict(preview_widget_found=parser.preview_detected,
       preview_posts_found=len(parser.messages),posts_dated_recent=len(out),
       posts_without_valid_time=invalid_date,old_posts_ignored=old,
       future_posts_ignored=future,preview_may_be_truncated=True)

def fetch(channel,opener=urlopen):
    if channel not in CHANNELS:raise ValueError("UNREGISTERED_CHANNEL")
    url=f"https://t.me/s/{channel}"
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; C3-public-preview-evidence/1.0)",
                             "Accept":"text/html"})
    with opener(req,timeout=14) as response:
        result=response.read(1_500_001)
    if len(result)>1_500_000:raise ValueError("PUBLIC_PREVIEW_TOO_LARGE")
    return result.decode("utf-8",errors="replace")

def run(output,now=None,fetcher=fetch):
    now=now or datetime.now(timezone.utc)
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    result=[];channels={}
    for channel in CHANNELS:
        try:
            html=fetcher(channel)
            posts,meta=parse_preview(html,channel,now=now)
            if not meta["preview_widget_found"]:
                state="PUBLIC_POST_PREVIEW_NOT_AVAILABLE"
            else:
                state="PUBLIC_PREVIEW_OBSERVED"
            channels[channel]=dict(status=state,**meta)
            result.extend(posts)
        except (HTTPError,URLError,TimeoutError,ValueError,OSError) as e:
            channels[channel]=dict(status="NOT_ACCESSIBLE_OR_REQUEST_FAILED",
                                   error_type=type(e).__name__,
                                   preview_may_be_truncated=True,posts_dated_recent=0)
    result.sort(key=lambda x:x["published_at_utc"],reverse=True)
    path=root/"c3_telegram_public_posts_72h.csv"
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(result)
    status=dict(schema=SCHEMA,captured_at_utc=now.isoformat(),lookback_hours=72,
       channels=channels,dated_72h_posts=len(result),
       source_scope="ONLY_PUBLIC_UNAUTHENTICATED_HTML_PREVIEW",
       no_private_groups_read=True,not_full_channel_history=True,
       no_missing_news_penalty=True,
       text_is_author_opinion_not_confirmed_catalyst=True,
       no_real_investor_flows_inferred=True,
       not_new_price_data=True,orders_enabled=False,buy_approved=False)
    (root/"c3_telegram_public_status.json").write_text(
        json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report=["## 텔레그램 공개방 보조자료 (최근 72시간·날짜 확인된 글만)",
       f"- 수집 시각 UTC: {now.isoformat()}",
       f"- 날짜 확인된 최근 게시물: {len(result)}건 · 미공개/비공개 원문이나 누락글은 확인 불가"]
    for ch in CHANNELS:
        state=channels[ch]
        report.append(f"- @{ch}: {state['status']} / 날짜 확인 최근 {state.get('posts_dated_recent',0)}건")
    report.append("- 원문 의견은 매수 신호가 아니며 사실검증 전 호재·수급 확정 금지")
    for v in result[:6]:
        snippet=v["content_excerpt"].replace("\n"," ").strip()[:110]
        report.append(f"- [{v['channel']} {v['published_at_utc'][:16]}]({v['post_url']}): {snippet}")
    (root/"c3_telegram_mobile_summary.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    return status

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True)
    args=p.parse_args()
    print(json.dumps(run(args.out),ensure_ascii=False))
