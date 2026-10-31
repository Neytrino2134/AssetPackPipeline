import sys
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline.custom_snapshot import SnapshotAPI

class SnapshotTests(unittest.TestCase):
    def test_slow_editor_does_not_block_gui_cache(self):
        entered=threading.Event();release=threading.Event()
        class SlowEditor:
            def call(self,method,run):
                self.method=method;entered.set();release.wait(3)
                return {'ready':{'active_run':None},'report':None,'guided':None}
        remote=SlowEditor();api=SnapshotAPI({},transport=remote)
        api.start();self.addCleanup(api.close);self.addCleanup(release.set)
        self.assertTrue(entered.wait(1))
        started=time.monotonic()
        for _ in range(1000):
            self.assertFalse(api.snapshot()['connected']);api.readiness();api.guided_status()
        self.assertLess(time.monotonic()-started,.1)
        self.assertEqual(remote.method,'ui_snapshot')
        release.set();api.worker.join(.1)
        self.assertTrue(api.snapshot()['connected'])

    def test_disconnect_keeps_last_report_and_stops(self):
        class Offline:
            def call(self,*args):raise RuntimeError('editor closed')
        api=SnapshotAPI({},transport=Offline());api._work_thread=None
        api.start()
        deadline=time.monotonic()+1
        while 'error' not in api.snapshot() and time.monotonic()<deadline:time.sleep(.005)
        api.close();api.worker.join(1)
        self.assertFalse(api.worker.is_alive())
        self.assertEqual(api.snapshot()['error'],'editor closed')
