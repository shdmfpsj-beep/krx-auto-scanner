"""Execute actual production selection/render/delivery code on verified archives.

No KRX/DART requests, credentials, operating reservations, or photo sends.
Historical export copies keep original expiry and add a conspicuous warning.
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo
from c3_top5_financial_selection import INDEPENDENT_POLICY, select, attach_support_evidence
from c3_balanced_validation import embedded
from c3_candidate_decisions import report as candidate_report, save as save_candidates
from c3_all_candidate_report import image_identity

REPO=Path(__file__).resolve().parents[1]


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def replay(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if source==out or source in out.parents or out in source.parents or out.exists():raise ValueError('OUTPUT_MUST_BE_NEW_SEPARATE_DIRECTORY')
    original={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    for path in (source/'krx_source').glob('*.meta.json'):
        item=json.loads(path.read_text())
        if Path(item['file']).name!=item['file'] or hashlib.sha256((path.parent/item['file']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('ARCHIVE_KRX_HASH_INVALID')
    work=out/'work';root=work/'output/c3_top5';shutil.copytree(source,root)
    def read(name):return json.loads((root/name).read_text())
    receipt=read('receipt.json');geometry=read('entry_geometry_audit.json');pool=read('qualified_chart_pool.json');financial=read('financial_pool_gate.json')
    if any(x['asof']!=receipt['asof'] for x in (geometry,pool,financial)):raise ValueError('ARCHIVE_DATE_MISMATCH')
    integrity=receipt['source_integrity']
    if integrity['session_count']!=60 or integrity['last_session']!=receipt['asof']:raise ValueError('ARCHIVE_PRICE_SOURCE_INCOMPLETE')
    financial['aggregate_policy']=INDEPENDENT_POLICY
    selection=select(attach_support_evidence(geometry,pool),financial)
    write(root/'financial_pool_gate.json',financial);write(root/'financial_selection_research.json',selection)
    save_candidates(root,candidate_report(receipt,geometry,selection,financial))
    env={k:os.environ[k] for k in ('PATH','C3_FONT_DIR') if k in os.environ}
    env.update(PYTHONPATH=str(REPO/'scripts'),GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_NAME='independent-archive-validation',
        GITHUB_REPOSITORY='shdmfpsj-beep/krx-auto-scanner',GITHUB_RUN_ID=os.environ.get('GITHUB_RUN_ID','archive-validation'),
        C3_FINANCIAL_MODEL='balanced',C3_APPROVAL_POLICY=INDEPENDENT_POLICY,C3_MANUAL_LIVE_DELIVERY='false')
    args=[sys.executable,str(REPO/'scripts/c3_all_candidate_report.py'),'--pool',str(root/'qualified_chart_pool.json'),
        '--selection',str(root/'financial_selection_research.json'),'--financial',str(root/'financial_pool_gate.json'),
        '--out',str(root/'all_candidate_report')]
    rendered=subprocess.run(args,env=env,capture_output=True,text=True)
    if rendered.returncode:raise ValueError('ARCHIVE_RENDER_FAILED_'+rendered.stderr[-100:])
    report=read('all_candidate_report/manifest.json');selected=[r for r in report['candidates'] if r['top5']]
    preview=root/'financial_preview';preview.mkdir(exist_ok=True);images=[]
    for row in selected:
        shutil.copy2(root/'all_candidate_report'/row['image'],preview/row['image'])
        images.append(dict(code=row['code'],image=row['image']))
    write(preview/'financial_preview_manifest.json',dict(asof=receipt['asof'],images=images))
    guard="import urllib.request\ndef forbidden(*a,**k):raise AssertionError('ARCHIVE_NETWORK_FORBIDDEN')\nurllib.request.urlopen=forbidden\n"
    commands=[('manifest',embedded('Build finance-first conditional signal delivery manifest')),
        ('top5',embedded('Validate delivery on every run; send only on scheduled main')),
        ('outcome',embedded('Publish operational outcome without sending'))]
    commands += [(family,"import runpy,sys\nsys.argv=['runner']\nrunpy.run_path("+repr(str(REPO/'scripts'/script))+",run_name='__main__')") for family,script in
        [('watch','c3_watch5_delivery.py'),('review','c3_review_delivery.py')]]
    commands.append(('final',"from c3_delivery_outcome import finalize\nassert finalize('output/c3_top5')['program_status']=='COMPLETED'"))
    for family,code in commands:
        process=subprocess.run([sys.executable,'-c',guard+code],cwd=work,env=env,capture_output=True,text=True)
        (out/(family+'.log')).write_text(process.stdout+process.stderr)
        if process.returncode:raise ValueError('ARCHIVE_BOUNDARY_FAILED_'+family)
    watch,review=read('watch_delivery_result.json'),read('review_delivery_result.json');outcome=read('execution_outcome.json')
    for row in report['candidates']:
        path=root/'all_candidate_report'/row['image']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError('ARCHIVE_IMAGE_HASH')
        with Image.open(path) as image:
            if json.loads(image.info['c3_candidate'])!=image_identity(row,receipt['asof']):raise ValueError('ARCHIVE_IMAGE_METADATA')
    fields=['code','name','status','asof_close','entry_low','entry_high','stop_ref','risk_pct','r1_ref','r2_ref','entry_valid_until']
    with (root/'top5.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(selected)
    with (root/'top5.csv').open(encoding='utf-8-sig') as stream:csv_rows=list(csv.DictReader(stream))
    for row,saved in zip(selected,csv_rows):
        if any(saved[k]!=(str(row[k]) if row.get(k) is not None else '') for k in fields):raise ValueError('ARCHIVE_CSV_JSON_MISMATCH')
    exports=[];directory=out/'historical_reference';directory.mkdir()
    for kind,rows,folder in [('TOP5',selected,'all_candidate_report'),('WATCH5',watch['selected'],'watch5'),('REVIEW_REQUIRED',review['selected'],'review_unverified')]:
        for row in rows:
            path=root/folder/row['image'];binary=path.read_bytes()
            with Image.open(path) as image:
                canvas=Image.new('RGB',(image.width,image.height+90),'#40454c');canvas.paste(image.convert('RGB'),(0,90))
            draw=ImageDraw.Draw(canvas);font=ImageFont.truetype(str(Path(env.get('C3_FONT_DIR','/usr/share/fonts/truetype/nanum'))/'NanumGothicBold.ttf'),28)
            draw.text((700,42),'과거 분석 참고용 · '+receipt['asof']+' · 유효기간 만료 · 실발송 금지',font=font,fill='white',anchor='mm')
            identity=dict(kind=kind,asof=receipt['asof'],code=row['code'],entry_valid_until=receipt['entry_valid_until'],
                validity_extended=False,trade_approved=False,source_image_sha256=hashlib.sha256(binary).hexdigest())
            info=PngInfo();info.add_text('c3_historical_reference',json.dumps(identity,ensure_ascii=False))
            dest=directory/(row['code']+'_'+kind+'.png');canvas.save(dest,pnginfo=info)
            exports.append(dict(**identity,image=dest.name,image_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    if any(hashlib.sha256((source/name).read_bytes()).hexdigest()!=sha for name,sha in original.items()):raise ValueError('ARCHIVE_SOURCE_MUTATED')
    summary=dict(asof=receipt['asof'],source_mode='ACTUAL_ARCHIVE_PRODUCTION_CODE_REPLAY_NO_NEW_API',aggregate_policy=INDEPENDENT_POLICY,
        operational_status=outcome['operational_status'],approval_financial_complete=selection.get('approval_financial_complete'),
        selected_financial_complete=selection.get('selected_financial_complete'),selection_approval_complete=selection.get('selection_approval_complete'),
        all_interest_financial_complete=selection.get('all_interest_financial_complete'),
        top5=[r['code'] for r in selected],watch5=[r['code'] for r in watch['selected']],reference=[r['code'] for r in review['selected']],
        delivery_channels=outcome['delivery_channels'],actual_telegram_sent=outcome['total_telegram_photos_sent'],operating_receipts_created=False,
        original_sources_preserved=True,csv_json_png_consistent=True,historical_images=exports)
    write(out/'release_validation.json',summary);write(directory/'manifest.json',summary)
    print('C3_INDEPENDENT_RELEASE_VALIDATION',json.dumps(summary,ensure_ascii=False))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();replay(args.source,args.out)
