"""Package only plugin source/content/docs, excluding caches and test host data."""
from pathlib import Path
import json
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import hashlib

parser = argparse.ArgumentParser()
parser.add_argument('--binary-source', type=Path)
parser.add_argument('--engine-version',default='5.8.4')
args = parser.parse_args()

project = Path(__file__).resolve().parents[3]
plugin = project / 'Plugins' / 'AssetPackPipeline'
version = json.loads((plugin / 'AssetPackPipeline.uplugin').read_text(encoding='utf-8-sig'))['VersionName']
output = project / 'Releases' / f'AssetPackPipeline-{version}.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in sorted(plugin.rglob('*')):
        if (path.is_file() and path.suffix.lower() != '.pdb'
                and not path.name.startswith('.env')
                and path.name not in ('ai-settings.json','active_profile.json')
                and not any(part in ('.git','__pycache__','Intermediate','Saved','DerivedDataCache','Releases','.vs') for part in path.relative_to(plugin).parts)):
            if args.binary_source and 'Binaries' in path.relative_to(plugin).parts:
                continue
            archive.write(path, path.relative_to(plugin.parent))
    if args.binary_source:
        assert (args.binary_source/'UnrealEditor-AssetPackPipelineEditor.dll').is_file()
        assert (args.binary_source/'UnrealEditor.modules').is_file()
        for file in args.binary_source.iterdir():
            if file.suffix in ('.dll','.modules'):
                archive.write(file, 'AssetPackPipeline/Binaries/Win64/'+file.name)
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert 'AssetPackPipeline/AssetPackPipeline.uplugin' in archive.namelist()
print(output)
with ZipFile(output) as archive:
    modules=json.loads(archive.read('AssetPackPipeline/Binaries/Win64/UnrealEditor.modules'))
metadata={'schema_version':1,'version':version,'engine_version':args.engine_version,'platform':'Win64',
          'build_id':modules['BuildId'],'archive':output.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
manifest=output.parent/'AssetPackPipeline-update.json'
manifest.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
print(manifest)
