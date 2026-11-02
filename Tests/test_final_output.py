import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline.final_output import export_renders, export_root


class FinalOutputTests(unittest.TestCase):
    def test_only_completed_outputs_are_copied_with_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'capture'; source.mkdir()
            (source/'overview.png').write_bytes(b'captured PNG')
            (source/'secret.txt').write_text('not a render')
            dest = root/'delivery'; dest.mkdir()
            report = {'status':'passed','run_id':'test123','output_directory':str(source),
                      'assets':[{'status':'passed','output_path':str(source/'overview.png')}]}
            result = export_renders([report], dest)
            self.assertEqual(result['count'], 1)
            with ZipFile(result['zip_path']) as archive:
                self.assertEqual(set(archive.namelist()), {'AssetPack_Renders/Overview_All_Meshes.png','AssetPack_Renders/manifest.json','AssetPack_Renders/sources.json'})
            self.assertTrue((source/'overview.png').is_file())

    def test_readable_launch_folders_never_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            stamp=datetime(2026,11,2,15,4,7)
            first=export_root(temp,stamp);second=export_root(temp,stamp)
            self.assertEqual(first.relative_to(temp).as_posix(),'FinalProject/2026-11-02_15-04-07')
            self.assertEqual(second.name,'2026-11-02_15-04-07_02')

    def test_variants_views_and_duplicate_overviews_share_one_flat_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'capture';source.mkdir();dest=root/'delivery';dest.mkdir()
            reports=[]
            for run,nanite in [('abc',False),('def',True)]:
                assets=[]
                for lod in ([0] if nanite else [0,2]):
                    file=source/f'{run}_{lod}.png';file.write_bytes(f'{run}_{lod}'.encode())
                    assets.append({'asset_id':'SomePack_01_01','lod_index':lod,'view_index':0,
                                   'representation':'Nanite' if nanite else 'LOD','status':'passed','output_path':str(file)})
                file=source/f'{run}_overview.png';file.write_bytes(b'overview')
                assets.append({'status':'passed','output_path':str(file)})
                reports.append({'status':'passed','run_id':run,'output_directory':str(source),'assets':assets})
            result=export_renders(reports,dest,'TestPack')
            folder=Path(result['directory'])
            self.assertEqual(folder.name,'TestPack_Renders')
            self.assertEqual({p.name for p in folder.glob('*.png')},{'MESH_LOW_01_01.png',
                'MESH_LOD2_01_01.png','MESH_MID_01_01.png',
                'Overview_All_Meshes.png','Overview_All_Meshes_02.png'})
            self.assertFalse(any(p.is_dir() for p in folder.iterdir()))
            with ZipFile(result['zip_path']) as archive:self.assertIsNone(archive.testzip())

    def test_pack_name_cannot_escape_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):export_renders([],temp,'../outside')

    def test_output_escape_is_rejected_before_copying(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = {'status':'passed','run_id':'test123','output_directory':str(root/'capture'),
                      'assets':[{'status':'passed','output_path':str(root/'outside.png')}]}
            with self.assertRaises(ValueError):
                export_renders([report], root/'delivery')
