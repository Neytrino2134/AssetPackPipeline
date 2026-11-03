import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Content' / 'Python'))
from asset_pack_pipeline import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('a.fbx', 'b.fbx', 'T_Asset_01_BaseColor.png', 'T_Asset_01_Normal.png'):
            (self.root / name).write_bytes(b'test')
        self.catalog = {'schema_version': 2, 'meshes': [
            {'asset': 'Asset_01', 'name': f'SM_Asset_01_LOD{i}', 'role': 'LOD', 'lod_index': i,
             'triangles': 100 // (i+1), 'files': {'FBX': filename}}
            for i, filename in enumerate(('a.fbx', 'b.fbx'))]}
        self.profile = {'schema_version': 1, 'source_root': str(self.root), 'pack_id': 'Test',
                        'source_format': 'FBX', 'destination_root': '/Game/Test',
                        'texture_directory': '.', 'lod_screen_sizes': [1, 0.5], 'validation_policy':'strict'}

    def scan(self):
        (self.root / 'MeshInfo.json').write_text(json.dumps(self.catalog))
        (self.root / 'profile.json').write_text(json.dumps(self.profile))
        return discovery.scan(self.root / 'profile.json')

    def test_valid_chain_and_hashes(self):
        result = self.scan()
        self.assertEqual(result['expected']['meshes'], 1)
        self.assertEqual(result['assets'][0]['lods'][1]['index'], 1)
        self.assertEqual(len(result['source_hashes']), 4)

    def test_unreadable_source_keeps_catalog_row_and_other_asset(self):
        for entry in list(self.catalog['meshes']):
            row=copy.deepcopy(entry);row.update(asset='Asset_02',name=entry['name'].replace('01','02'))
            self.catalog['meshes'].append(row)
        for channel in ('BaseColor','Normal'):
            (self.root/f'T_Asset_02_{channel}.png').write_bytes(b'texture')
        self.catalog['meshes'][0]['files']['FBX']='missing.fbx'
        self.profile.update(skip_invalid_sources=True,validation_policy='warn')
        result=self.scan()
        self.assertEqual([a['id'] for a in result['assets']],['Asset_01','Asset_02'])
        self.assertEqual(result['excluded_sources'],[])
        self.assertIn('Missing source',result['assets'][0]['preflight_error'])
        self.assertEqual(len(result['source_hashes']),4)
        self.assertFalse(any('missing.fbx' in p for p in result['source_hashes']))
        self.profile['validation_policy']='strict'
        with self.assertRaisesRegex(ValueError,'Missing source'):self.scan()

    def test_asset_id_may_start_with_digit(self):
        asset = '52_Ruini_Skali_Pesok_01_01'
        for entry in self.catalog['meshes']:
            entry.update(asset=asset, name=entry['name'].replace('Asset_01', asset))
        for channel in ('BaseColor', 'Normal'):
            (self.root/f'T_{asset}_{channel}.png').write_bytes(b'texture')
        result = self.scan()
        self.assertEqual(result['assets'][0]['id'], asset)
        self.assertTrue(result['assets'][0]['mesh_path'].endswith('/SM_'+asset))
        for bad in ('_Leading', 'Ruины_01', 'a-b'):
            for entry in self.catalog['meshes']:
                entry['asset'] = bad
            with self.assertRaisesRegex(ValueError, 'Invalid asset id'):
                self.scan()

    def test_convex_collision_is_accepted_by_scan(self):
        # Quick start / Master write collision=convex; scan must not reject it.
        self.profile.update(collision='convex',convex_collision={'hull_count':8})
        self.assertTrue(self.scan()['assets'])

    def test_skip_never_bypasses_bad_global_settings_or_all_invalid(self):
        self.profile['skip_invalid_sources']='yes'
        with self.assertRaisesRegex(ValueError,'boolean'):self.scan()
        self.profile.update(skip_invalid_sources=True,validation_policy='warn',collision='invalid')
        with self.assertRaisesRegex(ValueError,'collision'):self.scan()
        self.profile.update(collision='none')
        (self.root/'a.fbx').unlink()
        result=self.scan()
        self.assertEqual(len(result['assets']),1)
        self.assertIn('Missing source',result['assets'][0]['preflight_error'])

    def add_detail(self, kind, role='HIGH'):
        entry={'asset':'Asset_01','name':'SM_Asset_01_'+kind,'role':role,'lod_index':None,
               'triangles':7000,'files':{'FBX':'SM_Asset_01_'+kind+'.fbx'}}
        (self.root/entry['files']['FBX']).write_bytes(b'fixture')
        self.catalog['meshes'].append(entry)
        return entry

    def test_nanite_mid_legacy_role_and_effective_single_source(self):
        self.add_detail('MID')
        self.profile.update(nanite_enabled=True)
        result=self.scan()
        asset=result['assets'][0]
        self.assertEqual(result['expected']['lods_per_mesh'],1)
        self.assertEqual(asset['source_kind'],'MID')
        self.assertEqual(asset['lods'][0]['index'],0)
        self.assertTrue(asset['lods'][0]['file'].endswith('_MID.fbx'))
        self.assertEqual(asset['effective_settings']['lod_screen_sizes'],[1.0])

    def test_nanite_auto_prefers_mid_and_explicit_high_selects_high(self):
        self.add_detail('HIGH');self.add_detail('MID')
        self.profile.update(nanite_enabled=True)
        self.assertEqual(self.scan()['assets'][0]['source_kind'],'MID')
        self.profile['nanite_source']='HIGH'
        self.assertEqual(self.scan()['assets'][0]['source_kind'],'HIGH')

    def test_nanite_high_only_and_no_conventional_lods(self):
        self.catalog['meshes']=[]
        self.add_detail('HIGH')
        self.profile.update(nanite_enabled=True)
        self.assertEqual(self.scan()['assets'][0]['source_kind'],'HIGH')
        self.profile.update(nanite_enabled=False,validation_policy='warn')
        result=self.scan()
        self.assertEqual([a['id'] for a in result['assets']],['Asset_01'])
        self.assertIn('LOD indices',result['assets'][0]['preflight_error'])

    def test_nanite_missing_explicit_source_and_no_lod_fallback(self):
        self.profile.update(nanite_enabled=True)
        with self.assertRaisesRegex(ValueError,'expected one catalog source'):self.scan()
        self.add_detail('MID');self.profile['nanite_source']='HIGH'
        with self.assertRaisesRegex(ValueError,'Nanite HIGH'):self.scan()

    def test_nanite_ambiguous_source_rejected(self):
        self.add_detail('MID');self.add_detail('MID')
        self.profile.update(nanite_enabled=True)
        with self.assertRaisesRegex(ValueError,'found 2'):self.scan()

    def test_nanite_suffix_disagreement_rejected(self):
        entry=self.add_detail('MID');entry['name']='SM_Asset_01_HIGH'
        self.profile.update(nanite_enabled=True)
        with self.assertRaisesRegex(ValueError,'suffix disagree'):self.scan()

    def test_conventional_ignores_detail_sources(self):
        self.add_detail('MID');self.add_detail('HIGH')
        asset=self.scan()['assets'][0]
        self.assertEqual(asset['source_kind'],'LOD')
        self.assertEqual(len(asset['lods']),2)

    def test_nanite_override_selection_and_invalid_modes(self):
        self.add_detail('MID');self.add_detail('HIGH')
        self.profile.update(nanite_enabled=True,asset_overrides={'Asset_01':{'nanite_source':'HIGH'}})
        self.assertEqual(self.scan()['assets'][0]['source_kind'],'HIGH')
        self.profile['nanite_enabled']='true'
        with self.assertRaisesRegex(ValueError,'boolean'):self.scan()
        self.profile.update(nanite_enabled=True,nanite_source='LOD0')
        with self.assertRaisesRegex(ValueError,'AUTO, MID or HIGH'):self.scan()

    def test_duplicate_lod(self):
        self.catalog['meshes'].append(copy.deepcopy(self.catalog['meshes'][0]))
        with self.assertRaisesRegex(ValueError, 'LOD indices'):
            self.scan()

    def test_path_escape(self):
        self.catalog['meshes'][0]['files']['FBX'] = '../outside.fbx'
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.scan()

    def test_missing_texture(self):
        (self.root / 'T_Asset_01_Normal.png').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing source'):
            self.scan()

    def test_invalid_thresholds(self):
        self.profile['lod_screen_sizes'] = [0.5, 1]
        with self.assertRaisesRegex(ValueError, 'decrease'):
            self.scan()

    def test_invalid_glb(self):
        with self.assertRaisesRegex(ValueError, 'Truncated GLB'):
            discovery.glb_document(self.root / 'a.fbx')

    def test_overrides_resolve_and_orm_is_contained_hashed(self):
        (self.root/'orm_Asset_01.png').write_bytes(b'orm')
        self.profile.update(orm_texture='orm_{asset_id}.png', asset_overrides={
            'Asset_01': {'roughness': .3, 'normal_strength': 2, 'collision': 'box', 'lod_screen_sizes': [1, .25]}})
        result = self.scan()
        self.assertEqual(result['assets'][0]['effective_settings']['roughness'], .3)
        self.assertEqual(result['assets'][0]['effective_settings']['lod_screen_sizes'], [1, .25])
        self.assertIn('ORM', result['assets'][0]['textures'])
        self.assertEqual(result['expected']['textures'], 4)
        self.assertEqual(len(result['source_hashes']), 5)
        self.profile['asset_overrides']['Asset_01']['orm_texture'] = ''
        self.assertNotIn('ORM', self.scan()['assets'][0]['textures'])

    def test_invalid_overrides_rejected(self):
        for overrides in ({'Unknown': {}}, {'Asset_01': {'lod_screen_sizes': [1]}},
                          {'Asset_01': {'metallic': float('nan')}}, {'Asset_01': {'remove_degenerates': 'false'}},
                          {'Asset_01': {'destination_root': '/Game/Other'}}, {'Asset_01': {'uv_scale': 0}},
                          {'Asset_01': {'orm_texture': '../outside.png'}}):
            self.profile['asset_overrides'] = overrides
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.scan()


if __name__ == '__main__':
    unittest.main()
