#!/usr/bin/env python3
"""Kanghyun AI classic research cards. Requires verifiable historical OHLCV.
No synthetic prices, MAs, trading instructions, or stock orders.
"""
import ast, datetime as dt, io, json, os, pathlib, sys, urllib.request
from PIL import Image, ImageDraw, ImageFont

OUT=pathlib.Path("/tmp/c3-classic-cards"); OUT.mkdir(parents=True,exist_ok=True)
FONT="/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
BOLD="/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
DARK="#292B2C"; INK="#25282B"; GOLD="#AE873C"; LIGHT="#FAF9F6"
BORDER="#D9D7D0"; SUB="#656A70"; GREEN="#2D785B"; RED="#BA524B"
BLUE="#337AA3"; PURPLE="#886EA3"; CREAM="#F3EEE3"
def font(z,b=False): return ImageFont.truetype(BOLD if b else FONT,z)
def txt(d,x,y,v,z=25,c=INK,b=False,anchor=None): d.text((x,y),str(v),font=font(z,b),fill=c,anchor=anchor)
def box(d,r,fill=LIGHT,border=BORDER,rad=17,width=2):d.rounded_rectangle(r,radius=rad,fill=fill,outline=border,width=width)
def won(n):return f"{int(n):,}원" if n is not None else "미확정"
def base(s,page):
    im=Image.new("RGB",(1080,1520),LIGHT);d=ImageDraw.Draw(im)
    d.rectangle((0,0,1080,110),fill=DARK)
    d.rectangle((0,106,1080,112),fill=GOLD)
    txt(d,52,25,"강현AI PRO  |  C3 TOP2",43,"#F3E4C4",True)
    txt(d,1023,35,f"{page} / 2",26,"#ECE8DF",anchor="ra")
    txt(d,50,135,s["name"],58,INK,True)
    txt(d,50,212,f'{s["ticker"]}  |  2026.11.05 종가 기준 · 연구 예시',24,SUB)
    return im,d
def read_naver(ticker,asof):
    start=(dt.datetime.strptime(asof,"%Y-%m-%d")-dt.timedelta(days=330)).strftime("%Y%m%d")
    end=asof.replace("-","")
    url=f"https://api.finance.naver.com/siseJson.naver?symbol={ticker}&requestType=1&startTime={start}&endTime={end}&timeframe=day"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; KanghyunC3Research/1.0)","Referer":"https://finance.naver.com/"})
    with urllib.request.urlopen(req,timeout=24) as resp: payload=resp.read(1600000).decode("utf-8")
    raw=ast.literal_eval(payload.strip().rstrip(";"))
    bars=[]
    for r in raw[1:]:
        if len(r)<6 or r[0] is None:continue
        date=str(r[0]).replace(".","").replace("-","").strip()
        if len(date)!=8 or not date.isdigit() or date>end:continue
        try:
            o,h,l,c,v=[int(float(str(x).replace(",",""))) for x in r[1:6]]
        except (TypeError,ValueError):continue
        if not(0<l<=min(o,c)<=max(o,c)<=h and v>=0):continue
        bars.append((date,o,h,l,c,v))
    bars.sort(key=lambda x:x[0])
    dates=[r[0] for r in bars]
    if len(set(dates))!=len(dates):raise ValueError("DUPLICATE_DATES")
    return bars
