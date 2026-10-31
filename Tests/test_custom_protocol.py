import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import custom_protocol as p

class ProtocolTests(unittest.TestCase):
    def test_roundtrip_and_tampering(self):
        text=p.encode({'method':'plan','args':['путь/FBX']},'test-key')
        self.assertEqual(p.decode(text,'test-key')['method'],'plan')
        with self.assertRaises(ValueError):p.decode(text.replace('plan','exec'),'test-key')
        with self.assertRaises(ValueError):p.decode(text,'wrong-key')

    def test_size_cap(self):
        from unittest.mock import patch
        with patch.object(p,'MAX_BYTES',20),self.assertRaises(ValueError):
            p.decode('x'*21,'test')

    def test_atomic_message_contains_no_auth_secret(self):
        folder=Path(__file__).resolve().parents[3]/'Saved/CustomProtocolTests'
        folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            path=Path(temp)/'response.json'
            p.write(path,{'id':'abc','ok':True},'never-written-secret')
            self.assertNotIn('never-written-secret',path.read_text())
            self.assertEqual(p.decode(path.read_text(),'never-written-secret')['id'],'abc')
