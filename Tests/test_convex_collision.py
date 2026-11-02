import sys
import unittest
import types
from unittest.mock import patch,MagicMock
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import profiles,collision

class ConvexCollisionTests(unittest.TestCase):
    def test_convex_defaults_and_explicit_legacy_modes(self):
        base={'lod_screen_sizes':[1,.5]}
        self.assertEqual(profiles.effective(base,'Mesh')['collision'],'convex')
        for mode in ('none','box','convex'):
            self.assertEqual(profiles.effective(dict(base,collision=mode),'Mesh')['collision'],mode)
        self.assertEqual(profiles.convex_settings(base),{'hull_count':8,'max_hull_verts':16,'precision':100000})

    def test_invalid_convex_budgets_are_rejected(self):
        for config in ({'hull_count':0},{'hull_count':True},{'max_hull_verts':3},{'precision':-1},{'extra':1}):
            with self.assertRaises(ValueError):profiles.convex_settings({'convex_collision':config})

    def test_readback_counts_convex_even_when_primitive_api_returns_zero(self):
        aggregate=types.SimpleNamespace(get_editor_property=lambda name:[1]*8 if name=='convex_elems' else [])
        body=types.SimpleNamespace(get_editor_property=lambda name:aggregate if name=='agg_geom' else 'simple_and_complex')
        mesh=types.SimpleNamespace(get_editor_property=lambda name:body)
        subsystem=types.SimpleNamespace(get_simple_collision_count=lambda mesh:0,get_convex_collision_count=lambda mesh:8)
        unreal=types.SimpleNamespace(CollisionTraceFlag=types.SimpleNamespace(CTF_USE_SIMPLE_AND_COMPLEX='simple_and_complex'))
        with patch.dict(sys.modules,{'unreal':unreal}):
            result=collision.inspect(mesh,'convex',subsystem)
            self.assertEqual(result['simple_collision_count'],8);self.assertTrue(result['collision_count_ok'])

    def test_failed_decomposition_does_not_silently_substitute_a_box(self):
        mesh=MagicMock();subsystem=MagicMock();subsystem.set_convex_decomposition_collisions.return_value=False
        unreal=types.SimpleNamespace(CollisionTraceFlag=types.SimpleNamespace(CTF_USE_SIMPLE_AND_COMPLEX=1))
        with patch.dict(sys.modules,{'unreal':unreal}):
            with self.assertRaisesRegex(RuntimeError,'no box fallback'):collision.apply(mesh,{'collision':'convex'},subsystem)
        subsystem.add_simple_collisions.assert_not_called()
