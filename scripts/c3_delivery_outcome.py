"""Account for actual outcomes of TOP5, WATCH5 and unverified references."""
import argparse
import json
import os
from pathlib import Path


def finalize(root):
    root=Path(root)
    def read(name):return json.loads((root/name).read_text())
    try:
        result=read('execution_outcome.json');selection=read('financial_selection_research.json')
        state=selection['operational_status'];channels={};failed=[]
        for family,file in [('top5','delivery_result.json'),('watch5','watch_delivery_result.json'),('review','review_delivery_result.json')]:
            data=read(file);photos=data.get('photos',[])
            count=selection['selected_count'] if family=='top5' else len(data.get('selected',[]))
            channels[family]=dict(status=data['status'],selected_count=count,telegram_photos_sent=len(photos),
                message_ids=[p.get('telegram_message_id') for p in photos],
                images=[{k:p.get(k) for k in ('code','image','image_sha256','destination_matches')} for p in photos],
                reservation_path=data.get('reservation_path'),sent_receipt_path=data.get('sent_receipt_path'),reason=data.get('reason'))
            if data.get('telegram_photos_sent',0)!=len(photos):failed.append(family+'_COUNT_MISMATCH')
            if state in ('TOP5_READY','CASH_NO_ELIGIBLE'):
                allowed=('SENT','DRY_RUN') if family=='top5' and state=='TOP5_READY' else ('CASH',) if family=='top5' else ('SENT','DRY_RUN','EMPTY','NOT_APPLICABLE')
                if data['status'] not in allowed:failed.append(family+'_DELIVERY_'+data['status'])
                if data['status']=='SENT' and (count!=len(photos) or not photos or any(
                    type(p.get('telegram_message_id')) is not int or p['telegram_message_id']<=0 or p.get('destination_matches') is not True for p in photos)):
                    failed.append(family+'_SENT_EVIDENCE_INVALID')
            elif photos:failed.append(family+'_SENT_DURING_HOLD_OR_ERROR')
        result.update(selection_operational_status=state,delivery_channels=channels,
            total_telegram_photos_sent=sum(r['telegram_photos_sent'] for r in channels.values()),
            delivery_reconciliation_errors=failed)
        if failed:result.update(operational_status='ERROR',program_status='ERROR')
    except (OSError,KeyError,ValueError,TypeError) as error:
        result=dict(operational_status='ERROR',program_status='ERROR',error='DELIVERY_RECONCILIATION_'+type(error).__name__)
    root.mkdir(parents=True,exist_ok=True)
    (root/'execution_outcome.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C3_FINAL_DELIVERY_OUTCOME',json.dumps(result,ensure_ascii=False))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:
            stream.write('\n### C3 final delivery outcome\n\n'+json.dumps(result,ensure_ascii=False)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    r=finalize(p.parse_args().root);raise SystemExit(1 if r['operational_status']=='ERROR' else 0)
