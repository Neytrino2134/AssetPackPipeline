import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import auto_lod


class AutoLODTests(unittest.TestCase):
    def test_boundary_samples_cross_each_saved_threshold(self):
        rows=auto_lod.samples([1,.5,.25,.125,.0625])
        self.assertEqual([a['expected_lod'] for a in rows],[0,1,1,2,2,3,3,4])
        self.assertAlmostEqual(rows[0]['target_screen_size'],.55)
        self.assertAlmostEqual(rows[-1]['target_screen_size'],.05625)

    def test_non_geometric_threshold_spacing_uses_actual_walk(self):
        self.assertEqual(auto_lod.samples([1,.5,.49,.01])[1]['expected_lod'],2)
        with self.assertRaises(ValueError):auto_lod.samples([1,.5,.6])

    def test_distance_inverts_engine_projected_sphere_diameter(self):
        for size in (.55,.45,.1375,.05625):
            self.assertAlmostEqual((16/9)*60/auto_lod.distance(60,size),size)

    def test_frame_plan_calibrates_once(self):
        checks=[{'lod_count':5,'screen_sizes':[1,.5,.25,.125,.0625]}]*2
        rows=auto_lod.rows([{'id':'A'},{'id':'B'}],checks,{'yaw_angles':[-60]},'out','Studio')
        self.assertEqual(len(rows),21)
        self.assertEqual(sum(bool(r.get('calibration')) for r in rows),5)
        self.assertEqual(len({r['output_path'] for r in rows}),len(rows))

    def test_renderer_csv_filters_resource_pass_and_culled_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'stats.csv'
            path.write_text('Pass,ResourceName,VisibleInstances,LODIndex,PrimitiveCount\n'
                'ShadowDepth,SM_A,1,0,2900\nBasePass,SM_A,1,2,1000\nBasePass,SM_B,1,0,200\nBasePass,SM_A,0,0,2900\n')
            result=auto_lod.inspect_stats(path,'A',2,[2900,1500,1000,500,250])
            self.assertEqual(result['observed_lod'],2)
            self.assertEqual(result['observed_triangles'],1000)
            with self.assertRaises(RuntimeError):auto_lod.inspect_stats(path,'A',1,[2900,1500,1000,500,250])
            with self.assertRaises(RuntimeError):auto_lod.inspect_stats(path,'Missing',0,[100])

    def test_ambiguous_actual_lods_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'stats.csv'
            path.write_text('Pass,ResourceName,VisibleInstances,LODIndex,PrimitiveCount\nBasePass,SM_A,1,0,2900\nBasePass,SM_A,1,1,1500\n')
            with self.assertRaises(RuntimeError):auto_lod.inspect_stats(path,'A',0,[2900,1500])

    def test_multiple_sections_are_summed_but_duplicate_draws_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'stats.csv'
            text='Pass,ResourceName,VisibleInstances,LODIndex,SegmentIndex,PrimitiveCount\nBasePass,SM_A,1,0,0,1400\nBasePass,SM_A,1,0,1,1500\n'
            path.write_text(text)
            self.assertEqual(auto_lod.inspect_stats(path,'A',0,[2900])['observed_triangles'],2900)
            path.write_text(text+'BasePass,SM_A,1,0,1,1500\n')
            with self.assertRaises(RuntimeError):auto_lod.inspect_stats(path,'A',0,[2900])