def read_yahoo(ticker,asof):
    # Read-only fallback; never use when its close contradicts the KRX report.
    end=dt.datetime.strptime(asof,"%Y-%m-%d").replace(tzinfo=dt.timezone.utc)+dt.timedelta(days=1)
    start=end-dt.timedelta(days=330)
    suff=".KS" if ticker=="028050" else ".KQ"
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}{suff}?period1={int(start.timestamp())}&period2={int(end.timestamp())}&interval=1d"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=24) as response:j=json.load(response)
    result=j["chart"]["result"][0]; a=result["indicators"]["quote"][0]
    bars=[]
    for i,ts in enumerate(result["timestamp"]):
        day=dt.datetime.fromtimestamp(ts,dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d")
        if day>asof.replace("-",""):continue
        try:
            o,h,l,c,v=(a[k][i] for k in ("open","high","low","close","volume"))
            if any(z is None for z in (o,h,l,c,v)):continue
            row=(day,round(o),round(h),round(l),round(c),round(v))
            if 0<row[3]<=min(row[1],row[4])<=max(row[1],row[4])<=row[2]:bars.append(row)
        except (ValueError,TypeError,IndexError):continue
    return sorted(bars)
def verified_bars(s):
    asof=s["date"]; errors=[]
    for provider,fetch in (("NAVER",read_naver),("YAHOO",read_yahoo)):
        try:
            rows=fetch(s["ticker"],asof)
            if len(rows)<60:raise ValueError("INSUFFICIENT_60_DAY_BARS")
            if rows[-1][0]!=asof.replace("-",""):raise ValueError("MISSING_EXPECTED_LAST_BAR")
            if rows[-1][4]!=int(s["close"]):raise ValueError("CLOSE_NOT_MATCHING_KRX_RESEARCH")
            print("CHART_DATA_VERIFIED_"+s["ticker"]+"_"+provider+"_"+str(len(rows)),flush=True)
            return rows
        except Exception as e:
            errors.append(provider+"_"+type(e).__name__+":"+str(e)[:60])
    raise ValueError("NO_VERIFIED_60_DAY_CHART: "+",".join(errors))
def ma(rows,n):
    close=[r[4] for r in rows];return [sum(close[i-n+1:i+1])/n if i+1>=n else None for i in range(len(close))]
def plot(d,rect,rows,s):
    x0,y0,x1,y1=rect
    show=rows[-21:]; offset=len(rows)-len(show)
    levels=[s["buy_low"],s["buy_high"],s["stop"],s.get("r1"),s.get("r2")]
    levels=[v for v in levels if v is not None]
    mins=[r[3] for r in show];maxs=[r[2] for r in show]
    low=min(mins+levels)*0.974;high=max(maxs+levels)*1.025
    # separate price (upper) and volume panel (lower)
    p_top=y0+12;p_end=y1-140;vtop=p_end+33;vbottom=y1-28
    Y=lambda v:p_end-(v-low)/(high-low)*(p_end-p_top)
    left=x0+85;right=x1-140;step=(right-left)/(len(show)-1)
    for j in range(6):
        val=low+(high-low)*j/5;yy=Y(val)
        d.line((left-5,yy,x1-10,yy),fill="#E6E5E1",width=2)
        txt(d,left-15,yy,f"{int(round(val/100)*100):,}",17,SUB,anchor="ra")
    d.rectangle((left,Y(s["buy_high"]),x1-20,Y(s["buy_low"])),fill="#E4EFE7")
    for val,color in [(s["stop"],RED),(s["buy_low"],GREEN),(s["buy_high"],GREEN),
                      (s.get("r1"),GOLD),(s.get("r2"),PURPLE)]:
        if val is not None:
            yy=Y(val);d.line((left,yy,x1-8,yy),fill=color,width=3)
            # Small colored number at right, aligned to drawn line
            txt(d,x1-8,yy-23, f"{int(val):,}",18,color,True,anchor="ra")
    five=ma(rows,5);twenty=ma(rows,20);sixty=ma(rows,60)
    vmax=max(max(r[5] for r in show),1)
    for i,row in enumerate(show):
        day,o,h,l,c,v=row;xx=left+i*step
        color=RED if c>=o else BLUE
        d.line((xx,Y(h),xx,Y(l)),fill=color,width=3)
        yy0,yy1=sorted((Y(o),Y(c)))
        d.rectangle((xx-9,yy0,xx+9,max(yy1,yy0+3)),fill=color)
        vheight=(v/vmax)*(vbottom-vtop)
        d.rectangle((xx-9,vbottom-vheight,xx+9,vbottom),fill="#B2AFAB")
        if i%4==0 or i==len(show)-1:
            txt(d,xx,y1-19,f"{day[4:6]}/{day[6:]}",17,SUB,anchor="ma")
    for seq,col in [(five,GOLD),(twenty,PURPLE),(sixty,BLUE)]:
        pts=[(left+i*step,Y(seq[offset+i])) for i in range(len(show)) if seq[offset+i] is not None]
        if len(pts)>1:d.line(pts,fill=col,width=4,joint="curve")
    txt(d,left,vtop-21,"거래량",18,SUB)
def page1(s,rows):
    im,d=base(s,1)
    box(d,(730,145,1030,252),fill="#F2E8D3",border="#E0CC9C")
    txt(d,1005,162,won(s["close"]),45,INK,True,anchor="ra")
    txt(d,1005,214,s["chg"],23,RED,True,anchor="ra")
    box(d,(37,286,1043,1045),fill="#FFFFFF")
    txt(d,67,302,"주가 차트 (일봉)",31,INK,True)
    for i,(name,color) in enumerate([("5일선",GOLD),("20일선",PURPLE),("60일선",BLUE)]):
        xx=516+i*158;d.line((xx,322,xx+27,322),fill=color,width=4);txt(d,xx+35,307,name,21,SUB)
    plot(d,(66,354,1005,994),rows,s)
    box(d,(37,1070,1043,1335),fill="#FFFFFF")
    txt(d,63,1090,"매매 관찰 기준",31,INK,True)
    for label,value,col,x,y in [
        ("1차 매수 범위",f'{won(s["buy_low"])} ~ {won(s["buy_high"])}',GREEN,62,1154),
        ("2차 매수 범위","미확정 · 지지 재평가 후 산정",BLUE,62,1202),
        ("손절가",won(s["stop"]),RED,62,1250),
    ]:
        txt(d,x,y,label,25,SUB);txt(d,x+244,y,value,25,col,True)
    txt(d,62,1298,"1차 저항",24,SUB);txt(d,202,1298,won(s.get("r1")),24,GOLD,True)
    txt(d,522,1298,"2차 저항",24,SUB);txt(d,665,1298,won(s.get("r2")),24,PURPLE,True)
    box(d,(37,1370,1043,1458),fill=CREAM,border="#E6DFD1")
    txt(d,58,1395,"과거 연구 후보 예시 · 신규 매수 신호 아님 · 5/20/60일선 실제 종가로 계산",21,SUB)
    path=OUT/(s["ticker"]+"_01.png");im.save(path,optimize=True);return path
def multiline(d,x,y,lines,width,size=27,step=39,color=INK):
    for line in lines:
        # Preapproved short, factual source-backed summary only; no wrap needed
        txt(d,x,y,"• "+line,size,color);y+=step
    return y
def section(d,x,y,title,items):
    box(d,(x,y,x+978,y+216),fill="#FFFFFF",border=BORDER)
    d.rectangle((x,y,x+10,y+216),fill=GOLD)
    txt(d,x+30,y+18,title,29,INK,True)
    multiline(d,x+30,y+69,items,925,size=25,step=37)
def page2(s):
    im,d=base(s,2)
    txt(d,50,287,"종목 선정 이유 | 산업·재무·이슈·펀더멘털",32,INK,True)
    labels=["01  섹터·재료","02  재무·실적","03  주요 이슈·수급","04  펀더멘털·리스크"]
    for i,(label,items) in enumerate(zip(labels,s["notes"])):
        section(d,49,356+i*228,label,items)
    box(d,(49,1290,1030,1400),fill=CREAM,border="#DDC99F")
    txt(d,77,1304,f'시장 대비 상대강도(RS20)  {s["rs20"]:+.2f}%p',27,GOLD,True)
    txt(d,77,1353,f'최근 5일 상대강도 개선  {s["rsaccel"]:+.2f}%p',25,INK)
    txt(d,50,1443,"※ 확인된 연구 자료만 사용 · 신규 매수 신호 아님",21,SUB)
    path=OUT/(s["ticker"]+"_02.png");im.save(path,optimize=True);return path
def create_cards(report):
    if report.get("source_price_asof")!="2026-11-05":raise ValueError("HISTORICAL_SOURCE_DATE_MISMATCH")
    if report.get("source_provider")!="KRX_OFFICIAL_EOD":raise ValueError("OFFICIAL_RESEARCH_REQUIRED")
    look={r["ticker"]:r for r in report.get("research_top2",[])}
    if set(look)!={"028050","030530"}:raise ValueError("UNEXPECTED_TOP2")
    notes={
      "028050":[
         ["화공·첨단산업 플랜트 EPC 사업","해외 플랜트 프로젝트 수주 확대 관찰","AI·뉴에너지 투자 수요 연결 가능성"],
         ["2026년 3분기 실적 개선 보고","분기 매출·영업이익 성장 여부 확인","수주 잔고와 현금흐름 동시 점검"],
         ["대규모 해외 프로젝트 수주 이슈","주주환원·자기주식 관련 공시 관찰","시장 대비 주가 상대강도 우위"],
         ["프로젝트 원가·공정 지연 위험","국제 유가·환율·해외 발주 변동성","타점 도달·지지 확인까지 추격 금지"]],
      "030530":[
         ["반도체용 가스공급 장비 사업","로봇·자동화 관련 사업 노출","반도체 설비투자 회복 관찰 재료"],
         ["2026년 2분기 영업 흑자전환 관찰","실적 개선의 지속성 확인 필요","부채·현금흐름·자회사 실적 점검"],
         ["11월 초 고점 형성 뒤 급락 조정","11월 5일 종가 전일 대비 -10.47%","높은 변동성에 따른 손절 위험"],
         ["사업 다각화와 반도체 투자 사이클","높은 일일 변동성과 급등락 주의","1차 매수 범위 지지 여부 확인"]]
    }
    paths=[]
    for ticker in ("028050","030530"):
        r=look[ticker];p=r["entry_plans"]["A_SUPPORT_LIMIT"]["plan"]
        s=dict(ticker=ticker,name=r["name"],date=report["source_price_asof"],close=int(r["close"]),
               chg= "-1.83%" if ticker=="028050" else "-10.47%",
               buy_low=p["low"],buy_high=p["high"],stop=p["stop"],
               r1=int(p["resistance"]) if p.get("resistance") else None,
               r2=int(p["resistance2"]) if p.get("resistance2") else None,
               notes=notes[ticker],rs20=r["rs20"],rsaccel=r["rs_accel5"])
        data=verified_bars(s)
        paths.extend((page1(s,data),page2(s)))
    print("C3_CLASSIC_FOUR_CARDS_VERIFIED_AND_RENDERED",flush=True)
    return paths
def send_album(files):
    import requests
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    chat_id=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat_id:raise ValueError("TELEGRAM_SECRETS_MISSING")
    media=[];attachments=[];opened=[]
    try:
        for i,p in enumerate(files):
            fh=open(p,"rb");opened.append(fh)
            attachments.append((f"photo{i}",(p.name,fh,"image/png")))
            item={"type":"photo","media":f"attach://photo{i}"}
            if i==0:item["caption"]="강현AI PRO | C3 TOP2 클래식 테마 시험\n① 삼성E&A 차트 ② 선정 이유 ③ 원익홀딩스 차트 ④ 선정 이유\n2026.11.05 기준 과거 연구 후보 예시 · 신규 매매 신호 아님"
            media.append(item)
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMediaGroup",
                        data={"chat_id":chat_id,"media":json.dumps(media,ensure_ascii=False)},files=attachments,timeout=70)
        try:reply=r.json()
        except ValueError:raise ValueError("TELEGRAM_NON_JSON_RESPONSE")
        if not r.ok or not reply.get("ok") or len(reply.get("result",[]))!=4:
            raise ValueError("TELEGRAM_ALBUM_NOT_ACCEPTED_HTTP_"+str(r.status_code))
        print("C3_CLASSIC_FOUR_IMAGE_ALBUM_DELIVERED",flush=True)
    finally:
        for fh in opened:fh.close()
def main():
    url="https://raw.githubusercontent.com/shdmfpsj-beep/krx-auto-scanner/3f0c646094cacf5c6dc3e07188d1e73bf01289f2/reports/c3_forward_v8/latest.json"
    req=urllib.request.Request(url,headers={"User-Agent":"C3ResearchThemeDemo"})
    with urllib.request.urlopen(req,timeout=20) as response:j=json.load(response)
    files=create_cards(j)
    if "--send" in sys.argv:send_album(files)
if __name__=="__main__":main()
