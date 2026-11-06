"""Owner-encrypted key migration; never rewrite an immutable price record.

Prepare with both owner keys BEFORE replacing KRX_AUTH_KEY. The new key can
unwrap retired data keys. No key or decrypted envelope is returned or logged.
This does not change any API credential, GitHub Secret, or provider permission.
"""
import argparse,hashlib,json,os
from pathlib import Path

DEFAULT_DIR='reports/c3_forward_v8/key_envelopes'
MAX_KEYS=16


def retired_keys(current,folder=None):
    from cryptography.exceptions import InvalidTag
    from c3_supply_v11 import decrypt_bytes
    root=Path(folder or os.environ.get('C3_KEY_ENVELOPES_DIR',DEFAULT_DIR));keys=[]
    paths=sorted(root.glob('*.aesgcm'))
    if len(paths)>32:raise ValueError('KEY_ENVELOPE_BUDGET_EXCEEDED')
    for p in paths:
        body=p.read_bytes()
        if len(body)>65536:raise ValueError('KEY_ENVELOPE_SIZE_INVALID')
        try:plain=decrypt_bytes(body,current)
        except InvalidTag:continue  # A previous envelope can be for another owner key.
        try:
            doc=json.loads(plain)
            if doc.get('schema')!='C3_OWNER_KEY_ENVELOPE_V13' or not isinstance(doc.get('retired_keys'),list):raise ValueError()
            values=doc['retired_keys']
            if len(values)>MAX_KEYS or any(not isinstance(k,str) or not k or len(k)>1024 for k in values):raise ValueError()
        except (ValueError,TypeError,AttributeError):raise ValueError('KEY_ENVELOPE_SCHEMA_INVALID') from None
        for key in values:
            if key!=current and key not in keys:keys.append(key)
        if len(keys)>MAX_KEYS:raise ValueError('RETIRED_KEY_BUDGET_EXCEEDED')
    return keys


def prepare_rotation(folder,previous,new):
    from c3_supply_v11 import encrypt_bytes,decrypt_bytes
    if not previous or not new or previous==new:raise ValueError('DISTINCT_OLD_AND_NEW_OWNER_KEYS_REQUIRED')
    keys=[previous]+retired_keys(previous,folder)
    if len(keys)>MAX_KEYS:raise ValueError('RETIRED_KEY_BUDGET_EXCEEDED')
    plain=json.dumps(dict(schema='C3_OWNER_KEY_ENVELOPE_V13',retired_keys=keys),sort_keys=True,separators=(',',':')).encode()
    body=encrypt_bytes(plain,new)
    if decrypt_bytes(body,new)!=plain:raise ValueError('KEY_ENVELOPE_ROUNDTRIP_FAILED')
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    path=root/(hashlib.sha256(body).hexdigest()+'.aesgcm')
    with path.open('xb') as f:f.write(body)
    return dict(envelope_file=path.name,retired_key_count=len(keys),key_values_returned=False,existing_ciphertexts_rewritten=False,
        github_secrets_changed=False,real_rotation_requires_full_restore_verification=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',default=DEFAULT_DIR);a=p.parse_args()
    print(json.dumps(prepare_rotation(a.directory,os.environ.get('C3_OLD_ARCHIVE_KEY'),os.environ.get('C3_NEW_ARCHIVE_KEY'))))
