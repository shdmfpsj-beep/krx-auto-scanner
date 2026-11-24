"""Separate observation-only delivery; never writes TOP5 receipts."""
import base64, hashlib, json, os, re, urllib.request, uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from c3_all_candidate_report import image_identity
from c3_top5_financial_selection import valid_entry

def choose(report, selection, blocked):
    if selection.get('operational_status') not in ('TOP5_READY','CASH_NO_ELIGIBLE'):
        return []
    if report['asof'] != selection['asof']:
        raise ValueError('WATCH_DATE_MISMATCH')
    rows=report['candidates']
    if len({r['code'] for r in rows}) != len(rows):
        raise ValueError('WATCH_DUPLICATE_CODE')
    selected={r['code'] for r in selection['selected']}
    result=[]
    for r in rows:
        if r['code'] in selected or r['code'] in blocked or r.get('top5') or r.get('status')!='WATCH':
            continue
        if r.get('financial_verdict')!='PASS' or selection['financial_verdicts'].get(r['code'])!='PASS':
            continue
        if not valid_entry({**r,'close':r.get('asof_close')},allow_watch=True):
            continue
        distance=(r['asof_close']-r['entry_high'])/r['asof_close']*100
        if 2 < distance <= 5:
            result.append({**r,'distance_pct':distance})
    return sorted(result,key=lambda r:(-r['composite_score'],r['distance_pct'],r['code']))[:5]

def main():
    root=Path('output/c3_top5')
    out=root/'watch5';out.mkdir(exist_ok=True)
    result={'status':'ERROR','photos':[],'selected':[]}
    def save():
        (root/'watch_delivery_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    save()
    def read(p):return json.loads((root/p).read_text())
    outcome=read('execution_outcome.json')
    if outcome['operational_status'] not in ('TOP5_READY','CASH_NO_ELIGIBLE'):
        result['status']='BLOCKED';save();return
    if os.environ.get('C3_FINANCIAL_MODEL')!='balanced':
        result['status']='NOT_APPLICABLE';save();return
    report=read('all_candidate_report/manifest.json')
    selection=read('financial_selection_research.json')
    receipt=read('receipt.json')
    if not outcome['asof']==report['asof']==selection['asof']==receipt['asof']:
        raise ValueError('WATCH_DATE_MISMATCH')
    date=report['asof']
    if not re.fullmatch(r'\d{8}',date):raise ValueError('WATCH_DATE_FORMAT')
    result['asof']=date
    rows=choose(report,selection,set(read('duplicate_signal_audit.json')['blocked_codes']))
    for r in rows:
        if not re.fullmatch(r'\d{6}',r['code']) or Path(r['image']).name!=r['image']:
            raise ValueError('WATCH_PATH')
        if r['entry_valid_until']!=receipt['entry_valid_until'] or not r['entry_valid_until']:
            raise ValueError('WATCH_VALIDITY')
        p=root/'all_candidate_report'/r['image']
        if hashlib.sha256(p.read_bytes()).hexdigest()!=r['image_sha256']:
            raise ValueError('WATCH_HASH')
        with Image.open(p) as im:
            if im.format!='PNG' or im.size!=(1400,1710) or json.loads(im.info['c3_candidate'])!=image_identity(r,date):
                raise ValueError('WATCH_IMAGE_IDENTITY')
            canvas=Image.new('RGB',(1400,1810),'#28577d')
            canvas.paste(im.convert('RGB'),(0,100))
        font=ImageFont.truetype('/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf',36)
        ImageDraw.Draw(canvas).text((700,50),'WATCH5 관찰용 — 매수 승인 아님',font=font,fill='white',anchor='mm')
        dest=out/(r['code']+'_watch.png');canvas.save(dest)
        result['selected'].append({'code':r['code'],'image':dest.name,'image_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'distance_pct':r['distance_pct']})
    if not rows:result['status']='EMPTY';save();return
    if not (os.environ.get('GITHUB_EVENT_NAME')=='schedule' and os.environ.get('GITHUB_REF_NAME')=='main'):
        result['status']='DRY_RUN';save();return
    token,chat=os.environ['TELEGRAM_BOT_TOKEN'],os.environ['TELEGRAM_CHAT_ID']
    if not token or not chat:raise ValueError('WATCH_CREDENTIALS')
    marker={'asof':date,'status':'RESERVED_BEFORE_SEND','run_id':os.environ['GITHUB_RUN_ID'],'selected':result['selected']}
    payload=json.dumps({'message':'Reserve WATCH5 observation '+date,'branch':'main','content':base64.b64encode(json.dumps(marker).encode()).decode()}).encode()
    req=urllib.request.Request('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/contents/receipts/c3_watch5_daily/'+date+'.json',data=payload,method='PUT',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        if response.status!=201:raise ValueError('WATCH_RESERVATION')
    for item in result['selected']:
        boundary='----C3'+uuid.uuid4().hex
        def part(name,value,extra=''):
            return ('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'+extra+'\r\n\r\n').encode()+value+b'\r\n'
        body=part('chat_id',chat.encode())+part('photo',(out/item['image']).read_bytes(),'; filename="'+item['image']+'"\r\nContent-Type: image/png')+('--'+boundary+'--\r\n').encode()
        req=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendPhoto',data=body,method='POST',headers={'Content-Type':'multipart/form-data; boundary='+boundary})
        with urllib.request.urlopen(req,timeout=30) as response:answer=json.load(response)
        msg=answer.get('result',{}).get('message_id')
        if not answer.get('ok') or type(msg)!=int or msg<=0 or str(answer['result']['chat']['id'])!=chat:
            raise ValueError('WATCH_TELEGRAM_RESPONSE')
        result['photos'].append({**item,'telegram_message_id':msg});save()
    result['status']='SENT';save()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('WATCH_DELIVERY_FAILED',type(e).__name__)
        raise SystemExit(1)
