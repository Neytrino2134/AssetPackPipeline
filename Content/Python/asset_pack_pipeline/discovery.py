"""Pure-Python input validation. Safe to run outside Unreal."""
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from . import profiles

# Model IDs from MeshInfo (e.g. 52_Ruini_Skali_Pesok_01_01); see mesh_path for the SM_ prefix.
ASSET_ID = r'[A-Za-z0-9][A-Za-z0-9_]*'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def mesh_path(profile, asset):
    folder = profile['destination_root'].rstrip('/') + '/StaticMeshes'
    if profile.get('mesh_subdirectory'):
        folder += '/' + profile['mesh_subdirectory']
    suffix = {'LOD': '_LODS', 'Nanite': '_MID'}.get(profile.get('mesh_subdirectory'), '')
    return folder + '/SM_' + asset + suffix


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f'Path escapes source root: {relative}')
    if not path.is_file():
        raise ValueError(f'Missing source: {path}')
    return path


def glb_document(path):
    with Path(path).open('rb') as stream:
        header = stream.read(20)
        if len(header) != 20:
            raise ValueError(f'Truncated GLB: {path}')
        magic, version, total, size, kind = struct.unpack('<5I', header)
        if magic != 0x46546C67 or version != 2 or kind != 0x4E4F534A:
            raise ValueError(f'Unsupported GLB header: {path}')
        if total != Path(path).stat().st_size or size > total - 20:
            raise ValueError(f'Invalid GLB length: {path}')
        return json.loads(stream.read(size))


def detail_kind(entry,fmt):
    """Suffix is authoritative; legacy exporters can label a _MID entry role=HIGH."""
    stem=Path(entry.get('files',{}).get(fmt,'')).stem.upper()
    named=re.search(r'_(MID|HIGH)$',entry.get('name','').upper())
    filed=re.search(r'_(MID|HIGH)$',stem)
    if named and filed and named[1]!=filed[1]:raise ValueError('MID/HIGH name and file suffix disagree')
    return filed[1] if filed else named[1] if named else entry.get('role','').upper()


def select_detail(entries,fmt,selection):
    available={kind:[e for e in entries if detail_kind(e,fmt)==kind and fmt in e.get('files',{})] for kind in ('MID','HIGH')}
    kind=('MID' if available['MID'] else 'HIGH') if selection=='AUTO' else selection
    if len(available[kind])!=1:raise ValueError(f'Nanite {kind}: expected one catalog source, found {len(available[kind])}')
    return available[kind][0],kind


