#!/usr/bin/env python3
"""ONE-TIME visual demo for user-requested 2026-11-05 C3 TOP2 previews.
Only verified historical OHLC and published financial facts are drawn.
Creates four 1080x1440 PNGs; never places execution evidence in the media.
"""
import json, os, pathlib, sys
from PIL import Image, ImageDraw, ImageFont
import requests

OUT=pathlib.Path("/tmp/c3-telegram-demo-20261106");OUT.mkdir(parents=True,exist_ok=True)
FONT_PATH="/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
BOLD_PATH="/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
BG="#081222"; PANEL="#102038"; LINE="#263a55"; MUTED="#a4b9d4"; WHITE="#f4f7fc"
YELLOW="#ffd35e"; GREEN="#48dc93"; RED="#ff627f"; BLUE="#51b6ff"; PURPLE="#d69aff"
def F(size,bold=False):return ImageFont.truetype(BOLD_PATH if bold else FONT_PATH,size)
def label(d,xy,s,size=27,color=WHITE,bold=False,anchor=None):
    d.text(xy,str(s),font=F(size,bold),fill=color,anchor=anchor)
def panel(d,xy,fill=PANEL,stroke=LINE,r=24,width=2):
    d.rounded_rectangle(xy,radius=r,fill=fill,outline=stroke,width=width)
def hline(d,xy,clr=LINE,w=2):d.line(xy,fill=clr,width=w)
def money(v):return f"{v:,}원" if v is not None else "미확정"
def linewrap(d,text,width,size=28,bold=False):
    lines=[]
    for para in text.split("\n"):
        words=para.split(" ");curr=""
        for w in words:
            candidate=(curr+" "+w).strip()
            if d.textbbox((0,0),candidate,font=F(size,bold))[2]<=width:
                curr=candidate
            else:
                if curr:lines.append(curr)
                curr=w
        if curr:lines.append(curr)
    return lines
def bullet_block(d,text,x,y,max_width,size=26,fill=WHITE,line_space=10):
    for raw in text:
        lines=linewrap(d,raw,max_width-27,size)
        for k,li in enumerate(lines):
            label(d,(x+(24 if k else 0),y),("• " if k==0 else "")+li,size,fill)
            y+=size+line_space
        y+=6
    return y
def common(d,stock,page):
    d.rounded_rectangle((18,18,1062,1422),radius=30,outline="#27476a",width=3)
    panel(d,(34,34,1046,170),fill="#11233c",stroke="#203c60",r=22)
    label(d,(62,52),"제갈AI PRO  |  C3 TOP2",43,YELLOW,True)
    label(d,(64,116),"2026.11.05 정규장 데이터 · 과거 연구 예시",22,MUTED)
    label(d,(1008,64),f"{page}/2",29,WHITE,True,anchor="ra")
    label(d,(54,202),stock["name"],49,WHITE,True)
    label(d,(1042,219),stock["ticker"],26,MUTED,anchor="ra")
def footer(d,stock):
    panel(d,(35,1346,1045,1398),fill="#0b1a2c",stroke="#29435f",r=14)
    label(d,(60,1355),"※ 과거 연구 후보 미등록 · 매수 지시 아님 · 2차 매수 가격 미확정",21,MUTED)
