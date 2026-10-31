import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import delivery, discovery, profiles


class CombinedDeliveryTests(unittest.TestCase):
    def pair(self):
        result = []
        for variant in ('LOD', 'Nanite'):
            profile = {'pack_id': 'Example', 'source_root': 'sources', 'destination_root': '/Game/Example',
                       'mesh_subdirectory': variant, 'nanite_enabled': variant == 'Nanite',
                       'overview': {'map_name': 'Overview_' + variant}, 'delivery': {'maps': 'overview'}}
            result.append({'profile': profile, 'assets': [{'id': 'Model01', 'mesh_path': discovery.mesh_path(profile, 'Model01')}]})
        return result

    def test_two_representations_preserve_source_manifests(self):
        pair = self.pair(); before = copy.deepcopy(pair)
        result = delivery.combine(pair)
        self.assertEqual([a['representation'] for a in result['assets']], ['LOD', 'Nanite'])
        self.assertEqual(len({a['mesh_path'] for a in result['assets']}), 2)
        self.assertEqual(pair, before)

    def test_representation_names_are_explicit(self):
        pair = self.pair()
        self.assertTrue(pair[0]['assets'][0]['mesh_path'].endswith('/SM_Model01_LODS'))
        self.assertTrue(pair[1]['assets'][0]['mesh_path'].endswith('/SM_Model01_MID'))
        self.assertEqual(discovery.mesh_path({'destination_root': '/Game/Example'}, 'Model01'),
                         '/Game/Example/StaticMeshes/SM_Model01')

    def test_mismatch_or_overlap_is_rejected(self):
        for key, value in [('destination_root', '/Game/Other'), ('nanite_enabled', False),
                           ('mesh_subdirectory', 'LOD')]:
            pair = self.pair();pair[1]['profile'][key] = value
            pair[1]['assets'][0]['mesh_path'] = discovery.mesh_path(pair[1]['profile'], 'Model01')
            with self.subTest(key=key), self.assertRaises(ValueError):delivery.combine(pair)
        pair = self.pair();pair[1]['assets'] = []
        with self.assertRaises(ValueError):delivery.combine(pair)

    def test_invalid_mesh_subdirectory_is_rejected(self):
        for subdir in ('../Escape', '/Other', 'LOD/Nanite', None):
            with self.subTest(subdir=subdir), self.assertRaises(ValueError):
                profiles.validate_settings({'mesh_subdirectory': subdir})
