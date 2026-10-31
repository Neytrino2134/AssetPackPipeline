import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Content' / 'Python'))
from asset_pack_pipeline.overview import layout, settings


class OverviewLayoutTests(unittest.TestCase):
    def test_asymmetric_pivots_and_spacing(self):
        items = [{'id': str(i), 'min': [100-i, -10-i, -20], 'max': [150+i, 30+i, 80+i]}
                 for i in range(12)]
        result = layout(items, 4, 100)
        self.assertEqual(result['rows'], 3)
        for cell in result['cells']:
            self.assertAlmostEqual(cell['location'][2] + cell['min'][2], 0)
        for i, a in enumerate(result['cells']):
            for b in result['cells'][i+1:]:
                # Expanded footprint of each pair must have a separating axis.
                separated = any(a['max'][axis]+a['location'][axis]+99.9 <= b['min'][axis]+b['location'][axis]
                                or b['max'][axis]+b['location'][axis]+99.9 <= a['min'][axis]+a['location'][axis]
                                for axis in (0, 1))
                self.assertTrue(separated)

    def test_settings_paths_and_validation(self):
        profile = {'pack_id': 'Test', 'destination_root': '/Game/Test'}
        self.assertEqual(settings(profile)['map_path'], '/Game/Test/Maps/Overview_Test')
        self.assertEqual(settings(profile, True)['map_path'], '/Game/Test/Maps/LOD_Review_Test')
        for value in [0, 13, 2.5, True]:
            with self.assertRaises(ValueError):
                settings(dict(profile, overview={'columns': value}))
        for value in ['../Other', '/Game/Test', 'Карта']:
            with self.assertRaises(ValueError):
                settings(dict(profile, overview={'map_name': value}))

    def test_no_empty_map(self):
        with self.assertRaises(ValueError):
            layout([])


if __name__ == '__main__':
    unittest.main()
