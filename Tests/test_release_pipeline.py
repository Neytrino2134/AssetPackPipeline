import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

spec=importlib.util.spec_from_file_location('release_pipeline',Path(__file__).resolve().parents[1]/'Tools/publish_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ReleaseTests(unittest.TestCase):
    def exercise(self,corrupt=False):
        base=Path(__file__).resolve().parents[3]/'Saved/ReleasePipelineTests';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            project=Path(temp);plugin=project/'Plugins/AssetPackPipeline';plugin.mkdir(parents=True)
            (project/'Saved').mkdir();(project/'Releases').mkdir()
            (plugin/'AssetPackPipeline.uplugin').write_text(json.dumps({'VersionName':'1.0.0'}))
            notes=plugin/'notes.md';notes.write_text('test notes')
            archive=project/'Releases/AssetPackPipeline-1.0.0.zip'
            with ZipFile(archive,'w') as stream:stream.writestr('AssetPackPipeline/AssetPackPipeline.uplugin',json.dumps({'VersionName':'1.0.0'}))
            manifest=archive.parent/'AssetPackPipeline-update.json'
            manifest.write_text(json.dumps({'version':'1.0.0','archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
            calls=[]
            def run(command,capture=False):
                command=[str(x) for x in command];calls.append(command)
                if command[:3]==['git','branch','--show-current']:return 'main'
                if command[:3]==['git','remote','get-url']:return 'https://github.com/'+release.REPO+'.git'
                if command[:3]==['git','rev-list','--count']:return '0'
                if command[:3]==['git','rev-parse','HEAD']:return 'a'*40
                if command[:3]==['gh','release','download']:
                    destination=Path(command[command.index('--dir')+1])
                    shutil.copy2(archive,destination/archive.name);shutil.copy2(manifest,destination/manifest.name)
                    if corrupt:(destination/archive.name).write_bytes(b'corrupted uploaded ZIP')
                return ''
            outputs=[types.SimpleNamespace(returncode=0),types.SimpleNamespace(returncode=1),types.SimpleNamespace(returncode=1)]
            with patch.object(release,'PLUGIN',plugin),patch.object(release,'PROJECT',project),patch.object(release,'run',run),patch.object(release,'gh_path',return_value='gh'),patch.object(release.subprocess,'run',side_effect=outputs),patch.object(sys,'argv',['release','--publish','--notes-file',str(notes),'--binary-source',str(project/'Binaries')]):
                if corrupt:
                    with self.assertRaises(ValueError):release.main()
                else:release.main()
            return calls

    def test_publish_only_after_uploaded_zip_download_and_verification(self):
        calls=self.exercise()
        create=next(i for i,c in enumerate(calls) if c[:3]==['gh','release','create'])
        download=next(i for i,c in enumerate(calls) if c[:3]==['gh','release','download'])
        publish=next(i for i,c in enumerate(calls) if c[:3]==['gh','release','edit'])
        self.assertLess(create,download);self.assertLess(download,publish)
        self.assertIn('--draft',calls[create])
        self.assertTrue(any(c[:3]==['git','push','--atomic'] for c in calls))

    def test_corrupt_uploaded_artifact_keeps_release_unpublished(self):
        calls=self.exercise(corrupt=True)
        self.assertFalse(any(c[:3]==['gh','release','edit'] for c in calls))
