import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Content/Python'))
from asset_pack_pipeline.previews import settings, inspect_png


class PreviewTests(unittest.TestCase):
    def test_invalid_budget_modes_and_times(self):
        for overrides in ({'width': True}, {'height': 100}, {'width': 8192, 'height': 8192},
                          {'mode': 'all'}, {'camera': '../camera'}, {'warmup_seconds': 'nan'},
                          {'timeout_seconds': 0}, {'output_directory': 'relative/path'}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                settings({'previews': overrides})

    def test_png_dimensions_and_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'preview.png'
            path.write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I', 13)+b'IHDR'+struct.pack('>II', 640, 360)+bytes(9))
            result = inspect_png(path, 640, 360)
            self.assertEqual(len(result['sha256']), 64)
            with self.assertRaises(RuntimeError):
                inspect_png(path, 1920, 1080)
            path.write_bytes(b'not a png')
            with self.assertRaises(RuntimeError):
                inspect_png(path, 640, 360)