def page_one(s):
    im=Image.new("RGB",(1080,1440),BG); d=ImageDraw.Draw(im)
    common(d,s,1)
    panel(d,(36,280,1044,390),fill="#11233c")
    label(d,(62,295),"기준 종가",26,MUTED)
    label(d,(62,328),money(s["close"]),42,WHITE,True)
    label(d,(1015,322),s["day_move"],32,RED,True,anchor="ra")
    label(d,(62,408),"실제 OHLC 일봉 · 5일 이동평균 · 가격 구간",27,WHITE,True)
    chart=(103,480,985,978);x0,y0,x1,y1=chart
    ys=[r[2] for r in s["bars"]]+[r[3] for r in s["bars"]]+[r[4] for r in s["bars"]]
    levels=[s["stop"],s["buy1"][0],s["buy1"][1]]
    levels += [v for v in s["resist"] if v]
    ymin=min(ys+levels)*0.94; ymax=max(ys+levels)*1.04
    yval=lambda v: y1-(v-ymin)/(ymax-ymin)*(y1-y0)
    for i in range(6):
        value=ymin+(ymax-ymin)*i/5; yy=yval(value)
        hline(d,[(x0,yy),(x1,yy)],"#1a2c43",1)
        label(d,(x0-13,yy),f"{int(value/100)*100:,}",17,MUTED,anchor="ra")
    n=len(s["bars"]);left=x0+35; right=x1-55;gap=(right-left)/(n-1)
    if s["buy1"]:
        low,high=s["buy1"];d.rectangle((x0,yval(high),x1,yval(low)),fill="#123a32")
        hline(d,[(x0,yval(low)),(x1,yval(low))],GREEN,2);hline(d,[(x0,yval(high)),(x1,yval(high))],GREEN,2)
    for value,color in [(s["stop"],RED),(s["resist"][0],YELLOW),(s["resist"][1],PURPLE)]:
        if value:
            yy=yval(value);d.line([(x0,yy),(x1,yy)],fill=color,width=2)
    closes=[];pts=[]
    for i,(day,op,hi,lo,cl,vol) in enumerate(s["bars"]):
        cx=left+i*gap; col=RED if cl>=op else BLUE
        d.line((cx,yval(hi),cx,yval(lo)),fill=col,width=3)
        top,bottom=sorted((yval(op),yval(cl)))
        d.rectangle((cx-13,top,cx+13,max(top+3,bottom)),fill=col,outline=col)
        closes.append(cl)
        if len(closes)>=5:pts.append((cx,yval(sum(closes[-5:])/5)))
        if i%2==0 or i==n-1:label(d,(cx,1003),day,18,MUTED,anchor="ma")
    if len(pts)>1:d.line(pts,fill=YELLOW,width=4,joint="curve")
    label(d,(78,1042),"실제 가격 차트 (11월 5일까지)   ● 5일선   ━ 지지·저항",22,MUTED)
    panel(d,(39,1092,1043,1323),fill="#101f35")
    label(d,(61,1108),"매매 관찰 기준  |  신규 매수 대기",30,WHITE,True)
    label(d,(63,1165),f"1차 매수 범위   {money(s['buy1'][0])} ~ {money(s['buy1'][1])}",27,GREEN,True)
    label(d,(63,1207),"2차 매수 범위   미확정 (구조 재평가 후 산정)",25,BLUE)
    label(d,(63,1249),f"구조손절 {money(s['stop'])}   |   1차 저항 {money(s['resist'][0])}",25,WHITE)
    label(d,(63,1287),f"2차 저항 {money(s['resist'][1])}   |   최종 판단 CASH",24,YELLOW,True)
    footer(d,s)
    p=OUT/(s["ticker"]+"_01_chart.png");im.save(p,optimize=True);return p
def info_card(d,rect,title,lines,color):
    panel(d,rect,fill="#102139",stroke=color,r=18,width=2)
    x0,y0,x1,y1=rect
    label(d,(x0+24,y0+15),title,29,color,True)
    hline(d,[(x0+20,y0+58),(x1-20,y0+58)],"#2b425b",2)
    bullet_block(d,lines,x0+24,y0+74,x1-x0-52,size=24)
def page_two(s):
    im=Image.new("RGB",(1080,1440),BG);d=ImageDraw.Draw(im)
    common(d,s,2)
    label(d,(53,279),"선정 근거 · 실적 · 재료 · 리스크",35,WHITE,True)
    positions=[(38,347,528,587),(552,347,1042,587),
               (38,606,528,846),(552,606,1042,846)]
    titles=["섹터 · 재료","재무 · 실적","이슈 · 이벤트","펀더멘털 · 리스크"]
    cols=[BLUE,GREEN,YELLOW,PURPLE]
    for rect,title,lines,color in zip(positions,titles,s["notes"],cols):
        info_card(d,rect,title,lines,color)
    panel(d,(36,872,1045,1097),fill="#11233c",stroke="#2a4769")
    label(d,(63,887),"C3 정량 선정 근거",31,YELLOW,True)
    label(d,(63,940),f"상대강도(RS20)   {s['rs20']:+.2f}%p",29,WHITE,True)
    label(d,(63,987),f"최근 5일 상대강도 변화   {s['rsaccel']:+.2f}%p",27,WHITE)
    label(d,(63,1035),"선정 규칙: 추세 · 시장대비 강도 · 거래대금",25,MUTED)
    panel(d,(36,1114,1045,1328),fill="#171d35",stroke="#6359a2")
    label(d,(63,1129),"타점 · 대응 전략",31,WHITE,True)
    label(d,(64,1180),f"1차 매수 {money(s['buy1'][0])} ~ {money(s['buy1'][1])}",27,GREEN,True)
    label(d,(64,1222),"2차 매수 미확정 · 추격 매수 제한",26,BLUE)
    label(d,(64,1265),f"손절 {money(s['stop'])}  /  1차 저항 {money(s['resist'][0])}  /  CASH",23,WHITE)
    footer(d,s)
    p=OUT/(s["ticker"]+"_02_reason.png");im.save(p,optimize=True);return p

