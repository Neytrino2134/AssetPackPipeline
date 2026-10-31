import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Content' / 'Python'))
from asset_pack_pipeline.window import profile_from_fields


class ProfileEditorTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((Path(__file__).resolve().parents[1] / 'Content' / 'Profiles' /
                                'profile.example.json').read_text())
        self.values = dict(self.base)
        self.values.update(source_root='D:/Exports', lod_screen_sizes='1, 0.5, 0.25, 0.125, 0.0625',
                           asset_ids='GraveStones_02_01, GraveStones_02_02', roughness='0.85')

    def test_roundtrip_preserves_unknown_settings(self):
        self.base['future_setting'] = {'version': 3}
        result = profile_from_fields(self.base, self.values)
        self.assertEqual(result['future_setting'], {'version': 3})
        self.assertEqual(result['asset_ids'], ['GraveStones_02_01', 'GraveStones_02_02'])
        self.assertEqual(self.base['asset_ids'], ['GraveStones_02_01'])

    def test_empty_selection_means_all(self):
        self.values['asset_ids'] = ' '
        self.assertNotIn('asset_ids', profile_from_fields(self.base, self.values))

    def test_validation_policy_roundtrip(self):
        result=profile_from_fields(self.base,dict(self.values,validation_policy='warn'))
        self.assertEqual(result['validation_policy'],'warn')
        result=profile_from_fields(result,dict(self.values,validation_policy='strict'))
        self.assertEqual(result['validation_policy'],'strict')

    def test_flythrough_fields_preserve_future_settings(self):
        base=dict(self.base,flythrough={'margin':1.3})
        fields=dict(self.values,flythrough_seconds='8',flythrough_fps='24',flythrough_width='1280',flythrough_height='720',
                    flythrough_yaw_start='-115',flythrough_yaw_end='-65',flythrough_pitch='25',flythrough_fov='50')
        result=profile_from_fields(base,fields)
        self.assertEqual(result['flythrough']['fps'],24)
        self.assertEqual(result['flythrough']['seconds'],8)
        self.assertEqual(result['flythrough']['margin'],1.3)

    def test_nanite_controls_roundtrip(self):
        result=profile_from_fields(self.base,dict(self.values,nanite_enabled=True,nanite_source='MID'))
        self.assertTrue(result['nanite_enabled'])
        self.assertEqual(result['nanite_source'],'MID')
        result=profile_from_fields(result,dict(self.values,nanite_enabled=False,nanite_source='AUTO'))
        self.assertFalse(result['nanite_enabled'])
        self.assertEqual(len(result['lod_screen_sizes']),5)

    def test_invalid_lod_values_rejected(self):
        for value in ['1, nan, 0.2', '1, 0.3, 0.5', '', '1, 0', '1, 1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                profile_from_fields(self.base, dict(self.values, lod_screen_sizes=value))

    def test_invalid_roughness_rejected(self):
        for value in ['nan', 'inf', '-0.1', '1.1', 'invalid']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                profile_from_fields(self.base, dict(self.values, roughness=value))

    def test_overview_controls_preserve_other_options(self):
        self.base['overview'] = {'map_name': 'MyOverview'}
        result = profile_from_fields(self.base, dict(self.values, overview_columns='2', overview_spacing='120',
                                                     overview_label_size='6', overview_require_valid=False))
        self.assertEqual(result['overview'], {'map_name': 'MyOverview', 'columns': 2, 'spacing': 120,
                                              'label_size': 6, 'require_valid_assets': False})

    def test_media_lod_series_can_be_set_and_cleared(self):
        fields=dict(self.values,media_yaw_angles='-60,120',media_pitch='15',media_fov='40',media_margin='1.18',
                    media_exposure_bias='0',media_key_intensity='3',media_sky_intensity='1.1',
                    media_lod_index='0',media_lod_indices='0,1,2,3,4',media_include_invalid=False)
        result=profile_from_fields(self.base,fields)
        self.assertEqual(result['media']['lod_indices'],[0,1,2,3,4])
        self.assertNotIn('lod_indices',profile_from_fields(result,dict(fields,media_lod_indices=''))['media'])


if __name__ == '__main__':
    unittest.main()
