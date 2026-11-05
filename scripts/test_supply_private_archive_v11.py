"""Private archive integrity, run where the optional crypto dependency is installed."""
import io,tempfile,unittest,zipfile
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


if __name__=='__main__':unittest.main()
