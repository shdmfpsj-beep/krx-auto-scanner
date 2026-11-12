"""Research image envelope and a transport-contract test. Never live-sends.

The operational Telegram class is reused behind a local fake HTTP boundary.
No bot credential is loaded. A research namespace cannot reserve a live key.
"""
import hashlib,json
from pathlib import Path
from unittest.mock import patch
from c3_telegram_notify import Telegram,validate_photos

def envelope(paths,manifests,report):
    expected=max(1,len(report['watch_top2']))
    if len(paths)!=expected or len(manifests)!=expected:raise ValueError('RESEARCH_CARD_COUNT_MISMATCH')
    hashes=validate_photos(paths)
    for p,m,h in zip(paths,manifests,hashes):
        if m['png_sha256']!=h:raise ValueError('IMAGE_HASH_MISMATCH')
        if report['watch_top2'] and any(m.get(k)!=report[v] for k,v in (
            ('source_run_id','source_run_id'),('source_hash','source_hash'),('report_hash','report_payload_sha256'),('price_asof','source_date'))):
            raise ValueError('IMAGE_SOURCE_OR_REPORT_PROVENANCE_MISMATCH')
    return dict(key='research-observation-v1/'+report['source_date']+'/'+report['report_payload_sha256'],
        image_count=expected,images_sha256=hashes,source_run_id=report['source_run_id'],source_hash=report['source_hash'],
        report_sha256=report['report_payload_sha256'],mode='RESEARCH_PREVIEW_NOT_APPROVED_FOR_LIVE_CHANNEL',
        automatic_send_enabled=False,actual_telegram_requests=0)

def transport_test(paths):
    """Uses real multipart/media-group code; no network call can escape."""
    calls=[];chat='-1009999999999';ids=list(range(9001,9001+len(paths)))
    class Response:
        status_code=200
        def __init__(self,doc):self.doc=doc
        def json(self):return self.doc
    def fake(url,**kwargs):
        if url.endswith('/getChat'):return Response(dict(ok=True,result=dict(id=int(chat),type='supergroup',title='강현AI')))
        calls.append(dict(method=url.rsplit('/',1)[-1],data=kwargs.get('data'),files=[p[0] for p in kwargs.get('files',[])]))
        data=kwargs['data']
        if 'caption' in data or 'text' in data:raise AssertionError('CAPTION_OR_TEXT_FORBIDDEN')
        if 'media' in data and any('caption' in m or 'text' in m for m in json.loads(data['media'])):raise AssertionError('MEDIA_CAPTION_FORBIDDEN')
        messages=[dict(message_id=i,photo=[dict(file_id='TEST_ONLY')],chat=dict(id=int(chat)),media_group_id='mock-album') for i in ids]
        return Response(dict(ok=True,result=messages[0] if len(paths)==1 else messages))
    with patch('c3_telegram_notify.requests.post',side_effect=fake):
        bot=Telegram('FAKE_TEST_CREDENTIAL',chat);bot.verify_group();receipt=bot.send_album(paths)
    return dict(status='MOCK_DELIVERED',test_only=True,actual_telegram_requests=0,receipt=receipt,calls=calls,
        live_delivery_confirmed=False,human_receipt_confirmed=False)

def safe_claim(claims,key,body):
    if not key.startswith('research-observation-v1/'):raise ValueError('RESEARCH_NAMESPACE_REQUIRED')
    if key in claims:return 'DUPLICATE_BLOCKED'
    claims[key]=body
    return 'CLAIMED_NO_AUTOMATIC_RETRY_AFTER_UNCERTAIN_SEND'
