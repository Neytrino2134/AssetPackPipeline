import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import discovery,review_bundle


class ReviewBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/'image.png';self.path.write_bytes(b'test png')
        self.report={'kind':'individual_previews','status':'passed','run_id':'lod','output_directory':str(self.root),
            'manifest':{'profile':{'pack_id':'Pack'},'assets':[{'id':'Mesh'}]},
            'source_asset_checks':[{'id':'Mesh','passed':True,'strict_passed':False,'expected_triangles':[100],
                                    'triangles':[90],'warnings':[{'code':'TRIANGLES'}]}],
            'assets':[{'status':'passed','asset_id':'Mesh','lod_index':0,'yaw':-60,'output_path':str(self.path),
                       'sha256':discovery.digest(self.path)}]}

    def test_warning_model_retained_and_both_representations_copied(self):
        second=copy.deepcopy(self.report);second.update(run_id='nanite')
        second['manifest']['profile']['nanite_enabled']=True
        result=review_bundle.build([self.report,second],self.root/'review')
        self.assertEqual(result['model_count'],1)
        self.assertEqual(result['frame_count'],2)
        self.assertEqual(result['models_with_warnings'],['Mesh'])
        data=json.loads((self.root/'review/review.json').read_text())
        self.assertEqual([f['mode'] for f in data['frames']],['LOD','Nanite'])
        self.assertFalse(data['publication_ready'])

    def test_missing_model_and_changed_image_rejected(self):
        empty=copy.deepcopy(self.report);empty['manifest']['assets']=[]
        with self.assertRaisesRegex(ValueError,'requires catalog models'):
            review_bundle.build([empty],self.root/'empty')
        report=copy.deepcopy(self.report);report['manifest']['assets'].append({'id':'Missing'})
        with self.assertRaisesRegex(ValueError,'every catalog model'):
            review_bundle.build([report],self.root/'missing')
        self.path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            review_bundle.build([self.report],self.root/'changed')
