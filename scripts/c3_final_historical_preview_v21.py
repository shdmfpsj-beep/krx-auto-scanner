"""Historical, strictly no-delivery 2026-11-10 C3 source replay.

Only official read paths; no Git writes, Telegram API calls, receipt changes
or retroactive B-model signals. Used in PR CI with pinned immutable reader.
"""
import hashlib,json,os,sys
from pathlib import Path

from c3_telegram_inputs import GitHub,canonical,report_pair,frozen_live_bars
from c3_final_delivery_gate_v1 import review,filtered_report_for_presentation
from c3_classic_theme import create_final_cards
from c3_telegram_notify import validate_photos

ASOF='2026-11-10'


def execute(outdir='/tmp/c3-v21-historical-preview'):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    status={'schema':'C3_V21_HISTORICAL_READ_ONLY_REPLAY','asof':ASOF,
            'actual_telegram_send_attempts':0,'orders_enabled':False,
            'operating_main_modified':False,'registered_new_signals':0,
            'status':'BLOCKED','reason':None}
    try:
        gh=GitHub(os.environ.get('GH_TOKEN',''))
        report,summary,ref=report_pair(gh)
        if (report.get('source_price_asof')!=ASOF or
            summary.get('source_price_asof')!=ASOF or
            summary.get('source_run_id')!=report.get('source_run_id') or
            summary.get('generated_at')!=report.get('generated_at')):
            raise ValueError('HISTORICAL_SOURCE_REPORT_NOT_SAME_SESSION')
        original_sha=hashlib.sha256(canonical(report)).hexdigest()
        sealed=frozen_live_bars(gh,report,ref)
        audited=review(sealed,sealed.get('presentation_ranked_pool'),
                       sealed.get('presentation_pool_proof'))
        original=audited.get('reviewed',[])[:2]
        if ([r.get('ticker') for r in original]!=['028050','180640'] or
            [r.get('technical_status') for r in original]!=['RISK_REJECTED','STALE_ENTRY'] or
            audited['eligible_count']!=0):
            raise ValueError('NOV10_FIXED_TOP2_DIAGNOSIS_CHANGED')
        output=filtered_report_for_presentation(sealed,audited,sealed.get('presentation_ranked_pool'))
        output['historical_test_only']=True
        paths=create_final_cards(output,root)
        hashes=validate_photos(paths,allow_single=True)
        status.update(status='PASS_HISTORICAL_CASH_REPLAY_NO_DELIVERY',
            reason=None,source_run_id=report['source_run_id'],
            original_public_report_sha256=original_sha,
            immutable_decision_sha256=sealed.get('input_provenance',{}).get('decision_payload_sha256'),
            regular_session_1530_certified=report.get('source_regular_only_certified') is True,
            candidate_pool_status=audited['candidate_pool_status'],
            review_summary=[{k:row.get(k) for k in ('ticker','technical_status','final_status',
                'premium_over_entry_high_pct','costed_r1_rr','source_blockers')}
                for row in original],
            final_images=[{'name':Path(p).name,'sha256':h} for p,h in zip(paths,hashes)],
            image_count=len(paths))
    except Exception as exc:
        # Only an allowed code, never arbitrary error strings/secrets.
        reason=str(exc)
        if (isinstance(exc,ValueError) and reason.isupper() and len(reason)<100 and
                all(x.isupper() or x.isdigit() or x=='_' for x in reason)):
            status['reason']=reason
        else:
            status['reason']='REPLAY_SOURCE_OR_PRIVATE_READER_UNAVAILABLE'
    (root/'historical_replay_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in status.items() if k in
                      ('status','reason','asof','source_run_id','image_count',
                       'actual_telegram_send_attempts')}))
    return status


if __name__=='__main__':sys.exit(0 if execute()['status'].startswith(('PASS_','BLOCKED')) else 1)
