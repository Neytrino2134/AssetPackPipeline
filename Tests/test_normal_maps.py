import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import discovery, profiles


class NormalMapConventionTests(unittest.TestCase):
    base = {'lod_screen_sizes': [1.0]}

    def test_default_is_auto_and_unlabeled_flips_green(self):
        # Blender/glTF normal maps are OpenGL (Y+); Unreal needs Flip Green Channel.
        profiles.validate_settings(self.base)
        self.assertTrue(profiles.flip_normal_green(self.base))
        self.assertTrue(profiles.flip_normal_green(self.base, {'normal_convention': 'OpenGL'}))
        self.assertFalse(profiles.flip_normal_green(self.base, {'normal_convention': 'DirectX'}))

    def test_manual_modes(self):
        for mode, flip in (('DirectX', False), ('OpenGL', True)):
            profile = dict(self.base, normal_map_convention=mode)
            profiles.validate_settings(profile)
            self.assertEqual(profiles.flip_normal_green(profile), flip)

    def test_unknown_convention_rejected(self):
        for value in ('opengl', 'GL', None):
            with self.assertRaisesRegex(ValueError, 'normal_map_convention'):
                profiles.validate_settings(dict(self.base, normal_map_convention=value))

    def test_example_profiles_are_valid(self):
        for path in (Path(__file__).resolve().parents[1]/'Content/Profiles').glob('*.example.json'):
            profile = json.loads(path.read_text(encoding='utf-8-sig'))
            self.assertIn(profile.get('normal_map_convention', 'Auto'), profiles.NORMAL_CONVENTIONS, path.name)


class SmartNormalSourceTests(unittest.TestCase):
    """discovery.normal_source: MeshInfo labels, file suffixes, unlabeled = OpenGL."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root/'FBX/Textures').mkdir(parents=True)
        self.profile = {'texture_directory': 'FBX/Textures'}

    def texture(self, name):
        (self.root/'FBX/Textures'/name).write_bytes(b'png')
        return 'FBX/Textures/'+name

    def pick(self, entries=(), **profile):
        path, convention, how = discovery.normal_source(dict(self.profile, **profile), self.root, self.root, 'Rock_01', list(entries))
        return path.name, convention, how

    def test_meshinfo_preferred_directx_skips_conversion(self):
        gl = self.texture('T_Rock_01_Normal.png'); dx = self.texture('T_Rock_01_Normal_DirectX.png')
        entry = {'textures': [{'role': 'Normal', 'path': gl},
                              {'role': 'Normal', 'path': dx, 'convention': 'DirectX', 'preferred': True,
                               'unreal': {'flip_green_channel': False}}]}
        self.assertEqual(self.pick([entry]), ('T_Rock_01_Normal_DirectX.png', 'DirectX', 'meshinfo'))

    def test_meshinfo_opengl_label_and_flip_hint(self):
        path = self.texture('T_Rock_01_Normal.png')
        self.assertEqual(self.pick([{'textures': [{'role': 'Normal', 'path': path, 'convention': 'OpenGL'}]}])[1:], ('OpenGL', 'meshinfo'))
        self.assertEqual(self.pick([{'textures': [{'role': 'Normal', 'path': path, 'unreal': {'flip_green_channel': True}}]}])[1:], ('OpenGL', 'meshinfo'))
        self.assertEqual(self.pick([{'textures': [{'role': 'normal', 'path': path}]}])[1:], ('OpenGL', 'assumed'))

    def test_old_catalog_uses_suffix_files(self):
        self.texture('T_Rock_01_Normal.png')
        self.assertEqual(self.pick(), ('T_Rock_01_Normal.png', 'OpenGL', 'assumed'))
        self.texture('T_Rock_01_Normal_GL.png')
        self.assertEqual(self.pick(), ('T_Rock_01_Normal_GL.png', 'OpenGL', 'suffix'))
        self.texture('T_Rock_01_Normal_DX.png')
        self.assertEqual(self.pick(), ('T_Rock_01_Normal_DX.png', 'DirectX', 'suffix'))

    def test_manual_mode_prefers_matching_file(self):
        self.texture('T_Rock_01_Normal.png'); self.texture('T_Rock_01_Normal_DirectX.png')
        self.assertEqual(self.pick(normal_map_convention='OpenGL'), ('T_Rock_01_Normal.png', 'OpenGL', 'manual'))
        self.assertEqual(self.pick(normal_map_convention='DirectX'), ('T_Rock_01_Normal_DirectX.png', 'DirectX', 'suffix'))

    def test_missing_normal_still_fails(self):
        with self.assertRaisesRegex(ValueError, 'Missing source'):
            self.pick()

    def test_catalog_relative_paths(self):
        # Older catalogs in FBX/ list files relative to that folder.
        (self.root/'FBX/a.fbx').write_bytes(b'x')
        self.assertEqual(discovery.catalog_source(self.root, self.root/'FBX', 'a.fbx'), self.root/'FBX/a.fbx')
        self.assertEqual(discovery.catalog_source(self.root, self.root/'FBX', 'FBX/a.fbx'), self.root/'FBX/a.fbx')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            discovery.catalog_source(self.root, self.root/'FBX', '../../outside.fbx')


class NormalSummaryTests(unittest.TestCase):
    def test_summary_counts(self):
        from asset_pack_pipeline import guided
        assets = [{'normal_convention': 'DirectX'}] * 2 + [{'normal_convention': 'OpenGL', 'normal_convention_source': 'assumed'}]
        self.assertEqual(guided.normal_summary(assets), 'Normal: 2 DirectX — без конвертации; 1 OpenGL — переворот канала G (без метки: 1)')
        self.assertEqual(guided.normal_summary([{'id': 'failed'}]), '')


if __name__ == '__main__':
    unittest.main()
