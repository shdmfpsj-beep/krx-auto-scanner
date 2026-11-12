"""Restore this Work execution's verified financial snapshot for Nov11 replay.

Never a fallback for future dates; the original collection timestamp and
unverified-PIT status remain intact. No OpenDART request or ledger write.
"""
import argparse,hashlib,io,subprocess,zipfile
from pathlib import Path

ARTIFACT_ID=13902868724
ZIP_SHA='ca26e3e5ab90b3275bec1f742e97a288a35338fb22852f84ad363cdc300df0c7'

def restore(path):
    body=subprocess.check_output(['gh','api','repos/shdmfpsj-beep/krx-auto-scanner/actions/artifacts/'+str(ARTIFACT_ID)+'/zip'],timeout=60)
    if hashlib.sha256(body).hexdigest()!=ZIP_SHA:raise ValueError('PINNED_COMPANY_SOURCE_ARTIFACT_HASH_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        item=z.getinfo('company/company_quality.json')
        if item.file_size>2*1024*1024:raise ValueError('PINNED_COMPANY_SOURCE_OVERSIZED')
        raw=z.read(item)
    import json
    doc=json.loads(raw)
    if doc.get('asof')!='2026-11-11' or doc.get('requested')!=149:raise ValueError('PINNED_COMPANY_SOURCE_DATE_MISMATCH')
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();print(restore(a.out))
