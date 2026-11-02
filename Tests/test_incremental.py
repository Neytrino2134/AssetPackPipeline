import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import incremental


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root/'model.fbx'
        self.source.write_bytes(b'geometry one')
        self.asset = {'id':'Asset_01', 'mesh_path':'/Game/Test/StaticMeshes/SM_Asset_01',
                      'lods':[{'index':0,'file':str(self.source),'node':'Asset_01_LOD0','triangles':3}],
                      'textures':{}}
        self.manifest = {'profile':{'destination_root':'/Game/Test','source_format':'FBX','pack_id':'Test',
                                    'lod_screen_sizes':[1.0], 'asset_overrides':{}, 'incremental':True},
                         'source_hashes':{str(self.source):incremental.discovery.digest(self.source)}}

    def test_convex_budget_change_invalidates_receipt(self):
        self.manifest['profile']['collision']='convex'
        first=incremental.fingerprint(self.manifest,self.asset,'settings_update','5.8.4')
        self.manifest['profile']['convex_collision']={'hull_count':16}
        self.assertNotEqual(first,incremental.fingerprint(self.manifest,self.asset,'settings_update','5.8.4'))

    def test_fingerprint_changes_for_effective_settings_and_operation(self):
        first = incremental.fingerprint(self.manifest, self.asset, 'import', '5.8.3')
        self.manifest['profile']['lod_screen_sizes'] = [1]
        self.manifest['profile']['roughness'] = .85
        self.assertEqual(first, incremental.fingerprint(self.manifest, self.asset, 'import', '5.8.3'))
        self.manifest['profile']['asset_overrides'] = {'Other':{'roughness':.3}}
        self.assertEqual(first, incremental.fingerprint(self.manifest, self.asset, 'import', '5.8.3'))
        self.manifest['profile']['asset_overrides']['Asset_01'] = {'roughness':.3}
        self.assertNotEqual(first, incremental.fingerprint(self.manifest, self.asset, 'import', '5.8.3'))
        self.assertNotEqual(first, incremental.fingerprint(self.manifest, self.asset, 'settings_update', '5.8.3'))

    def test_source_change_with_same_triangle_count_is_rejected(self):
        self.source.write_bytes(b'geometry two')
        with self.assertRaisesRegex(RuntimeError, 'Source changed'):
            incremental.sources_unchanged(self.manifest, self.asset)

    def test_nanite_mode_and_source_invalidate_receipt(self):
        original=incremental.fingerprint(self.manifest,self.asset,'import','5.8.3')
        self.manifest['profile']['nanite_enabled']=True
        enabled=incremental.fingerprint(self.manifest,self.asset,'import','5.8.3')
        self.assertNotEqual(original,enabled)
        self.manifest['profile']['nanite_source']='HIGH'
        self.assertNotEqual(enabled,incremental.fingerprint(self.manifest,self.asset,'import','5.8.3'))

    def test_saved_package_sidecar_hashes_detect_changes(self):
        content = Path(self.temp.name)/'Content'
        package = content/'Test/StaticMeshes/SM_Asset_01'
        package.parent.mkdir(parents=True)
        package.with_suffix('.uasset').write_bytes(b'asset')
        package.with_suffix('.uexp').write_bytes(b'export')
        original = incremental.output_hashes(content, [self.asset['mesh_path']])
        self.assertEqual(len(original), 2)
        package.with_suffix('.uexp').write_bytes(b'changed')
        self.assertNotEqual(original, incremental.output_hashes(content, [self.asset['mesh_path']]))
        package.with_suffix('.uasset').unlink()
        with self.assertRaises(FileNotFoundError):
            incremental.output_hashes(content, [self.asset['mesh_path']])
