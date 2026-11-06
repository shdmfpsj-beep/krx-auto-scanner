"""Private archive integrity, run where the optional crypto dependency is installed."""
import hashlib,io,json,os,tempfile,unittest,zipfile
from unittest.mock import patch
from pathlib import Path
from c3_supply_v11 import seal,open_sealed


class PrivateArchiveTests(unittest.TestCase):
    def test_roundtrip_wrong_key_and_tamper(self):
        from cryptography.exceptions import InvalidTag
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'private';root.mkdir();(root/'x.json').write_text('SYNTHETIC_ONLY');p=Path(tmp)/'data.aesgcm';seal(root,p,'SYNTHETIC_KEY_NOT_REAL')
            with zipfile.ZipFile(io.BytesIO(open_sealed(p,'SYNTHETIC_KEY_NOT_REAL'))) as z:self.assertEqual(z.read('x.json'),b'SYNTHETIC_ONLY')
            with self.assertRaises(InvalidTag):open_sealed(p,'WRONG_SYNTHETIC_KEY')
            b=bytearray(p.read_bytes());b[-1]^=1;p.write_bytes(b)
            with self.assertRaises(InvalidTag):open_sealed(p,'SYNTHETIC_KEY_NOT_REAL')

    def test_encrypted_market_and_decision_retry_preserves_original(self):
        from c3_forward_ledger_v8 import freeze_market,read_record,immutable
        from test_c3_forward_ledger_v8 import market
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'KRX_AUTH_KEY':'SYNTHETIC_KEY_NOT_REAL'}):
            root=Path(tmp)/'lanes'/'synthetic';m=market(0);_,added=freeze_market(root,m,'2026-11-06T07:01:00Z');self.assertTrue(added)
            path=root/'markets/2026-11-06.json.gz';before=path.read_bytes();self.assertTrue(before.startswith(b'C3V11GCM1'));self.assertEqual(read_record(path),m)
            _,added=freeze_market(root,m,'2026-11-06T07:02:00Z');self.assertFalse(added);self.assertEqual(path.read_bytes(),before)
            decision=root/'decisions/synthetic.json';self.assertTrue(immutable(decision,{'synthetic':True}));body=decision.read_bytes();self.assertFalse(immutable(decision,{'synthetic':True}));self.assertEqual(body,decision.read_bytes())
            with self.assertRaisesRegex(ValueError,'CONFLICT'):immutable(decision,{'synthetic':False})


