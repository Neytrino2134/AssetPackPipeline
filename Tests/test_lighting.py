import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline.lighting import key_rotation

class LightingTests(unittest.TestCase):
    def test_key_illuminates_camera_side_for_all_orbit_views(self):
        for yaw in range(-180,181,15):
            angles=key_rotation(yaw)
            pitch=math.radians(angles['pitch']);azimuth=math.radians(angles['yaw'])
            ray=(math.cos(pitch)*math.cos(azimuth),math.cos(pitch)*math.sin(azimuth),math.sin(pitch))
            camera_forward=(math.cos(math.radians(yaw)),math.sin(math.radians(yaw)))
            self.assertLess(ray[2],0) # light descends onto the stage
            self.assertGreater(sum(a*b for a,b in zip(ray[:2],camera_forward)),.6)
        self.assertEqual(key_rotation(-90),{'pitch':225.,'yaw':60.,'roll':0.})
