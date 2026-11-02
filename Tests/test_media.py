import itertools
import math
import sys
import unittest
import tempfile
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import media,delivery,overview,review


class MediaTests(unittest.TestCase):
    def test_nanite_uses_one_representation_and_rejects_forced_lod_review(self):
        profile={'pack_id':'Pack','destination_root':'/Game/Pack','nanite_enabled':True,'lod_screen_sizes':[1,.5,.25]}
        self.assertEqual(media.settings(profile)['lod_indices'],[0])
        with self.assertRaisesRegex(ValueError,'valid LOD indices'):
            media.settings(dict(profile,media={'lod_indices':[0,1]}))
        with self.assertRaisesRegex(ValueError,'Nanite OFF'):overview.settings(profile,True)
        self.assertEqual(overview.settings(profile)['map_path'],'/Game/Pack/Maps/Overview_Pack')
    def test_camera_contains_all_bounds_corners(self):
        for yaw,pitch,aspect in itertools.product([-90,-60,45,120,180],[0,15,65],[16/9,1,9/16]):
            frame=media.frame([-20,-8,0],[20,8,100],yaw,pitch,40,aspect,1.18)
            az,el=math.radians(yaw),math.radians(pitch)
            forward=[-math.cos(el)*math.cos(az),-math.cos(el)*math.sin(az),-math.sin(el)]
            right=[-math.sin(az),math.cos(az),0]
            up=[-math.sin(el)*math.cos(az),-math.sin(el)*math.sin(az),math.cos(el)]
            for corner in itertools.product([-20,20],[-8,8],[0,100]):
                delta=[v-p for v,p in zip(corner,frame['position'])]
                dot=lambda vector:sum(a*b for a,b in zip(delta,vector))
                self.assertGreater(dot(forward),0)
                self.assertLess(abs(dot(right)),dot(forward)*math.tan(math.radians(20)))
                self.assertLess(abs(dot(up)),dot(forward)*math.tan(math.radians(20))/aspect)

    def test_media_settings_reject_bad_values(self):
        for item in ({'yaw_angles':[]},{'yaw_angles':[float('nan')]},{'fov':0},{'include_invalid':'yes'},{'lod_index':5},
                     {'lod_indices':[]},{'lod_indices':[0,0]},{'lod_indices':[True]},{'lod_indices':[5]},{'lod_indices':'all'}):
            with self.assertRaises(ValueError):media.settings({'lod_screen_sizes':[1,.5,.25,.125,.0625],'media':item})

    def test_lod_series_has_unique_frames_and_legacy_single_lod_fallback(self):
        profile={'lod_screen_sizes':[1,.5,.25,.125,.0625],'media':{'yaw_angles':[-60,120],'lod_indices':[0,1,2,3,4]}}
        rows=media.frame_rows([{'id':'Mesh'}],[{'passed':True}],media.settings(profile),Path('out'),'Studio')
        self.assertEqual(len({r['output_path'] for r in rows}),10)
        self.assertEqual([r['lod_index'] for r in rows[:5]],[0,1,2,3,4])
        config=media.settings({'lod_screen_sizes':[1,.5],'media':{'lod_index':1}})
        self.assertEqual(config['lod_indices'],[1])
        self.assertTrue(media.frame_rows([{'id':'Mesh'}],[{'passed':False}],config,Path('out'),'Studio')[0]['output_path'].endswith('Mesh_diagnostic_v00_Lit.png'))

    def test_review_only_includes_completed_local_frames_and_escapes_names(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'image.png';path.write_bytes(b'image')
            report={'run_id':'test','status':'passed','output_directory':folder,'assets':[
                {'status':'passed','output_path':str(path),'asset_id':'</script><fake>','yaw':0,'lod_index':0},
                {'status':'cancelled','output_path':'missing.png'}]}
            result=review.write(report)
            text=Path(result).read_text(encoding='utf-8')
            self.assertNotIn('</script><fake>',text)
            self.assertIn('&lt;fake&gt;',text)
            self.assertEqual(len(json.loads((Path(folder)/'review.json').read_text())['frames']),1)
            report['assets'][0]['output_path']=str(Path(folder).parent/'foreign.png')
            with self.assertRaises(ValueError):review.write(report)

    def test_project_name_matches_content_root_without_renaming_packages(self):
        self.assertEqual(delivery.project_name({'pack_id':'Pack','destination_root':'/Game/TestRoot/GLB'}),'TestRoot')

    def test_delivery_ignores_empty_editor_folders_but_rejects_foreign_files(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder)/'Pack';project.mkdir()
            (project/'Content/Pack').mkdir(parents=True)
            (project/'Content/Pack/mesh.uasset').write_bytes(b'test')
            (project/'Content/Developers').mkdir()
            descriptor=project/'Pack.uproject';descriptor.write_text(json.dumps({}))
            report={'project_directory':str(project),'project_path':str(descriptor),'file_hashes':{}}
            self.assertTrue(delivery.verify_files(report))
            (project/'Content/Developers/foreign.uasset').write_bytes(b'foreign')
            with self.assertRaises(RuntimeError):delivery.verify_files(report)

    def test_studio_override_cannot_target_foreign_maps(self):
        with self.assertRaises(ValueError):
            overview.settings({'pack_id':'Pack','destination_root':'/Game/Pack','overview':{'map_path_override':'/Game/UserMap'}})