STOCKS=[
  {"ticker":"028050","name":"삼성E&A","close":64300,"day_move":"-1.83% (전일 대비)",
   "buy1":(60700,63500),"stop":57700,"resist":(65500,None),"rs20":53.1764,"rsaccel":6.4031,
   "bars":[("10/26",59400,60900,57700,59800,5666914),
     ("10/27",60700,63900,60100,62200,4853393),
     ("10/28",63000,64900,62200,64200,4237254),
     ("10/29",64200,65500,62400,62800,3393336),
     ("10/30",62300,62800,60400,61700,2293307),
     ("11/02",60700,64000,59700,63200,1850653),
     ("11/03",62900,64000,61600,61600,1913027),
     ("11/04",62500,65700,62400,65500,4173981),
     ("11/05",65600,67700,63800,64300,3054309)],
   "notes":[
     ["화공·첨단산업 플랜트 EPC 사업","사우디 대형 비료 프로젝트 수주","AI·뉴에너지 투자 수요 연결"],
     ["3분기 매출 2조 9,105억원","3분기 영업이익 5,006억원","전년 동기 영업익 +183.6%"],
     ["3분기 누적 수주 17.1조원","자기주식 취득 7,800억원 결정","수주 전망 19조원 상향"],
     ["수주잔고 27.2조원 확보","직전 고점 67,700원 대비 변동성","1차 지지 확인 전 CASH"]]},
  {"ticker":"030530","name":"원익홀딩스","close":26950,"day_move":"-10.47% (전일 대비)",
   "buy1":(22100,23500),"stop":20600,"resist":(30400,31900),"rs20":17.2605,"rsaccel":0.4455,
   "bars":[("10/23",22300,22550,21600,22200,647278),
      ("10/26",22050,24750,22050,23550,2116914),
      ("10/27",23750,24850,23000,23750,1021774),
      ("10/28",24200,29900,24200,28000,6642274),
      ("10/29",27550,28750,27000,28050,2951661),
      ("10/30",27850,30400,27650,29500,4995151),
      ("11/02",29100,34000,29100,32350,8333354),
      ("11/03",31600,33300,30000,32350,5608289),
      ("11/04",33600,34500,28400,30100,5798196),
      ("11/05",29650,29900,26550,26950,3018147)],
   "notes":[
     ["반도체 가스공급·장비 사업","로봇·AMR 등 신사업 보유","반도체 설비투자 회복은 관찰 재료"],
     ["2026년 2분기 매출 1,765억원","전년동기 매출 +12%","영업이익 128억원, 흑자전환"],
     ["11/2 고가 34,000원 이후 조정","11/5 종가 -10.47% 급락","3분기 실적 발표 전 확인 필요"],
     ["시장 대비 상대강도는 양호","급등 후 변동성·낙폭 확대","새로운 지지 확인 전 CASH"]]}
]
def main():
    files=[]
    for stock in STOCKS:files.extend((page_one(stock),page_two(stock)))
    print("VISUAL_CARDS_RENDERED=4",flush=True)
    if "--dry-run" in sys.argv:return
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip();chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:print("TELEGRAM_SECRETS_MISSING");raise SystemExit(2)
    if chat!="-5578368803":print("GROUP_CHAT_ID_MISMATCH");raise SystemExit(2)
    opened=[];media=[];parts=[]
    try:
        for i,p in enumerate(files):
            fh=open(p,"rb");opened.append(fh)
            parts.append((f"photo{i}",(p.name,fh,"image/png")))
            item={"type":"photo","media":f"attach://photo{i}"}
            if i==0:item["caption"]="📊 C3 TOP2 이미지 4장 테스트 | 2026.11.05 연구 후보\n① 삼성E&A 차트 ② 삼성E&A 선정 이유 ③ 원익홀딩스 차트 ④ 원익홀딩스 선정 이유\n※ 신규 매수 신호가 아닌 과거 예시입니다. CASH"
            media.append(item)
        try:
            res=requests.post(f"https://api.telegram.org/bot{token}/sendMediaGroup",
                              data={"chat_id":chat,"media":json.dumps(media,ensure_ascii=False)},files=parts,timeout=55)
            response=res.json()
        except Exception as e:
            print("TELEGRAM_ALBUM_TRANSPORT_FAILURE_"+type(e).__name__);raise SystemExit(1)
        if not res.ok or not response.get("ok") or len(response.get("result",[]))!=4:
            print("TELEGRAM_ALBUM_REJECTED_HTTP_"+str(res.status_code));raise SystemExit(1)
        print("C3_TOP2_FOUR_IMAGE_ALBUM_DELIVERED",flush=True)
    finally:
        for fh in opened:fh.close()
if __name__=="__main__":main()
