import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline.native_profile import form_values, apply_fields, edit_override


class NativeProfileTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((Path(__file__).resolve().parents[1]/'Content/Profiles/profile.example.json').read_text())

    def test_forms_roundtrip_preserve_unknown_fields(self):
        self.base['future_setting'] = {'keep': True}
        result = apply_fields(self.base, form_values(self.base))
        self.assertEqual(result, self.base)

    def test_empty_ids_include_all_models(self):
        values = form_values(self.base)
        values['asset_ids'] = ''
        self.assertNotIn('asset_ids', apply_fields(self.base,values))

    def test_invalid_settings_rejected(self):
        for key,value in (('roughness','nan'),('lod_screen_sizes','1, .2, .5'),
                          ('destination_root','/Game'),('preview_width','10'),('media_fov','200')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                apply_fields(self.base,dict(form_values(self.base),**{key:value}))

    def test_changes_do_not_mutate_original_profile(self):
        values = form_values(self.base)
        values.update(roughness='0.3',overview_columns='6')
        result = apply_fields(self.base,values)
        self.assertEqual(result['roughness'], .3)
        self.assertEqual(result['overview']['columns'], 6)
        self.assertEqual(self.base['overview']['columns'], 4)

    def test_override_inheritance_disable_orm_and_copy(self):
        result = edit_override(self.base,'Mesh01',{'roughness':'0.3','collision':'inherit','orm_texture':'-'})
        self.assertEqual(result['asset_overrides']['Mesh01'],{'roughness':.3,'orm_texture':''})
        self.assertNotIn('Mesh01',self.base['asset_overrides'])
        self.assertNotIn('Mesh01', edit_override(result,'Mesh01',{},True)['asset_overrides'])

    def test_override_rejects_unknown_keys_bad_bool_and_lod_count(self):
        for values in ({'python':'bad'},{'remove_degenerates':'yes'},{'lod_screen_sizes':'1,.5'},{'metallic':'2'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                edit_override(self.base,'Mesh01',values)

    def test_flythrough_form_validates_sweep_and_duration(self):
        result=apply_fields(self.base,{'flythrough_seconds':'4','flythrough_fps':'24',
                                     'flythrough_yaw_start':'65','flythrough_yaw_end':'115'})
        self.assertEqual(result['flythrough']['seconds'],4)
        with self.assertRaises(ValueError):
            apply_fields(result,{'flythrough_yaw_end':'65'})
        with self.assertRaises(ValueError):
            apply_fields(result,{'flythrough_seconds':'100'})
