import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline.guided import prepare, Session


class GuidedTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((Path(__file__).resolve().parents[1]/'Content/Profiles/profile.example.json').read_text())
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def test_both_preserves_all_models_and_shared_destination(self):
        profiles, steps = prepare(self.base, self.folder.name, 'TestPack', 'FBX', renders=['overview'])
        self.assertEqual(set(profiles), {'LOD', 'Nanite'})
        self.assertTrue(all('asset_ids' not in p for p in profiles.values()))
        self.assertEqual(profiles['LOD']['destination_root'], profiles['Nanite']['destination_root'])
        self.assertTrue(profiles['Nanite']['nanite_enabled'])
        self.assertEqual(steps.count(('LOD', 'preview')), 1)
        self.assertNotIn(('Nanite', 'preview'), steps)
        self.assertIn('asset_ids', self.base)

    def test_lod_render_selection_is_deduplicated(self):
        p, steps = prepare(self.base, self.folder.name, 'TestPack', 'GLB', renders=['LOW', 'LODS', 'selected'], lod=2)
        self.assertEqual(p['LOD']['media']['lod_indices'], [0, 1, 2, 3, 4])
        self.assertEqual(steps.count(('LOD', 'media')), 1)

    def test_incompatible_render_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            prepare(self.base, self.folder.name, 'TestPack', 'FBX', 'LOD', ['MID'])

    def test_cancel_does_not_start_another_step(self):
        class API:
            def start(self, path): return 'job'
            def cancel(self, job): self.cancelled = job
        api = API()
        session = Session(api, {'LOD': 'p'}, [('LOD', 'import'), ('LOD', 'media')])
        session.tick()
        session.cancel()
        session.tick()
        self.assertEqual(api.cancelled, 'job')
        self.assertTrue(session.done)

    def test_failed_job_stops_pipeline(self):
        class API:
            def start(self, path): return 'job'
            def status(self, job): return {'status': 'failed'}
        session = Session(API(), {'LOD': 'p'}, [('LOD', 'import'), ('LOD', 'media')])
        session.tick()
        session.tick()
        self.assertTrue(session.done)
        self.assertIsNotNone(session.error)

    def test_delivery_follows_renders_and_requires_verification(self):
        profiles, steps = prepare(self.base, self.folder.name, 'TestPack', 'FBX', renders=['overview'], finalize=True, output=self.folder.name)
        self.assertEqual([op for _, op in steps][-3:], ['delivery', 'verify_delivery', 'package'])
        self.assertEqual(profiles['Nanite']['delivery']['output_directory'], self.folder.name)
        class API:
            def start_delivery_verification(self, job): return 'verification'
            def status(self, job): return {'status':'failed'}
            def package_delivery(self, job): raise AssertionError('Must not package after failed verification')
        session = Session(API(), {'LOD':'p'}, [('LOD','verify_delivery'), ('LOD','package')])
        session.delivery_id = 'delivery'
        session.tick()
        session.tick()
        self.assertTrue(session.error)

    def test_editor_reentrant_tick_does_not_launch_next_step(self):
        class API:
            def start(self,path):
                session.tick()
                return 'job'
            def validate(self,path):
                raise AssertionError('Must wait for start to return and job to finish')
        session=Session(API(),{'LOD':'p'},[('LOD','import'),('LOD','validate')])
        session.tick()
        self.assertEqual(session.waiting,'job')
        self.assertIsNone(session.error)
        self.assertFalse(session.done)
