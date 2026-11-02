import hashlib
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import updater,update_installer as installer

class UpdaterTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[3]/'Saved/UpdaterTests'
        base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.context={'engine_version':'5.8.4','build_id':'testbuild'}

    def archive(self,extra=None):
        path=self.root/'update.zip'
        with ZipFile(path,'w') as stream:
            stream.writestr('AssetPackPipeline/AssetPackPipeline.uplugin',json.dumps({'VersionName':'1.0.0'}))
            stream.writestr('AssetPackPipeline/Binaries/Win64/UnrealEditor.modules',json.dumps({'BuildId':'testbuild','Modules':{'AssetPackPipelineEditor':'Editor.dll'}}))
            stream.writestr('AssetPackPipeline/Binaries/Win64/Editor.dll',b'fake binary for filesystem test')
            if extra:stream.writestr(extra,b'invalid')
        self.metadata={'schema_version':1,'version':'1.0.0','platform':'Win64','engine_version':'5.8.4',
            'build_id':'testbuild','archive':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        return path

    def release(self):
        self.archive()
        prefix='https://github.com/'+updater.REPOSITORY+'/releases/download/v1.0.0/'
        return {'tag_name':'v1.0.0','assets':[
            {'name':updater.MANIFEST,'browser_download_url':prefix+updater.MANIFEST},
            {'name':'update.zip','browser_download_url':prefix+'update.zip','size':(self.root/'update.zip').stat().st_size}]}

    def test_semantic_comparison(self):
        self.assertGreater(installer.version('0.10.0'),installer.version('0.9.9'))
        for value in ('latest','1.0','1.0.0-beta'):
            with self.assertRaises(ValueError):installer.version(value)

    def test_check_requires_matching_engine_binary_build(self):
        release=self.release()
        with patch.object(updater,'read_url',side_effect=[json.dumps(release).encode(),json.dumps(self.metadata).encode()]):
            self.assertEqual(updater.check(self.context,updater.REPOSITORY)['status'],'available')
        self.context['build_id']='different'
        with patch.object(updater,'read_url',side_effect=[json.dumps(release).encode(),json.dumps(self.metadata).encode()]):
            self.assertEqual(updater.check(self.context,updater.REPOSITORY)['status'],'incompatible')

    def test_no_release_is_actionable(self):
        with patch.object(updater,'read_url',side_effect=urllib.error.HTTPError('https://api.github.com',404,'Not found',{},None)):
            self.assertEqual(updater.check(self.context,updater.REPOSITORY)['status'],'no_release')

    def test_manifest_and_download_stay_in_configured_repository(self):
        for url in ('http://github.com/a/b/releases/download/v1/x','https://evil.com/x','https://github.com/other/repo/releases/download/v1/a'):
            with self.assertRaises(ValueError):updater.release_url(url,updater.REPOSITORY)

    def test_bad_hash_rejected_without_extracting(self):
        archive=self.archive();self.metadata['sha256']='0'*64
        with self.assertRaises(ValueError):installer.unpack(archive,self.root/'payload',self.metadata)
        self.assertFalse((self.root/'payload').exists())

    def test_path_traversal_rejected_before_extracting(self):
        archive=self.archive('AssetPackPipeline/../../outside.py')
        with self.assertRaises(ValueError):installer.unpack(archive,self.root/'payload',self.metadata)
        self.assertFalse((self.root/'payload').exists())

    def test_windows_filename_alias_is_rejected(self):
        archive=self.archive('AssetPackPipeline/Content/test?.py')
        with self.assertRaises(ValueError):installer.unpack(archive,self.root/'payload',self.metadata)

    def test_git_metadata_in_zip_is_rejected(self):
        archive=self.archive('AssetPackPipeline/.git/config')
        with self.assertRaises(ValueError):installer.unpack(archive,self.root/'payload',self.metadata)

    def job(self):
        target=self.root/'Project/Plugins/AssetPackPipeline';target.mkdir(parents=True)
        (self.root/'Project/Project.uproject').write_text('{}')
        (target/'AssetPackPipeline.uplugin').write_text(json.dumps({'VersionName':'0.1.0'}))
        (target/'custom.txt').write_text('preserve in backup')
        archive=self.archive()
        root=self.root/'Project/Saved/AssetPackPipeline/Updates/jobs/test';root.mkdir(parents=True)
        import shutil
        shutil.copy2(archive,root/'update.zip')
        return {'target':str(target),'directory':str(root),'manifest':self.metadata}

    def test_installer_keeps_backup_and_never_touches_project_content(self):
        job=self.job();content=self.root/'Project/Content';content.mkdir();(content/'keep.txt').write_text('user')
        result=installer.install(job)
        self.assertEqual(result['status'],'installed')
        self.assertEqual((Path(result['backup'])/'custom.txt').read_text(),'preserve in backup')
        self.assertEqual((content/'keep.txt').read_text(),'user')
        self.assertEqual(json.loads((Path(job['target'])/'AssetPackPipeline.uplugin').read_text())['VersionName'],'1.0.0')

    def test_locked_destination_rolls_back(self):
        job=self.job();original=Path.rename
        def rename(source,target):
            if source.parent.name=='payload':raise PermissionError('simulated lock')
            return original(source,target)
        with patch.object(Path,'rename',rename):
            with self.assertRaises(PermissionError):installer.install(job)
        self.assertTrue((Path(job['target'])/'custom.txt').is_file())
        self.assertEqual(json.loads((Path(job['target'])/'AssetPackPipeline.uplugin').read_text())['VersionName'],'0.1.0')

    def test_developer_checkout_is_never_overwritten(self):
        job=self.job();(Path(job['target'])/'.git').mkdir()
        with self.assertRaises(ValueError):installer.install(job)
        self.assertTrue((Path(job['target'])/'custom.txt').is_file())

    def test_job_cannot_move_installation_outside_project_saved(self):
        job=self.job();job['directory']=str(self.root/'elsewhere')
        with self.assertRaises(ValueError):installer.install(job)

    def test_installation_never_downgrades(self):
        job=self.job();(Path(job['target'])/'AssetPackPipeline.uplugin').write_text(json.dumps({'VersionName':'2.0.0'}))
        with self.assertRaises(ValueError):installer.install(job)
