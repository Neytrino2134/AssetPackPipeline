import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))


class Asset:
    def __init__(self, path, kind):
        self.path, self.kind = path, kind


class FakeUnreal:
    """Just enough of the editor API for cleanup.plan/execute_forced."""

    def __init__(self, content, assets, referencers, current, presentation=True):
        self.content, self.assets, self.referencers, self.current = content, dict(assets), referencers, current
        self.calls, self.dirty = [], []
        self.presentation = presentation
        u = types.SimpleNamespace()
        for name in ('StaticMesh', 'Material', 'MaterialInstanceConstant', 'Texture2D', 'World'):
            setattr(u, name, type(name, (Asset,), {}))
        self.types = u
        fake = self

        class Library:
            @staticmethod
            def list_assets(root, recursive=True, include_folder=False):
                listed = list(fake.assets) + (['/Game/Presentation/L_Presentation.L_Presentation'] if fake.presentation else [])
                return [p for p in listed if p.startswith(root+'/')]
            get_metadata_tag = staticmethod(lambda obj, tag: '')
            find_package_referencers_for_asset = staticmethod(lambda path, load_assets_to_confirm=True: [])
            does_asset_exist = staticmethod(lambda package: any(p.split('.')[0] == package for p in fake.assets))
            does_directory_exist = staticmethod(lambda root: any(p.startswith(root+'/') for p in fake.assets))

            @staticmethod
            def delete_directory(root):
                fake.calls.append(('delete_directory', root))
                for p in [p for p in fake.assets if p.startswith(root+'/')]:
                    del fake.assets[p]
                    file = Path(fake.content)/(p.split('.')[0].removeprefix('/Game/')+'.uasset')
                    file.unlink(missing_ok=True)
                fake.dirty = ['/Game/AssetPackPipeline_Previews/abc/Studio']
                return True
        u.EditorAssetLibrary = Library
        u.load_asset = lambda path: fake.assets.get(path) or Asset(path, 'other')
        registry = types.SimpleNamespace(search_all_assets=lambda synchronous_search=True: None,
                                         scan_paths_synchronous=lambda paths, force_rescan=True: None,
                                         get_referencers=lambda package, options: fake.referencers.get(package, []))
        u.AssetRegistryHelpers = types.SimpleNamespace(get_asset_registry=lambda: registry)
        u.AssetRegistryDependencyOptions = lambda **kw: None
        world = types.SimpleNamespace(get_path_name=lambda: fake.current+'.'+fake.current.rsplit('/', 1)[-1])
        levels = types.SimpleNamespace(
            load_level=lambda path: (fake.calls.append(('load_level', path)), setattr(fake, 'current', path))[-1] is None,
            new_level_from_template=lambda path, template: (fake.calls.append(('new_level_from_template', path, template)),
                                                            setattr(fake, 'current', path))[-1] is None,
            new_level=lambda path: (fake.calls.append(('new_level', path)), True)[-1],
            save_current_level=lambda: (fake.calls.append(('save_current_level',)), True)[-1])
        u.UnrealEditorSubsystem, u.LevelEditorSubsystem = 'editor', 'levels'
        u.get_editor_subsystem = lambda cls: types.SimpleNamespace(get_editor_world=lambda: world) if cls == 'editor' else levels
        package = lambda name: types.SimpleNamespace(get_name=lambda: name)
        u.EditorLoadingAndSavingUtils = types.SimpleNamespace(
            get_dirty_map_packages=lambda: [package(p) for p in fake.dirty],
            get_dirty_content_packages=lambda: [],
            save_packages=lambda packages, only_dirty: True,
            save_dirty_packages=lambda maps, content: (fake.calls.append(('save_dirty', list(fake.dirty))), fake.dirty.clear()))
        u.Paths = types.SimpleNamespace(project_content_dir=lambda: str(fake.content))
        self.module = u


class ForcedCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.content = Path(self.temp.name)/'Content'
        root = self.content/'DesertRocks'
        (root/'Maps').mkdir(parents=True)
        (root/'StaticMeshes').mkdir()
        for rel in ('Maps/Overview_DesertRocks_LOD.umap', 'StaticMeshes/SM_Rock_01.uasset', 'notes.txt'):
            (root/rel).write_bytes(b'x')
        (self.content/'AssetPackPipeline_Previews/abc').mkdir(parents=True)
        (self.content/'AssetPackPipeline_Previews/abc/Studio.umap').write_bytes(b'studio')
        self.manifest = {'profile': {'pack_id': 'DesertRocks', 'destination_root': '/Game/DesertRocks'}}

    def fake(self, current='/Game/DesertRocks/Maps/Overview_DesertRocks_LOD', presentation=True):
        f = FakeUnreal(self.content, {}, {}, current, presentation)
        u = f.module
        f.assets.update({
            '/Game/DesertRocks/Maps/Overview_DesertRocks_LOD.Overview_DesertRocks_LOD': u.World('/Game/DesertRocks/Maps/Overview_DesertRocks_LOD', 'map'),
            '/Game/DesertRocks/StaticMeshes/SM_Rock_01.SM_Rock_01': u.StaticMesh('/Game/DesertRocks/StaticMeshes/SM_Rock_01', 'mesh')})
        f.referencers = {'/Game/DesertRocks/StaticMeshes/SM_Rock_01': ['/Game/AssetPackPipeline_Previews/abc/Studio']}
        return f

    def run_with(self, fake, function, *args, **kwargs):
        with mock.patch.dict(sys.modules, {'unreal': fake.module}):
            from asset_pack_pipeline import cleanup, runtime
            with mock.patch.object(runtime, 'assert_editor_idle', lambda: None), \
                 mock.patch.object(runtime, 'owned', lambda obj, pack: True):
                return getattr(cleanup, function)(*args, **kwargs)

    def test_forced_plan_deletes_everything_with_reasons(self):
        fake = self.fake()
        proposal = self.run_with(fake, 'plan', self.manifest, imported=True, folder_scope=True, force=True)
        self.assertTrue(proposal['force'])
        self.assertEqual(proposal['delete_count'], 2)
        reasons = {row['id']: row['reason'] for row in proposal['assets']}
        self.assertEqual(reasons['/Game/DesertRocks/Maps/Overview_DesertRocks_LOD'], 'forced_current_map')
        self.assertEqual(reasons['/Game/DesertRocks/StaticMeshes/SM_Rock_01'], 'forced_external_references')
        self.assertEqual(proposal['presentation_map'], '/Game/Presentation/L_Presentation')
        # Conservative plan keeps both (current map, external referencer).
        safe = self.run_with(self.fake(), 'plan', self.manifest, imported=True, folder_scope=True)
        self.assertEqual(safe['delete_count'], 0)

    def test_forced_execute_order_backup_and_folder_removal(self):
        fake = self.fake()
        backup = Path(self.temp.name)/'backup'
        plan = self.run_with(fake, 'plan', self.manifest, imported=True, folder_scope=True, force=True)
        result = self.run_with(fake, 'execute', self.manifest, backup, imported=True, folder_scope=True, force=True,
                               expected=plan['delete_packages'])
        names = [c[0] for c in fake.calls]
        self.assertEqual(names[:2], ['load_level', 'delete_directory'])
        self.assertIn('save_dirty', names)
        self.assertTrue(result['passed'] and result['folder_removed'])
        self.assertFalse((self.content/'DesertRocks').exists())
        # Whole folder (incl. untracked notes.txt) and the outside referencer are backed up.
        self.assertTrue((backup/'DesertRocks/notes.txt').is_file())
        self.assertTrue((backup/'DesertRocks/StaticMeshes/SM_Rock_01.uasset').is_file())
        self.assertTrue((backup/'_external_referencers/AssetPackPipeline_Previews/abc/Studio.umap').is_file())
        self.assertEqual(result['saved_after_delete'], ['/Game/AssetPackPipeline_Previews/abc/Studio'])
        self.assertEqual(result['presentation_map'], '/Game/Presentation/L_Presentation')
        self.assertFalse(result['presentation_created'])

    def test_missing_presentation_is_created_from_template(self):
        fake = self.fake(presentation=False)
        with mock.patch.dict(sys.modules, {'unreal': fake.module}):
            from asset_pack_pipeline import cleanup
            fake.module.EditorAssetLibrary.does_asset_exist = staticmethod(lambda p: p == cleanup.PRESENTATION_TEMPLATE)
            path, created = cleanup.open_presentation('/Game/DesertRocks')
        self.assertEqual((path, created), ('/Game/Presentation/L_Presentation', True))
        self.assertEqual(fake.calls[0][0], 'new_level_from_template')
        self.assertEqual(fake.calls[-1], ('save_current_level',))

    def test_protected_folders_refused(self):
        for root in ('/Game/Presentation', '/Game/AssetPackPipeline'):
            with self.assertRaisesRegex(ValueError, 'Protected'):
                self.run_with(self.fake(), 'plan', {'profile': {'pack_id': 'X', 'destination_root': root}},
                              imported=True, force=True)


if __name__ == '__main__':
    unittest.main()
