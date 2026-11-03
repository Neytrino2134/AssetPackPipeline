import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import profiles


class NormalMapConventionTests(unittest.TestCase):
    base = {'lod_screen_sizes': [1.0]}

    def test_default_is_opengl_and_flips_green(self):
        # Blender/glTF normal maps are OpenGL (Y+); Unreal needs Flip Green Channel.
        self.assertTrue(profiles.flip_normal_green(self.base))
        profiles.validate_settings(self.base)

    def test_directx_keeps_green(self):
        profile = dict(self.base, normal_map_convention='DirectX')
        profiles.validate_settings(profile)
        self.assertFalse(profiles.flip_normal_green(profile))

    def test_unknown_convention_rejected(self):
        for value in ('opengl', 'GL', None):
            with self.assertRaisesRegex(ValueError, 'normal_map_convention'):
                profiles.validate_settings(dict(self.base, normal_map_convention=value))

    def test_example_profiles_are_valid(self):
        import json
        for path in (Path(__file__).resolve().parents[1]/'Content/Profiles').glob('*.example.json'):
            profile = json.loads(path.read_text(encoding='utf-8-sig'))
            self.assertIn(profile.get('normal_map_convention', 'OpenGL'), profiles.NORMAL_CONVENTIONS, path.name)


if __name__ == '__main__':
    unittest.main()
