#!/usr/bin/env python3
"""Complete C3 candidate ranking and one PNG per detected candidate; non-trading report."""
import argparse,json,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pool',required=True);p.add_argument('--selection',required=True);p.add_argument('--out',required=True)
    a=p.parse_args()
    src=json.loads(Path(a.pool).read_text())
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    try: fin=json.loads(Path(a.selection).read_text())
    except (OSError,ValueError): fin={}
    finance={str(x.get('code')):x for x in fin.get('selected',[])}
    # Existing opportunity score is technical-only. Do not mislabel as financial composite.
    candidates=src.get('candidates',[])[:10]
    candidates=sorted(candidates,key=lambda x:(-float(x.get('opportunity_score',0)),-float(x.get('score',0)),x['code']))
    regular='/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    bold='/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'
    def font(n,b=False):return ImageFont.truetype(bold if b else regular,n)
    rows=[]
    for rank,x in enumerate(candidates,1):
        valid=bool(x.get('geometry_validated'))
        state=x.get('entry_status','WATCH') if valid else 'WATCH'
        is_fin=x['code'] in finance
        score=round(float(x.get('opportunity_score',x.get('score',0))),2)
        bars=x['bars'];prices=[float(b['close']) for b in bars]
        im=Image.new('RGB',(1400,1710),(249,248,244));d=ImageDraw.Draw(im)
        ink=(39,43,49);muted=(97,104,110);gold=(162,121,54)
        d.rectangle((0,0,1400,110),fill=ink)
        d.text((45,25),'강현AI PRO | 전체 후보 순위',font=font(42,True),fill='white')
        d.text((1325,36),src['asof'],font=font(28),fill='white',anchor='ra')
        d.text((55,145),x['name'],font=font(62,True),fill=ink)
        d.text((55,242),f"전체 {rank}위 / {len(candidates)}종목  |  기술점수 {score:.2f}",font=font(37,True),fill=gold)
        d.text((55,315),f"{x['code']}  |  {state}  |  "+('재무선정' if is_fin else '재무 미선정/미검증'),font=font(31),fill=ink)
        d.text((55,395),f"종가 {prices[-1]:,.0f}원",font=font(43,True),fill=ink)
        d.text((55,477),"매수범위 / 구조손절 / 목표가",font=font(31,True),fill=ink)
        if valid and all(x.get(k) is not None for k in ('entry_low','entry_high','stop_ref','r1_ref')):
            levels=f"{x['entry_low']:,.0f} ~ {x['entry_high']:,.0f}원  /  {x['stop_ref']:,.0f}원"
            target=f"R1 {x['r1_ref']:,.0f}원  /  R2 "+(f"{x['r2_ref']:,.0f}원" if x.get('r2_ref') else '미확정')
        else:
            levels="진입 구조 미확정 · 관찰 전용 (매수 금지)"
            target="R1 / R2 미확정"
        d.text((55,535),levels,font=font(30),fill=ink)
        d.text((55,595),target,font=font(29),fill=muted)
        left,top,right,bottom=90,715,1320,1275
        d.rectangle((left,top,right,bottom),outline=(203,204,204),width=2)
        lo=min(prices)*.98;hi=max(prices)*1.02
        if hi<=lo:hi=lo+1
        xy=[(left+i*(right-left)/max(1,len(prices)-1),bottom-(v-lo)/(hi-lo)*(bottom-top)) for i,v in enumerate(prices)]
        d.line(xy,fill=(50,109,166),width=5,joint='curve')
        for window,color in ((5,(187,91,66)),(20,(42,137,91)),(60,(137,96,172))):
            ma=[sum(prices[max(0,i-window+1):i+1])/min(window,i+1) for i in range(len(prices))]
            pts=[(left+i*(right-left)/max(1,len(prices)-1),bottom-(v-lo)/(hi-lo)*(bottom-top)) for i,v in enumerate(ma)]
            d.line(pts,fill=color,width=3)
        d.text((65,1325),"종가(파랑) / MA5(빨강) / MA20(초록) / MA60(보라)",font=font(25),fill=muted)
        d.text((65,1390),"거래량",font=font(29,True),fill=ink)
        volumes=[float(b['volume']) for b in bars];vmax=max(volumes) or 1
        for i,v in enumerate(volumes):
            px=left+i*(right-left)/len(volumes)
            d.rectangle((px,1580-v/vmax*140,px+max(2,(right-left)/len(volumes)-2),1580),fill=(140,151,161))
        d.text((65,1630),"WATCH·NEAR는 매수 신호 아님 | 조건 충족 전 PASS | 주문은 사용자 직접",font=font(23),fill=muted)
        name=f"{rank:02d}_{x['code']}_all_candidate.png"
        im.save(out/name,optimize=True)
        rows.append({'rank':rank,'code':x['code'],'name':x['name'],'technical_score':score,
          'score_type':'TECHNICAL_OPPORTUNITY_ONLY','status':state,'financial_selected':is_fin,
          'top5':rank<=5,'geometry_validated':valid,'image':name,
          'entry_low':x.get('entry_low') if valid else None,'entry_high':x.get('entry_high') if valid else None,
          'stop_ref':x.get('stop_ref') if valid else None})
    result={'schema':'C3_ALL_CANDIDATES_V1','asof':src['asof'],'candidate_count':len(rows),
      'score_disclaimer':'Technical opportunity ranking, not verified financial composite',
      'candidates':rows,'trade_approved':False}
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C3_ALL_CANDIDATES',json.dumps({'asof':src['asof'],'count':len(rows),
      'images':len(rows),'top5':[x['code'] for x in rows[:5]]},ensure_ascii=False))
if __name__=='__main__':main()
