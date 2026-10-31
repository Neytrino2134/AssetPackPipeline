import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import candidate


class CandidateTests(unittest.TestCase):
    def report(self):
        return {'manifest':{'assets':[{'id':x} for x in ('good','failed','readback')],
                            'excluded_sources':[{'id':'missing','stage':'source_preflight','reason':'Missing source'}]},
                'assets':[{'id':'good','status':'skipped','passed':True},
                          {'id':'failed','status':'failed','passed':False,'error':'Lost triangles'},
                          {'id':'readback','status':'passed','passed':True}]}

    def test_import_and_readback_failures_never_exclude_models(self):
        checked=[]
        accepted,excluded,checks=candidate.select(self.report(),lambda a:checked.append(a['id']),
            lambda a:{'id':a['id'],'passed':a['id']=='good'})
        self.assertEqual(accepted,['good','failed','readback'])
        self.assertEqual(checked,['good','readback'])
        self.assertEqual([r['id'] for r in excluded],['failed','readback'])
        self.assertTrue(all(row['blocking'] for row in excluded))

    def test_source_revision_change_blocks_candidate(self):
        def changed(asset):raise RuntimeError('Source changed')
        with self.assertRaisesRegex(RuntimeError,'Source changed'):
            candidate.select(self.report(),changed,lambda a:{'passed':True})

    def test_exception_in_readback_is_recorded(self):
        def broken(asset):raise ValueError('Missing mesh')
        accepted,excluded,_=candidate.select(self.report(),lambda a:None,broken)
        self.assertEqual(accepted,['good','failed','readback'])
        self.assertEqual(excluded[-1]['reason'],'Missing mesh')

    def test_strict_profile_and_nanite_compatible_stages(self):
        original={'nanite_enabled':True,'skip_invalid_sources':True,'asset_ids':['good','bad'],
                  'asset_overrides':{'good':{'roughness':.2},'bad':{'roughness':.8}},
                  'delivery':{'maps':'both'},'media':{'include_invalid':True,'lod_indices':[0,1]},
                  'previews':{'mode':'both'}}
        result=candidate.profile(original,['good'])
        self.assertNotIn('skip_invalid_sources',result)
        self.assertFalse(result['media']['include_invalid'])
        self.assertEqual(result['media']['lod_indices'],[0])
        self.assertEqual(result['delivery']['maps'],'overview')
        self.assertEqual(result['previews']['mode'],'overview')
        self.assertEqual(result['asset_ids'],['good'])
        self.assertEqual(set(result['asset_overrides']),{'good'})
        self.assertEqual(original['asset_ids'],['good','bad'])
        with self.assertRaisesRegex(ValueError,'No catalog assets'):candidate.profile(original,[])

    def test_quality_warnings_continue_with_all_models(self):
        report={'manifest':{'assets':[{'id':'quality_issue'}]},
                'assets':[{'id':'quality_issue','status':'passed','passed':True,'strict_passed':False}]}
        accepted,issues,checks=candidate.select(report,lambda a:None,lambda a:
            {'id':a['id'],'passed':True,'strict_passed':False,'warnings':[{'code':'TRIANGLES'}]})
        self.assertEqual(accepted,['quality_issue'])
        self.assertFalse(issues[0]['blocking'])
        self.assertFalse(checks[0]['strict_passed'])
