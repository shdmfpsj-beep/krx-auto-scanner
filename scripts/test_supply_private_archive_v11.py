"""Private archive integrity, run where the optional crypto dependency is installed."""
import io,os,tempfile,unittest,zipfile
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


if __name__=='__main__':unittest.main()
