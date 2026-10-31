import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline.final_output import export_renders


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
                self.assertEqual(set(archive.namelist()), {'Renders/test123/overview.png','Renders/manifest.json'})
            self.assertTrue((source/'overview.png').is_file())

    def test_output_escape_is_rejected_before_copying(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = {'status':'passed','run_id':'test123','output_directory':str(root/'capture'),
                      'assets':[{'status':'passed','output_path':str(root/'outside.png')}]}
            with self.assertRaises(ValueError):
                export_renders([report], root/'delivery')
