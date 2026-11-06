"""Hash-pinned owner-encrypted bootstrap recovery independent of artifact expiry."""
import hashlib,io,json,os,re,stat,subprocess,zipfile
from pathlib import Path
from c3_supply_v11 import encrypt_bytes,open_sealed,write

REPO='shdmfpsj-beep/krx-auto-scanner'
LIMIT=128*1024*1024


def extract(body,root):
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or sum(i.file_size for i in z.infolist())>512*1024*1024:raise ValueError('BOOTSTRAP_ZIP_BUDGET_OR_DUPLICATE')
        if any(Path(n).is_absolute() or '..' in Path(n).parts or '\\' in n for n in names):raise ValueError('BOOTSTRAP_ZIP_PATH_REJECTED')
        if any(stat.S_ISLNK(i.external_attr>>16) for i in z.infolist()):raise ValueError('BOOTSTRAP_ZIP_SYMLINK_REJECTED')
        z.extractall(root)


def read_artifact(item):
    path='repos/'+REPO+'/actions/artifacts/'+str(item['id'])
    try:meta=json.loads(subprocess.check_output(['gh','api',path],text=True,stderr=subprocess.DEVNULL,timeout=30))
    except subprocess.CalledProcessError:raise ValueError('BOOTSTRAP_ARTIFACT_UNAVAILABLE_NO_GIT_CACHE') from None
    if meta.get('expired'):raise ValueError('BOOTSTRAP_ARTIFACT_EXPIRED_NO_GIT_CACHE')
    if meta.get('size_in_bytes',0)>LIMIT:raise ValueError('BOOTSTRAP_ARCHIVE_TOO_LARGE')
    try:body=subprocess.check_output(['gh','api',path+'/zip'],timeout=60,stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:raise ValueError('BOOTSTRAP_ARTIFACT_DOWNLOAD_FAILED_NO_GIT_CACHE') from None
    return body,dict(expired=False,expires_at=meta.get('expires_at'))


def restore(manifest,inputs,ledger,audit_path,reader=read_artifact):
    m=json.loads(Path(manifest).read_text());root=Path(inputs);cache=Path(ledger)/'bootstrap';cache.mkdir(parents=True,exist_ok=True);audit=[]
    for name,item in m['artifacts'].items():
        if Path(name).name!=name:raise ValueError('BOOTSTRAP_INPUT_NAME_INVALID')
        if not re.fullmatch('[0-9a-f]{64}',item['sha256']):raise ValueError('BOOTSTRAP_HASH_FORMAT_INVALID')
        path=cache/(item['sha256']+'.aesgcm');source='ENCRYPTED_PINNED_GIT_CACHE';extra={}
        if path.exists():body=open_sealed(path,os.environ.get('KRX_AUTH_KEY'))
        else:body,extra=reader(item);source='GITHUB_ARTIFACT'
        if len(body)>LIMIT or hashlib.sha256(body).hexdigest()!=item['sha256']:raise ValueError('PINNED_BOOTSTRAP_SOURCE_HASH_MISMATCH:'+name)
        dest=root/name;dest.mkdir(parents=True,exist_ok=True);extract(body,dest)
        if not path.exists():
            encrypted=encrypt_bytes(body,os.environ.get('KRX_AUTH_KEY'))
            with path.open('xb') as f:f.write(encrypted)
            write(cache/(item['sha256']+'.manifest.json'),dict(schema='C3_PINNED_BOOTSTRAP_CACHE_V13',artifact_id=item['id'],plaintext_sha256=item['sha256'],ciphertext_sha256=hashlib.sha256(encrypted).hexdigest(),bytes=len(encrypted),key_persisted=False))
        check=cache/(item['sha256']+'.manifest.json')
        if check.exists() and json.loads(check.read_text())['ciphertext_sha256']!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('BOOTSTRAP_CACHE_CIPHERTEXT_MISMATCH')
        audit.append(dict(name=name,id=item['id'],sha256=item['sha256'],source=source,encrypted_git_cache_verified=True,bytes=len(body),**extra))
        write(audit_path,audit)
    return audit


def verify_storage(ledger,full=False):
    """Read ciphertexts and payload hashes without returning their contents."""
    from c3_forward_ledger_v8 import read_record
    root=Path(ledger);records=[];archives=[]
    for folder,pattern in [('markets','*.json.gz'),('decisions','*.json'),('observations','*.json'),('corrections','*.json'),('supply_receipts','*.json')]:
        got=sorted((root/'lanes/krx_unadjusted_v12'/folder).rglob(pattern));records+=got if full else got[-1:]
    for p in records:read_record(p)
    candidates=sorted((root/'lanes/krx_unadjusted_v12/supply_archives').rglob('*.aesgcm'));archives=candidates if full else candidates[-1:]
    for p in archives:
        with zipfile.ZipFile(io.BytesIO(open_sealed(p,os.environ.get('KRX_AUTH_KEY')))) as z:
            m=json.loads(z.read('krx_v65_collect_status.json'))
            for market,expected in m['market_file_sha256'].items():
                name=(m.get('price_files') or {}).get(market,market+'_official.csv')
                if hashlib.sha256(z.read(name)).hexdigest()!=expected:raise ValueError('STORED_ORIGINAL_MARKET_HASH_MISMATCH')
    bootstrap=list((root/'bootstrap').glob('*.aesgcm'))
    for p in bootstrap:
        if hashlib.sha256(open_sealed(p,os.environ.get('KRX_AUTH_KEY'))).hexdigest()!=p.stem:raise ValueError('BOOTSTRAP_RESTORE_HASH_MISMATCH')
    return dict(scope='FULL_CURRENT_INVENTORY' if full else 'LATEST_RECORDS_AND_ALL_BOOTSTRAP',records_verified=len(records),original_archives_verified=len(archives),bootstrap_archives_verified=len(bootstrap),mutations=0,key_values_returned=False)
