"""Prepare or publish a verified installable release; requires no tokens in files."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

PLUGIN=Path(__file__).resolve().parents[1]
PROJECT=PLUGIN.parents[1]
REPO='Neytrino2134/AssetPackPipeline'

def run(command,capture=False):
    result=subprocess.run([str(x) for x in command],cwd=PLUGIN,check=True,
        stdout=subprocess.PIPE if capture else None,text=True,encoding='utf-8')
    return result.stdout.strip() if capture else ''

def gh_path():
    installed=shutil.which('gh')
    local=PROJECT/'Saved/ReleaseTools/gh.exe'
    if installed:return installed
    if local.is_file():return str(local)
    raise RuntimeError('GitHub CLI is missing. Install the official CLI or set it up in Saved/ReleaseTools/gh.exe.')

def validate_bundle(archive,manifest,expected):
    data=json.loads(Path(manifest).read_text(encoding='utf-8'))
    if data['version']!=expected or data['archive']!=Path(archive).name:raise ValueError('Release manifest version/name mismatch')
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest()!=data['sha256']:raise ValueError('Release SHA256 mismatch')
    with ZipFile(archive) as stream:
        if stream.testzip():raise ValueError('Corrupt release ZIP')
        descriptor=json.loads(stream.read('AssetPackPipeline/AssetPackPipeline.uplugin'))
        if descriptor['VersionName']!=expected:raise ValueError('ZIP descriptor version mismatch')
        if any('/.git/' in name or '/__pycache__/' in name for name in stream.namelist()):raise ValueError('Unexpected files in ZIP')
    return data

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish',action='store_true',help='Push main/tag and publish Release. Without it only prepare local artifacts.')
    parser.add_argument('--engine',type=Path,default=Path(r'C:\Program Files\Epic Games\UE_5.8'))
    parser.add_argument('--engine-version',default='5.8.4')
    parser.add_argument('--binary-source',type=Path,help='Explicitly reuse a previously verified compatible build; default is a fresh BuildPlugin.')
    parser.add_argument('--notes-file',type=Path,required=True)
    args=parser.parse_args()
    descriptor=json.loads((PLUGIN/'AssetPackPipeline.uplugin').read_text(encoding='utf-8-sig'))
    version=descriptor['VersionName']
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('A stable semantic version is required')
    tag='v'+version
    if not args.notes_file.resolve().is_file():raise ValueError('Release notes file is missing')
    if run(['git','branch','--show-current'],True)!='main':raise ValueError('Release must be made from main')
    if run(['git','status','--porcelain'],True):raise ValueError('Commit the reviewed changes, including logo/resources, before releasing')
    origin=run(['git','remote','get-url','origin'],True).removesuffix('.git')
    if origin not in ('https://github.com/'+REPO,'git@github.com:'+REPO):raise ValueError('Unexpected origin repository')
    cli=None
    if args.publish:
        cli=gh_path()
        auth=subprocess.run([cli,'auth','status','--hostname','github.com'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if auth.returncode:raise RuntimeError('One-time GitHub login required: run Tools/GitHub-Login.cmd. Never paste a token in chat.')
        run(['git','fetch','origin','main'])
        if run(['git','rev-list','--count','HEAD..origin/main'],True)!='0':raise ValueError('Remote main is ahead/diverged; reconcile before release')
    run([sys.executable,'-m','unittest','discover','-s','Tests'])
    binary=args.binary_source
    if binary is None:
        build=PROJECT/'Saved/ReleaseBuilds'/version
        if not build.resolve().is_relative_to((PROJECT/'Saved').resolve()):raise ValueError('Build path escaped Saved')
        run([args.engine/'Engine/Build/BatchFiles/RunUAT.bat','BuildPlugin',
             '-Plugin='+str(PLUGIN/'AssetPackPipeline.uplugin'),'-Package='+str(build),'-TargetPlatforms=Win64'])
        binary=build/'Binaries/Win64'
    run([sys.executable,PLUGIN/'Tools/package_pipeline.py','--binary-source',binary,'--engine-version',args.engine_version])
    archive=PROJECT/'Releases'/f'AssetPackPipeline-{version}.zip'
    manifest=archive.parent/'AssetPackPipeline-update.json'
    validate_bundle(archive,manifest,version)
    if not args.publish:
        print('Prepared locally. Add --publish after requesting release publication.');return
    head=run(['git','rev-parse','HEAD'],True)
    local=subprocess.run(['git','rev-parse','--verify','refs/tags/'+tag],cwd=PLUGIN,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    if local.returncode==0 and run(['git','rev-list','-n','1',tag],True)!=head:raise ValueError('Existing tag points elsewhere; increase the version, never move a released tag')
    if local.returncode:run(['git','tag',tag])
    run(['git','push','--atomic','origin','main',tag])
    command=[cli,'release','view',tag,'--repo',REPO,'--json','isDraft,url']
    existing=subprocess.run(command,cwd=PLUGIN,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
    if existing.returncode==0:
        raise RuntimeError('Release already exists. Inspect it and resume explicitly; published assets are never overwritten automatically.')
    # A draft is kept private until both assets have been downloaded and verified.
    run([cli,'release','create',tag,str(archive),str(manifest),'--repo',REPO,'--verify-tag','--draft',
         '--title','MESHFLOW Asset Pack Pipeline '+tag,'--notes-file',args.notes_file.resolve()])
    with tempfile.TemporaryDirectory(dir=PROJECT/'Saved') as folder:
        run([cli,'release','download',tag,'--repo',REPO,'--dir',folder,'--pattern',archive.name,'--pattern',manifest.name])
        validate_bundle(Path(folder)/archive.name,Path(folder)/manifest.name,version)
        if hashlib.sha256((Path(folder)/archive.name).read_bytes()).digest()!=hashlib.sha256(archive.read_bytes()).digest():
            raise ValueError('Uploaded ZIP differs from local ZIP; release remains a draft')
    run([cli,'release','edit',tag,'--repo',REPO,'--draft=false','--latest'])
    print(run([cli,'release','view',tag,'--repo',REPO,'--json','url','--jq','.url'],True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Release stopped: '+str(error),file=sys.stderr);sys.exit(1)
