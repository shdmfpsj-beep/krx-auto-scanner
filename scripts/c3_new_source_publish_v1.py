"""Append encrypted new-source evidence and dated research reviews only."""
import argparse,base64,hashlib,json,os,time
from pathlib import Path
from c3_telegram_inputs import GitHub,RESEARCH,canonical,ServiceError

PREFIX='reports/c3_new_session_v1/'


def publish(source,analysis,gh=None):
    from c3_supply_v11 import encrypt_bytes,open_sealed
    gh=gh or GitHub(os.environ['GH_TOKEN']);report=json.loads((analysis/'report.json').read_text())
    payload=json.loads((analysis/'source_payload.json').read_text());body=canonical(payload);digest=hashlib.sha256(body).hexdigest()
    if digest!=report['source_hash'] or payload['asof']!=report['source_date']:raise ValueError('RESEARCH_PUBLICATION_SOURCE_MISMATCH')
    day=report['source_date'];review_hash=report['report_payload_sha256'];copy=dict(report);copy.pop('report_payload_sha256')
    if hashlib.sha256(canonical(copy)).hexdigest()!=review_hash:raise ValueError('RESEARCH_PUBLICATION_REPORT_HASH_MISMATCH')
    path=PREFIX+'sources/'+day+'/'+digest+'.aesgcm';review=PREFIX+'reviews/'+day+'/'+review_hash+'.json'
    for attempt in range(2):
        head=gh.head(RESEARCH);commit=gh.api('git/commits/'+head);tree=gh.api('git/trees/'+head+'?recursive=1')
        if tree.get('truncated'):raise ValueError('RESEARCH_PUBLICATION_TREE_TRUNCATED')
        known={r['path']:r['sha'] for r in tree['tree'] if r['type']=='blob'};entries=[]
        if path in known:
            encrypted=base64.b64decode(gh.api('git/blobs/'+known[path])['content'])
            if hashlib.sha256(open_sealed(encrypted,os.environ.get('KRX_AUTH_KEY'))).hexdigest()!=digest:
                raise ValueError('IMMUTABLE_NEW_SOURCE_CONFLICT')
        else:
            encrypted=encrypt_bytes(body,os.environ.get('KRX_AUTH_KEY'))
            blob=gh.api('git/blobs',method='POST',payload={'content':base64.b64encode(encrypted).decode(),'encoding':'base64'})
            entries.append(dict(path=path,mode='100644',type='blob',sha=blob['sha']))
        receipt=dict(schema='C3_NEW_SESSION_SOURCE_RECEIPT_V1',asof=day,source_run_id=report['source_run_id'],
            analysis_run_id=report['research_run_id'],source_status=report['source_status'],source_sha256=digest,
            normalized_rows_sha256=report['normalized_rows_sha256'],encrypted_sha256=hashlib.sha256(encrypted).hexdigest(),
            original_signal_registered=False,key_persisted=False,report_payload_sha256=review_hash)
        values={review:report,PREFIX+'receipts/'+day+'/'+review_hash+'.json':receipt}
        latest_path=PREFIX+'latest.json'
        if latest_path not in known or json.loads(base64.b64decode(gh.api('git/blobs/'+known[latest_path])['content'])).get('source_date','')<=day:
            values[latest_path]=report
        for dest,doc in values.items():
            raw=canonical(doc)+b'\n'
            if dest!=latest_path and dest in known:
                if base64.b64decode(gh.api('git/blobs/'+known[dest])['content'])!=raw:raise ValueError('IMMUTABLE_RESEARCH_REVIEW_CONFLICT')
                continue
            if not dest.startswith(PREFIX):raise ValueError('NONRESEARCH_PUBLICATION_PATH')
            entries.append(dict(path=dest,mode='100644',type='blob',content=raw.decode()))
        if not entries:return dict(status='ALREADY_RECORDED',commit=head,source_sha256=digest,original_signal_registered=False)
        created=gh.api('git/trees',method='POST',payload={'base_tree':commit['tree']['sha'],'tree':entries})
        new=gh.api('git/commits',method='POST',payload={'tree':created['sha'],'parents':[head],'message':'research: preserve actual '+day+' source and V4 review (NO ORDERS / NO SEND)'})
        try:gh.api('git/refs/heads/'+RESEARCH,method='PATCH',payload={'sha':new['sha'],'force':False})
        except ServiceError:
            if attempt:raise
            continue
        return dict(status='RESEARCH_SOURCE_AND_REVIEW_REGISTERED',commit=new['sha'],branch=RESEARCH,source_record_path=path,
            review_record_path=review,source_sha256=digest,encrypted_sha256=hashlib.sha256(encrypted).hexdigest(),
            original_signal_registered=False,actual_telegram_requests=0)
    raise ValueError('RESEARCH_PUBLICATION_RETRY_EXHAUSTED')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=publish(a.source,a.analysis);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_bytes(canonical(result)+b'\n');print(json.dumps(result))
