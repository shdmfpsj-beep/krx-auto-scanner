#!/usr/bin/env python3
"""Render finance-qualified TOP5 conditional-signal images; never sends Telegram."""
import argparse,json,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def render(pool,selection,out):
    if pool.get("asof")!=selection.get("asof"):
        raise ValueError("ASOF_MISMATCH")
    candidates=pool.get("candidates",[])
    lookup={c["code"]:c for c in candidates}
    if len(lookup)!=len(candidates):
        raise ValueError("DUPLICATE_POOL_CODE")
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    for rank,item in enumerate(selection.get("selected",[])[:5],1):
        c=lookup.get(item["code"])
        if not c or c.get("entry_status")!=item.get("technical_status"):
            raise ValueError("SELECTED_NOT_IN_POOL")
        bars=c.get("bars",[])
        if len(bars)<60 or not all(b.get("close",0)>0 for b in bars):
            raise ValueError("INSUFFICIENT_BARS")
        lo,hi,stop=c.get("entry_low"),c.get("entry_high"),c.get("stop_ref")
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (lo,hi,stop)):
            raise ValueError("INVALID_ENTRY_GEOMETRY")
        if not (0<stop<lo<=hi and 0<(hi-stop)/hi<=.05):
            raise ValueError("INVALID_RISK")
        im=Image.new("RGB",(1400,1710),(249,248,245))
        d=ImageDraw.Draw(im)
        fontpath="/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        def font(n):
            try:return ImageFont.truetype(fontpath,n)
            except OSError:return ImageFont.load_default()
        d.rectangle((0,0,1400,115),fill=(40,46,55))
        d.text((50,27),"C3 TOP5 | FINANCE-FIRST SIGNAL PREVIEW",font=font(36),fill="white")
        d.text((50,160),str(c.get("name",""))+"  "+c["code"],font=font(45),fill=(38,42,46))
        d.text((50,235),"As-of "+str(pool["asof"])+" | "+c["entry_status"],font=font(30),fill=(80,90,95))
        d.text((50,295),"BUY_CONSIDER=entry ready | NEAR_ENTRY=wait | User trades",font=font(25),fill=(150,70,60))
        closes=[b["close"] for b in bars[-60:]]
        prior_close=bars[-61]["close"] if len(bars)>=61 else None
        targets=[(key,c.get(key)) for key in ("r1_ref","r2_ref") if isinstance(c.get(key),(int,float)) and math.isfinite(c.get(key)) and c.get(key)>hi]
        values=closes+[lo,hi,stop]+[v for _,v in targets]
        low=min(values)*.95;high=max(values)*1.05
        left,right,top,bottom=135,1270,430,1120
        px=lambda i:int(left+(right-left)*i/59)
        py=lambda v:int(bottom-(v-low)/(high-low)*(bottom-top))
        for j in range(5):
            y=top+(bottom-top)*j//4
            d.line((left,y,right,y),fill=(215,215,215),width=2)
        for i in range(1,60):
            d.line((px(i-1),py(closes[i-1]),px(i),py(closes[i])),fill=(46,112,167),width=4)
        for n,color in ((5,(53,125,88)),(20,(187,130,52)),(60,(121,93,157))):
            if n==60 and prior_close is None:
                d.ellipse((px(59)-5,py(sum(closes)/60)-5,px(59)+5,py(sum(closes)/60)+5),fill=color)
                continue
            for i in range(n-1,60):
                if i==n-1: continue
                a=sum(closes[i-n:i])/n
                b=sum(closes[i-n+1:i+1])/n
                d.line((px(i-1),py(a),px(i),py(b)),fill=color,width=3)
        for key,val in targets:
            y=py(val)
            d.line((left,y,right,y),fill=(115,85,155),width=2)
            d.text((left+15,y-35),f"{key.upper()} {val:,.0f}",font=font(25),fill=(115,85,155))
        for val,color in ((lo,(45,133,85)),(hi,(45,133,85)),(stop,(177,63,63))):
            y=py(val);d.line((left,y,right,y),fill=color,width=3)
            d.text((right-180,y-39),f"{val:,.0f}",font=font(25),fill=color)
        d.text((60,1180),f"Entry  {lo:,.0f} - {hi:,.0f} KRW",font=font(43),fill=(35,102,72))
        d.text((60,1250),f"Structural stop  {stop:,.0f} KRW",font=font(43),fill=(175,65,65))
        d.text((60,1320),f"Max entry risk  {(hi-stop)/hi*100:.2f}%",font=font(37),fill=(45,48,55))
        volumes=[max(0,float(b.get("volume") or b.get("trading_volume") or 0)) for b in bars[-60:]]
        vmax=max(volumes) if volumes else 0
        d.text((60,1395),"Volume (60 sessions)",font=font(26),fill=(75,85,95))
        for i,v in enumerate(volumes):
            height=int(100*v/vmax) if vmax else 0
            x=px(i)
            d.rectangle((x-5,1530-height,x+5,1530),fill=(110,135,155))
        d.text((60,1570),"Conditional signal / Independent certification not required",font=font(25),fill=(105,95,85))
        d.text((60,1620),"Entry not reached: PASS. No automated orders.",font=font(26),fill=(105,95,85))
        name=f"financial_preview_{rank:02d}_{c['code']}.png"
        im.save(out/name)
        results.append({"code":c["code"],"image":name})
    return results

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pool",type=Path,required=True)
    p.add_argument("--selection",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    pool=json.loads(a.pool.read_text())
    selection=json.loads(a.selection.read_text())
    results=render(pool,selection,a.out)
    (a.out/"financial_preview_manifest.json").write_text(json.dumps({
        "asof":pool["asof"],"status":"CONDITIONAL_SIGNAL_PREVIEW_NO_SEND",
        "images":results},ensure_ascii=False,indent=2)+"\n")
    print("FINANCIAL_PREVIEW_RENDERED",len(results),"NO_TELEGRAM")
if __name__=="__main__":main()
