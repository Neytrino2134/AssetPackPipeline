import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import render_views,render_quality,media
from asset_pack_pipeline import guided,final_output
import tempfile

class RenderViewsTests(unittest.TestCase):
    def test_lit_is_mandatory_and_duplicates_are_removed(self):
        self.assertEqual(render_views.settings(['wireframe','wireframe']),['lit','wireframe'])
        for value in ('wireframe',[False],['unknown']):
            with self.assertRaises(ValueError):render_views.settings(value)

    def test_each_lod_gets_primary_and_diagnostic_images(self):
        profile={'lod_screen_sizes':[1,.5],'previews':{'view_modes':['wireframe','collision_visibility','collision_pawn']},
                 'media':{'yaw_angles':[90],'lod_indices':[0,1]}}
        rows=media.frame_rows([{'id':'Mesh_01_01'}],[{'passed':True}],media.settings(profile),Path('out'),'Studio')
        self.assertEqual(len(rows),8)
        self.assertEqual(len({r['output_path'] for r in rows}),8)
        self.assertEqual([r['render_view'] for r in rows[:4]],list(render_views.MODES))
        self.assertTrue(rows[0]['output_path'].endswith('_Lit.png'))

    def test_enforce_lit_after_wireframe_and_restore_original_on_failure(self):
        class Automation:
            mode='wire';sets=[]
            @classmethod
            def get_editor_active_viewport_view_mode(cls):return cls.mode
            @classmethod
            def set_editor_active_viewport_view_mode(cls,mode):cls.mode=mode;cls.sets.append(mode)
        enum=types.SimpleNamespace(**{entry[0]:name for name,entry in render_views.MODES.items()})
        commands=[]
        system=types.SimpleNamespace(get_console_variable_int_value=lambda name:1,
                                     execute_console_command=lambda world,command:commands.append(command))
        unreal=types.SimpleNamespace(AutomationLibrary=Automation,ViewModeIndex=enum,SystemLibrary=system)
        with patch.dict(sys.modules,{'unreal':unreal}),patch.object(render_quality,'_world',return_value=None),patch.object(render_quality,'_saved',None),patch.object(render_quality,'_saved_throttle',None),patch.object(render_quality,'_saved_view_mode',None):
            render_quality.select_view('lit');self.assertEqual(Automation.mode,'lit')
            render_quality.select_view('collision_pawn');self.assertEqual(Automation.mode,'collision_pawn')
            render_quality.restore();self.assertEqual(Automation.mode,'wire')
            render_quality.restore();self.assertEqual(Automation.sets.count('wire'),1)
            self.assertEqual(commands,['r.Nanite 0','r.Nanite 1'])

    def test_final_export_retains_distinct_render_suffixes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();destination=root/'delivery';destination.mkdir()
            rows=render_views.expand([{'id':'overview','status':'passed','output_path':str(source/'overview.png')}],list(render_views.MODES))
            for row in rows:Path(row['output_path']).write_bytes(row['render_view'].encode())
            result=final_output.export_renders([{'status':'passed','run_id':'test123','output_directory':str(source),'assets':rows}],destination,'Pack')
            self.assertEqual({p.name for p in Path(result['directory']).glob('*.png')},
                {'Overview_All_Meshes'+render_views.suffix(mode)+'.png' for mode in render_views.MODES})

    def test_quick_presets_propagate_modes_to_both_representations(self):
        with tempfile.TemporaryDirectory() as temp:
            profiles,_=guided.prepare({'lod_screen_sizes':[1,.5]},temp,'TestPack','FBX',view_modes=['collision_pawn'])
            self.assertTrue(all(p['previews']['view_modes']==['lit','collision_pawn'] for p in profiles.values()))
