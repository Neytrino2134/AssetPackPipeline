"""Copy only completed PNG outputs, alongside the separately verified UE ZIP."""
import hashlib
import json
import shutil
import re
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def export_root(base, now=None):
    """Atomically reserve a readable launch folder without overwriting a prior run."""
    parent=Path(base).resolve()/'FinalProject'
    parent.mkdir(parents=True,exist_ok=True)
    stamp=(now or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')
    for index in range(10000):
        folder=parent/(stamp if not index else f'{stamp}_{index+1:02d}')
        try:
            folder.mkdir()
            return folder
        except FileExistsError:continue
    raise RuntimeError('Could not reserve final output directory')


def pack_folder_name(pack):
    if not re.fullmatch(r'[A-Za-z0-9_]+',pack):raise ValueError('Invalid export pack name')
    return pack


def export_renders(reports, destination, pack_name='AssetPack', *, partial=False):
    pack_folder_name(pack_name)
    files = []
    ids=sorted({str(a['asset_id']) for r in reports for a in r['assets'] if a.get('asset_id')})
    model_ids={}
    used_ids=set()
    for index,asset_id in enumerate(ids,1):
        tail=re.search(r'(\d+(?:_\d+)*)$',asset_id)
        candidate=tail.group(1) if tail else f'{index:02d}_01'
        while candidate in used_ids:candidate+='_'+f'{index:02d}'
        model_ids[asset_id]=candidate;used_ids.add(candidate)
    names=set()
    for report in reports:
        if not partial and report['status'] != 'passed':
            raise ValueError('Render run did not pass')
        root = Path(report['output_directory']).resolve()
        run = report['run_id']
        if not run.isalnum():
            raise ValueError('Invalid render run ID')
        for asset in report['assets']:
            if partial and asset['status'] != 'passed':
                continue
            path = Path(asset['output_path']).resolve()
            if asset['status'] != 'passed' or path.suffix.lower() != '.png' or not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Missing, incomplete or unexpected render output')
            if asset.get('asset_id'):
                nanite=asset.get('representation')=='Nanite' or report.get('manifest',{}).get('profile',{}).get('nanite_enabled',False)
                lod=asset.get('lod_index',0)
                kind='MID' if nanite else 'LOW' if lod==0 else f'LOD{lod}'
                name=f"MESH_{kind}_{model_ids[str(asset['asset_id'])]}"
                if asset.get('view_index',0)>0:name+=f"_View_{asset['view_index']+1:02d}"
            else:
                name='Overview_LODs' if asset.get('lod_review') else 'Overview_All_Meshes'
            if 'render_view' in asset:
                from .render_views import suffix
                name+=suffix(asset['render_view'])
            unique=name;index=2
            while unique.casefold() in names:
                unique=f'{name}_{index:02d}';index+=1
            names.add(unique.casefold())
            files.append((unique+'.png',path,run,asset.get('asset_id')))
    if not files:
        return {'count': 0, 'status': 'not_requested'}
    folder = Path(destination)/(pack_name+'_Renders')
    folder.mkdir(exist_ok=False)
    hashes = {}
    sources={}
    for relative, source,run,asset_id in files:
        target = folder/relative
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        sources[relative]={'run_id':run,'asset_id':asset_id,'source':str(source)}
    (folder/'manifest.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    (folder/'sources.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
    archive = folder.with_suffix('.zip')
    with ZipFile(archive, 'x', ZIP_DEFLATED) as stream:
        for file in sorted(folder.rglob('*')):
            if file.is_file():
                stream.write(file, folder.name+'/'+file.relative_to(folder).as_posix())
    with ZipFile(archive) as stream:
        if stream.testzip():
            raise RuntimeError('Render ZIP failed integrity check')
    return {'count':len(files), 'directory':str(folder), 'zip_path':str(archive)}
