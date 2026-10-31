import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import assistant


class AssistantTests(unittest.TestCase):
    def test_arbitrary_code_tool_rejected(self):
        with self.assertRaises(ValueError):
            assistant.decode_action({'type':'function_call','name':'python','arguments':'{}'})
        with self.assertRaises(ValueError):
            assistant.decode_action({'type':'function_call','name':'pipeline_action',
                                     'arguments':'{"action":"delete"}', 'call_id':'x'})

    def test_extra_arguments_rejected(self):
        with self.assertRaises(ValueError):
            assistant.decode_action({'type':'function_call','name':'pipeline_action',
                                     'arguments':'{"action":"status","code":"unsafe"}', 'call_id':'x'})

    def test_missing_key_stops_before_network(self):
        with patch.dict('os.environ', {}, clear=True), patch('urllib.request.build_opener') as network:
            with self.assertRaisesRegex(RuntimeError, 'OPENAI_API_KEY'):
                assistant.request('model', [])
            network.assert_not_called()

    def test_http_errors_do_not_expose_body_or_key(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY':'unit-test-secret'}), patch('urllib.request.build_opener') as network:
            network.return_value.open.side_effect = urllib.error.HTTPError('url',401,'private error',{},None)
            with self.assertRaises(RuntimeError) as error:
                assistant.request('model', [])
            self.assertNotIn('unit-test-secret', str(error.exception))
            self.assertNotIn('private error', str(error.exception))

    def test_advice_mode_omits_tools_and_disables_storage(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY':'unit-test-secret'}), patch('urllib.request.build_opener') as network:
            network.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"status":"completed","output":[]}'
            assistant.request('model', [{'role':'user','content':'Help'}], True)
            req = network.return_value.open.call_args.args[0]
            body = json.loads(req.data)
            self.assertNotIn('tools', body)
            self.assertFalse(body['store'])
            self.assertNotIn('unit-test-secret', req.data.decode())
