import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Content/Python'))
from asset_pack_pipeline import media, flythrough, overview


class FrontCameraTests(unittest.TestCase):
    def test_front_still_looks_down_negative_y(self):
        config = media.settings({'lod_screen_sizes': [1]})
        self.assertEqual(config['yaw_angles'][0], 90)
        frame = media.frame([-20, -10, 0], [20, 10, 60], 90, 15, 40, 16/9, 1.18)
        self.assertGreater(frame['position'][1], 0)
        self.assertAlmostEqual(math.degrees(math.atan2(-frame['position'][1], -frame['position'][0])), -90)

    def test_front_flythrough_and_legacy_presets(self):
        for config in ({}, {'yaw_start': -115, 'yaw_end': -65}):
            route = flythrough.poses([-20, -10, 0], [20, 10, 60], flythrough.settings({'flythrough': config}))
            self.assertTrue(all(p['position'][1] > 0 and -116 < p['rotation'][2] < -64 for p in route))
        self.assertEqual(media.settings({'lod_screen_sizes': [1], 'media': {'yaw_angles': [-60]}})['yaw_angles'], [90])

    def test_custom_rear_view_is_retained(self):
        self.assertEqual(media.settings({'lod_screen_sizes': [1], 'media': {'yaw_angles': [-90]}})['yaw_angles'], [-90])