class RecoveryV13Tests(unittest.TestCase):
    def manifest(self,root,body):
        p=Path(root)/'inputs.json';p.write_text(json.dumps(dict(artifacts={'panel':dict(id=1,sha256=hashlib.sha256(body).hexdigest())})));return p

    def zipped(self,name='nested/synthetic.txt'):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(name,'SYNTHETIC_ONLY')
        return b.getvalue()

    def test_new_owner_key_reads_old_records_without_changing_ciphertext(self):
        from c3_archive_keys_v13 import prepare_rotation
        from c3_forward_ledger_v8 import immutable,read_record
        with tempfile.TemporaryDirectory() as tmp:
            keys=Path(tmp)/'keys';record=Path(tmp)/'lanes/old/record.json'
            with patch.dict(os.environ,{'KRX_AUTH_KEY':'SYNTHETIC_OLD_KEY','C3_KEY_ENVELOPES_DIR':str(keys)}):immutable(record,{'synthetic':True})
            before=record.read_bytes();result=prepare_rotation(keys,'SYNTHETIC_OLD_KEY','SYNTHETIC_NEW_KEY')
            self.assertNotIn('SYNTHETIC_OLD_KEY',json.dumps(result));self.assertNotIn('SYNTHETIC_NEW_KEY',json.dumps(result))
            with patch.dict(os.environ,{'KRX_AUTH_KEY':'SYNTHETIC_NEW_KEY','C3_KEY_ENVELOPES_DIR':str(keys)}):self.assertEqual(read_record(record),{'synthetic':True})
            self.assertEqual(record.read_bytes(),before)

    def test_multiple_rotations_keep_all_prior_keys_and_fail_closed_on_tamper(self):
        from c3_archive_keys_v13 import prepare_rotation
        from c3_supply_v11 import encrypt_bytes
        from cryptography.exceptions import InvalidTag
        with tempfile.TemporaryDirectory() as tmp:
            keys=Path(tmp)/'keys';a=Path(tmp)/'a.enc';b=Path(tmp)/'b.enc';a.write_bytes(encrypt_bytes(b'SYNTHETIC_A','KEY_A'));b.write_bytes(encrypt_bytes(b'SYNTHETIC_B','KEY_B'))
            prepare_rotation(keys,'KEY_A','KEY_B');r=prepare_rotation(keys,'KEY_B','KEY_C');self.assertEqual(r['retired_key_count'],2)
            with patch.dict(os.environ,{'C3_KEY_ENVELOPES_DIR':str(keys)}):
                self.assertEqual(open_sealed(a,'KEY_C'),b'SYNTHETIC_A');self.assertEqual(open_sealed(b,'KEY_C'),b'SYNTHETIC_B')
                with self.assertRaises(InvalidTag):open_sealed(a,'WRONG_OWNER')
                body=bytearray(a.read_bytes());body[-1]^=1;a.write_bytes(body)
                with self.assertRaises(InvalidTag):open_sealed(a,'KEY_C')
            with self.assertRaises(ValueError):prepare_rotation(keys,'KEY_C','KEY_C')

    def test_pin_preserved_and_warm_bootstrap_ignores_expired_or_missing_artifact(self):
        from c3_bootstrap_cache_v13 import restore
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'KRX_AUTH_KEY':'SYNTHETIC_CACHE_KEY'}):
            root=Path(tmp);body=self.zipped();m=self.manifest(root,body);ledger=root/'ledger'
            first=restore(m,root/'first',ledger,root/'audit.json',reader=lambda _: (body,dict(expires_at='SYNTHETIC_EXPIRY')))
            p=next((ledger/'bootstrap').glob('*.aesgcm'));before=p.read_bytes()
            def missing(_):self.fail('A verified encrypted pin must restore without an artifact request')
            second=restore(m,root/'second',ledger,root/'audit2.json',reader=missing)
            self.assertEqual(first[0]['source'],'GITHUB_ARTIFACT');self.assertEqual(second[0]['source'],'ENCRYPTED_PINNED_GIT_CACHE')
            self.assertEqual((root/'second/panel/nested/synthetic.txt').read_text(),'SYNTHETIC_ONLY');self.assertEqual(p.read_bytes(),before)

    def test_cache_tampering_and_wrong_pin_do_not_trigger_silent_replacement(self):
        from c3_bootstrap_cache_v13 import restore
        from cryptography.exceptions import InvalidTag
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'KRX_AUTH_KEY':'SYNTHETIC_CACHE_KEY'}):
            root=Path(tmp);body=self.zipped();m=self.manifest(root,body)
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):restore(m,root/'bad',root/'bad-ledger',root/'bad.json',reader=lambda _: (b'WRONG_SOURCE',{}))
            self.assertFalse(list((root/'bad-ledger').rglob('*.aesgcm')))
            restore(m,root/'first',root/'ledger',root/'audit.json',reader=lambda _: (body,{}));p=next((root/'ledger/bootstrap').glob('*.aesgcm'));wire=bytearray(p.read_bytes());wire[-1]^=1;p.write_bytes(wire)
            with self.assertRaises(InvalidTag):restore(m,root/'second',root/'ledger',root/'audit2.json',reader=lambda _:self.fail('No network replacement for tampered cache'))

    def test_pinned_zip_cannot_write_outside_bootstrap_root(self):
        from c3_bootstrap_cache_v13 import restore
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'KRX_AUTH_KEY':'SYNTHETIC_CACHE_KEY'}):
            root=Path(tmp);body=self.zipped('../escape.txt');m=self.manifest(root,body)
            with self.assertRaisesRegex(ValueError,'PATH_REJECTED'):restore(m,root/'inputs',root/'ledger',root/'audit.json',reader=lambda _: (body,{}))
            self.assertFalse((root/'escape.txt').exists());self.assertFalse(list((root/'ledger').rglob('*.aesgcm')))

    def test_no_cache_and_unavailable_artifact_does_not_fabricate_inputs(self):
        from c3_bootstrap_cache_v13 import restore
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);body=self.zipped();m=self.manifest(root,body)
            def expired(_):raise ValueError('BOOTSTRAP_ARTIFACT_EXPIRED_NO_GIT_CACHE')
            with self.assertRaisesRegex(ValueError,'EXPIRED_NO_GIT_CACHE'):restore(m,root/'inputs',root/'ledger',root/'audit.json',reader=expired)
            self.assertFalse((root/'inputs/panel').exists())

    def test_existing_original_prices_and_payload_hashes_are_recoverable(self):
        from c3_bootstrap_cache_v13 import verify_storage
        from c3_forward_ledger_v8 import immutable
        from test_c3_supply_runtime_v12 import fixture
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'KRX_AUTH_KEY':'SYNTHETIC_OWNER_KEY'}):
            root=Path(tmp);source=root/'source';fixture(source);ledger=root/'ledger';p=ledger/'lanes/krx_unadjusted_v12/supply_archives/2026-11-05/a.aesgcm';p.parent.mkdir(parents=True);seal(source,p,'SYNTHETIC_OWNER_KEY')
            immutable(ledger/'lanes/krx_unadjusted_v12/supply_receipts/2026-11-05/a.json',{'synthetic':True})
            audit=verify_storage(ledger,full=True);self.assertEqual(audit['records_verified'],1);self.assertEqual(audit['original_archives_verified'],1);self.assertEqual(audit['mutations'],0)
            (source/'KOSPI_official.csv').write_text('SYNTHETIC_CORRECTION_WITHOUT_HASH');seal(source,p,'SYNTHETIC_OWNER_KEY')
            with self.assertRaisesRegex(ValueError,'ORIGINAL_MARKET_HASH_MISMATCH'):verify_storage(ledger,full=True)


if __name__=='__main__':unittest.main()
