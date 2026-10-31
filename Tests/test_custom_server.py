import importlib
import json
import sys
import tempfile
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import custom_protocol as protocol

class ServerTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(sys.modules,{'unreal':types.SimpleNamespace()}):
            self.server=importlib.import_module('asset_pack_pipeline.custom_server')
        base=Path(__file__).resolve().parents[3]/'Saved/CustomServerTests'
        base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        s=self.server;s._busy=False;s._token='test-token';s._session='test-session';s._seen.clear()
        patches=[patch.object(s,'directory',return_value=self.root),patch.object(s,'active_guided',return_value=None)]
        for p in patches:p.start();self.addCleanup(p.stop)

    def request(self,method,created=None,token='test-token',request_id=None):
        key=request_id or uuid.uuid4().hex
        protocol.write(self.root/(key+'.request.json'),{'id':key,'session':'test-session','created':time.time() if created is None else created,'method':method,'args':[],'kwargs':{}},token)
        return key

    def test_authentication_and_expired_requests_never_dispatch(self):
        self.request('start',token='wrong')
        self.request('start',created=time.time()-500)
        with patch.object(self.server,'dispatch') as call:
            self.server.serve(0);call.assert_not_called()

    def test_duplicate_request_is_not_executed_twice(self):
        key=self.request('plan')
        with patch.object(self.server,'dispatch',return_value={'ready':True}) as call:
            self.server.serve(0)
            self.request('plan',request_id=key)
            self.server.serve(0)
            self.assertEqual(call.call_count,1)
        result=protocol.decode((self.root/(key+'.response.json')).read_text(encoding='utf-8'),'test-token')
        self.assertFalse(result['ok'])

    def test_arbitrary_python_method_is_rejected(self):
        with self.assertRaises(ValueError):self.server.dispatch('exec',['arbitrary'],{})