def scan(profile_path):
    profile = read_json(profile_path)
    if profile.get('schema_version') != 1:
        raise ValueError('Profile schema_version must be 1')
    root = Path(profile['source_root']).resolve()
    fmt = profile['source_format'].upper()
    if fmt not in ('FBX', 'GLB'):
        raise ValueError('source_format must be FBX or GLB')
    pack = profile['pack_id']
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', pack):
        raise ValueError('Invalid pack_id')
    destination = profile['destination_root'].rstrip('/')
    if not re.fullmatch(r'/Game/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*', destination):
        raise ValueError('Invalid destination_root')
    profiles.validate_settings(profile)
    warn = profile.get('validation_policy', 'warn') == 'warn'
    sizes = profile['lod_screen_sizes']
    if not sizes or any(not isinstance(x, (int, float)) or not math.isfinite(x)
                        or not 0 < x <= 1 for x in sizes):
        raise ValueError('LOD screen sizes must be finite numbers in (0,1]')
    if any(a <= b for a, b in zip(sizes, sizes[1:])):
        raise ValueError('LOD screen sizes must decrease strictly')
    if profile.get('high_policy', 'exclude') != 'exclude':
        raise ValueError('This version supports high_policy=exclude only')
    catalog = read_json(contained(root, profile.get('mesh_info', 'MeshInfo.json')))
    if catalog.get('schema_version') != 2:
        raise ValueError('MeshInfo schema_version must be 2')
    groups,details = {},{}
    for entry in catalog['meshes']:
        if entry.get('role') not in ('LOD','HIGH','MID'):
            continue
        asset = entry['asset']
        # Unreal names always get a prefix (SM_/MI_/T_), so a leading digit is safe.
        if not re.fullmatch(ASSET_ID, asset):
            raise ValueError(f'Invalid asset id: {asset}')
        groups.setdefault(asset, [])
        if entry.get('role')=='LOD':groups[asset].append(entry)
        else:details.setdefault(asset,[]).append(entry)
    selected = profile.get('asset_ids')
    overrides = profile.get('asset_overrides', {})
    if not isinstance(overrides, dict) or set(overrides) - set(groups):
        raise ValueError('asset_overrides contains unknown asset IDs or is not an object')
    # Validate even unselected overrides so a typo never remains latent in a profile.
    for asset_id in overrides:
        candidate = profiles.effective(profile, asset_id)
        if not profile.get('nanite_enabled',False) and len(candidate['lod_screen_sizes']) != len(sizes):
            raise ValueError(f'{asset_id}: override cannot change LOD count')
    if selected and len(set(selected)) != len(selected):
        raise ValueError('Duplicate asset_ids selection')
    if selected and set(selected) - set(groups):
        raise ValueError(f'Unknown asset_ids: {set(selected) - set(groups)}')
    assets = []
    hashed = {}
    for asset in sorted(groups, key=lambda value: [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', value)]):
        if selected and asset not in selected:
            continue
        try:
            item = build_asset(profile, root, fmt, asset, groups[asset], details.get(asset, []))
            assets.append(item)
            for filename in [lod['file'] for lod in item['lods']] + list(item['textures'].values()):
                hashed.setdefault(filename, None)
        except (ValueError, KeyError, OSError, IndexError, TypeError) as error:
            if not warn:
                raise
            # Keep the catalog row in the queue even when this source cannot be
            # read. A native import failure remains explicit; never shrink the pack.
            assets.append({'id': asset, 'mesh_path': mesh_path(profile, asset),
                           'lods': [], 'textures': {}, 'source_kind': 'MID' if profile.get('nanite_enabled') else 'LOD',
                           'effective_settings': {key: profiles.effective(profile, asset)[key] for key in profiles.OVERRIDE_KEYS},
                           'preflight_error': str(error), 'source_warnings': []})
    if not assets:
        raise ValueError('No LOD assets discovered')
    for path in hashed:
        hashed[path] = digest(path)
    profile_hash = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    return {'schema_version': 1, 'profile': profile, 'profile_path': str(Path(profile_path).resolve()),
            'profile_hash': profile_hash, 'source_hashes': hashed,
            'assets': assets, 'excluded_sources': [],
            'expected': {'meshes': len(assets), 'lods_per_mesh': 1 if profile.get('nanite_enabled',False) else len(sizes),
                                         'masters': 1, 'instances': len(assets),
                                         'textures': sum(len(a['textures']) for a in assets) + 1,
                                         'helper_textures': 1}}


def build_asset(profile, root, fmt, asset, ordinary, details):
    """Validate one complete source contract; errors never produce partial meshes."""
    entries = sorted(ordinary, key=lambda x: x['lod_index'])
    effective = profiles.effective(profile, asset)
    source_kind = 'LOD'
    if profile.get('nanite_enabled', False):
        entry, source_kind = select_detail(details, fmt, effective['nanite_source'])
        entries = [dict(entry, lod_index=0)]
    elif [x['lod_index'] for x in entries] != list(range(len(profile['lod_screen_sizes']))):
        raise ValueError(f'{asset}: duplicate, missing or unexpected LOD indices')
    lods, warnings = [], []
    for entry in entries:
        path = contained(root, entry['files'][fmt])
        if fmt == 'GLB':
            doc = glb_document(path)
            nodes = [n for n in doc.get('nodes', []) if n.get('name') == entry['name'] and 'mesh' in n]
            if len(nodes) != 1:
                raise ValueError(f'{asset}: ambiguous/missing GLB node {entry["name"]}')
            mesh = doc['meshes'][nodes[0]['mesh']]
            if any(p.get('mode', 4) != 4 for p in mesh['primitives']):
                raise ValueError('Only triangle-list GLB primitives are supported')
            count = sum(doc['accessors'][p['indices']]['count'] // 3 for p in mesh['primitives'])
            if count != entry['triangles']:
                message = f'{asset}: GLB triangles disagree with MeshInfo: LOD{entry["lod_index"]}, catalog {entry["triangles"]}, file {count}'
                if profile.get('validation_policy', 'warn') == 'strict':
                    raise ValueError(message)
                warnings.append({'code': 'CATALOG_TRIANGLE_MISMATCH', 'stage': 'source_preflight',
                                 'lod_index': entry['lod_index'], 'catalog_triangles': entry['triangles'],
                                 'file_triangles': count, 'message': message})
        lods.append({'index': entry['lod_index'], 'node': entry['name'],
                     'file': str(path), 'triangles': entry['triangles']})
    textures = {}
    for channel in ('BaseColor', 'Normal'):
        relative = profile.get('texture_directory', 'FBX/Textures') + f'/T_{asset}_{channel}.png'
        textures[channel] = str(contained(root, relative))
    orm = effective['orm_texture'].replace('{asset_id}', asset)
    if orm:
        textures['ORM'] = str(contained(root, orm))
    return {'id': asset, 'mesh_path': mesh_path(profile, asset),
            'lods': lods, 'textures': textures, 'source_kind': source_kind, 'source_warnings': warnings,
            'effective_settings': {key: effective[key] for key in profiles.OVERRIDE_KEYS}}
