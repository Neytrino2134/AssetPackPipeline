import base64
import importlib
import json
import sys
import tempfile
import types
import queue
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))


class NativeAgentTests(unittest.TestCase):
    def setUp(self):
        fake = types.SimpleNamespace(log_error=lambda text: None)
        with patch.dict(sys.modules, {'unreal':fake}):
            self.bridge = importlib.import_module('asset_pack_pipeline.native_bridge')
        b = self.bridge
        b._history.clear(); b._chat_log.clear(); b._events.clear()
        b._ai_round=0; b._ai_cancelled=False
        b._network=queue.Queue(); b._network_busy=False; b._session=None; b._observed_run=None; b._tick=None; b._last=0
        b._ai_snapshot={'action':'chat','pack':'SnapshotPack','source':'SnapshotSource','model':'test'}
        b._pending_ai={'type':'function_call','name':'pipeline_action','arguments':'{"action":"prepare_pack"}','call_id':'test'}
        b._last_result={}
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.patches=[patch.object(b,'folder',return_value=Path(self.folder.name)),
                      patch('asset_pack_pipeline.ai_settings.get_key',return_value='unit-test-key'),
                      patch.object(b,'launch_ai')]
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def test_reject_never_dispatches_action(self):
        with patch.object(self.bridge,'submit_b64') as execute:
            self.bridge.decide_ai(False)
            execute.assert_not_called()
        self.assertEqual(json.loads(self.bridge._history[-1]['output'])['status'],'rejected')

    def test_approved_action_uses_snapshot_and_whitelist(self):
        with patch.object(self.bridge,'submit_b64') as execute:
            self.bridge.decide_ai(True)
            data=json.loads(base64.b64decode(execute.call_args.args[0]))
            self.assertEqual(data['action'],'start')
            self.assertEqual(data['pack'],'SnapshotPack')

    def test_unknown_action_does_not_execute(self):
        self.bridge._pending_ai['arguments']='{"action":"delete"}'
        with patch.object(self.bridge,'submit_b64') as execute, self.assertRaises(ValueError):
            self.bridge.decide_ai(True)
        execute.assert_not_called()

    def test_history_survives_job_updates_and_redacts_secret(self):
        self.bridge.chat_line('Вы','unit-test-key and sk-secret123456789')
        self.bridge.state({'stage':'import'})
        self.bridge.state({'stage':'validate'})
        value=json.loads((Path(self.folder.name)/'state.json').read_text())
        self.assertNotIn('unit-test-key',value['chat_history'])
        self.assertNotIn('sk-secret123456789',value['chat_history'])
        self.assertIn('import',value['task_history'])
        self.assertIn('validate',value['task_history'])

    def test_round_limit_clears_pending_context(self):
        self.bridge._ai_round=5
        self.bridge.decide_ai(False)
        self.assertFalse(self.bridge._history)

    def test_confirmation_mode_stops_before_execution(self):
        b=self.bridge
        call=dict(b._pending_ai)
        b._pending_ai=None; b._ai_permission='Подтверждать действия'
        b._network.put(('chat',[call]))
        with patch.object(b,'submit_b64') as execute:
            b.poll(0)
            execute.assert_not_called()
        self.assertEqual(b._pending_ai['call_id'],'test')

    def test_advice_mode_cannot_execute_tool_output(self):
        b=self.bridge
        call=dict(b._pending_ai)
        b._pending_ai=None; b._ai_permission='Только советы'
        b._network.put(('chat',[call]))
        with patch.object(b,'submit_b64') as execute:
            b.poll(0)
            execute.assert_not_called()
        self.assertIsNone(b._pending_ai)

    def test_cancelled_network_reply_is_not_executed(self):
        b=self.bridge
        b._ai_cancelled=True; b._pending_ai=None
        b._network.put(('chat',[{'type':'message','content':[{'type':'output_text','text':'late response'}]}]))
        b.poll(0)
        self.assertFalse(b._history)
