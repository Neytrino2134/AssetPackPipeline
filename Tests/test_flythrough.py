import itertools
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import flythrough


class FlythroughTests(unittest.TestCase):
    def test_camera_yaw_wrap_does_not_add_a_full_rotation(self):
        config=flythrough.settings({'flythrough':{'seconds':2,'yaw_start':-30,'yaw_end':30}})
        route=flythrough.poses([-20,-10,0],[20,10,50],config)
        self.assertTrue(all(abs(a['rotation'][2]-b['rotation'][2])<5 for a,b in zip(route,route[1:])))

    def test_invalid_capture_settings_rejected(self):
        for values in ({'fps':True},{'fps':0},{'seconds':float('nan')},{'seconds':100},
                       {'width':100},{'yaw_start':0,'yaw_end':0},{'yaw_start':-170,'yaw_end':170}):
            with self.subTest(values=values),self.assertRaises(ValueError):flythrough.settings({'flythrough':values})

    def test_route_keeps_complete_bounds_inside_camera_and_has_no_skipped_frames(self):
        config=flythrough.settings({'flythrough':{'seconds':2,'fps':24}})
        lo=[-500,-240,-15];hi=[450,320,225]
        route=flythrough.poses(lo,hi,config)
        self.assertEqual([r['frame'] for r in route],list(range(48)))
        self.assertNotEqual(route[0]['position'],route[-1]['position'])
        center=[(a+b)/2 for a,b in zip(lo,hi)]
        for pose in route:
            _,pitch,yaw=map(math.radians,pose['rotation'])
            forward=[math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),math.sin(pitch)]
            right=[-math.sin(yaw),math.cos(yaw),0]
            up=[-math.sin(pitch)*math.cos(yaw),-math.sin(pitch)*math.sin(yaw),math.cos(pitch)]
            for corner in itertools.product(*zip(lo,hi)):
                d=[v-p for v,p in zip(corner,pose['position'])]
                dot=lambda axis:sum(a*b for a,b in zip(d,axis))
                self.assertGreater(dot(forward),0)
                self.assertLess(abs(dot(right)),dot(forward)*math.tan(math.radians(config['fov']/2)))
                self.assertLess(abs(dot(up)),dot(forward)*math.tan(math.radians(config['fov']/2))*config['height']/config['width'])
