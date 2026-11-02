"""Dependency-contained content project export and standalone verification launcher."""
import json
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from . import discovery

SCRIPT_MODULES = {'CoreUObject', 'Engine', 'UnrealEd', 'PhysicsCore', 'RenderCore', 'RHI', 'NavigationSystem',
                  'MeshDescription', 'StaticMeshDescription', 'InterchangeCore', 'InterchangeEngine',
                  'InterchangeFactoryNodes', 'InterchangeNodes', 'InterchangePipelines', 'InterchangeImport'}


def settings(profile):
    config = dict(profile.get('delivery', {}))
    config.setdefault('maps', 'overview')
    config.setdefault('output_directory', '')
    if config['maps'] not in ('none', 'overview', 'both'):
        raise ValueError('delivery.maps must be none, overview or both')
    if not isinstance(config['output_directory'], str) or (config['output_directory'] and not Path(config['output_directory']).is_absolute()):
        raise ValueError('delivery.output_directory must be absolute or empty')
    return config


def project_name(profile):
    # Unreal package paths cannot be renamed by copying files. Name the exported
    # project after its one top-level Content folder, preserving package paths.
    parts = profile['destination_root'].split('/')
    if len(parts)<3 or parts[1]!='Game' or not re.fullmatch('[A-Za-z0-9_]+',parts[2]):
        raise ValueError('Invalid delivery Content root')
    return parts[2]


def dependency_closure(roots, dependencies, allowed_root):
    pending, selected, blocked = list(roots), set(), set()
    while pending:
        package = pending.pop()
        if package in selected:
            continue
        if package.startswith('/Engine/'):
            continue
        if package.startswith('/Script/'):
            if package.removeprefix('/Script/') not in SCRIPT_MODULES:
                blocked.add(package)
            continue
        if not package.startswith(allowed_root+'/'):
            blocked.add(package)
            continue
        selected.add(package)
        pending.extend(dependencies(package))
    return sorted(selected), sorted(blocked)


def package_files(content, packages):
    content = Path(content).resolve()
    result = []
    for package in packages:
        if not package.startswith('/Game/'):
            raise ValueError('Invalid export package')
        stem = (content/package.removeprefix('/Game/')).resolve()
        if not stem.is_relative_to(content):
            raise ValueError('Package escapes Content')
        mains = [stem.with_suffix(ext) for ext in ('.uasset', '.umap') if stem.with_suffix(ext).is_file()]
        if len(mains) != 1:
            raise ValueError(f'Missing or ambiguous saved package: {package}')
        result.extend(mains)
        result.extend(stem.with_suffix(ext) for ext in ('.uexp', '.ubulk') if stem.with_suffix(ext).is_file())
    return sorted(set(result))


def plan(manifest):
    if manifest.get('variants'):
        proposals = [plan(part) for part in manifest['variants']]
        return {'ready': all(p['ready'] for p in proposals),
                'blockers': [b for p in proposals for b in p['blockers']],
                'packages': sorted({v for p in proposals for v in p['packages']}),
                'files': sorted({v for p in proposals for v in p['files']}),
                'maps': [v for p in proposals for v in p['maps']],
                'asset_checks': [v for p in proposals for v in p['asset_checks']],
                'delivery_settings': settings(manifest['profile']),
                'publication_ready': False, 'visual_review': 'deferred_by_user'}
    import unreal as u
    from . import runtime, cleanup, overview
    cleanup.assert_clean()
    config, profile = settings(manifest['profile']), manifest['profile']
    checks = [runtime.inspect(manifest, asset) for asset in manifest['assets']]
    blockers = [f"Asset failed validation: {row['id']}" for row in checks if not row['passed']]
    if manifest.get('excluded_sources'):
        blockers.append('Source preflight excluded assets; create an explicit strict review candidate first')
    roots = [p for asset in manifest['assets'] for p in runtime._paths(manifest, asset)]
    maps = []
    for lod in ([False, True] if config['maps']=='both' else [False] if config['maps']=='overview' else []):
        path = overview.settings(profile, lod)['map_path']
        world = u.load_asset(path)
        if not world or not runtime.owned(world, profile['pack_id']):
            blockers.append('Create/save the owned map first: '+path)
        del world
        maps.append({'map_path':path, 'lod_review':lod})
        roots.append(path)
    registry = u.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(synchronous_search=True)
    registry.scan_paths_synchronous([profile['destination_root']], force_rescan=True)
    packages, blocked = dependency_closure(roots,
        lambda p: [str(x) for x in (registry.get_dependencies(p, cleanup.dependency_options()) or [])], profile['destination_root'])
    blockers.extend('External/unsupported dependency: '+p for p in blocked)
    try:
        files = package_files(u.Paths.project_content_dir(), packages)
    except ValueError as error:
        files = []
        blockers.append(str(error))
    return {'ready':not blockers, 'blockers':blockers, 'packages':packages, 'maps':maps,
            'files':[str(p) for p in files], 'asset_checks':checks, 'delivery_settings':config,
            'publication_ready':False, 'visual_review':'pending'}


def create(manifest, run_id):
    import unreal as u
    from . import overview
    proposal = plan(manifest)
    if not proposal['ready']:
        raise RuntimeError('; '.join(proposal['blockers']))
    scenes = []
    for item in proposal['maps']:
        scene_manifest = next((part for part in manifest.get('variants', [])
            if overview.settings(part['profile'], item['lod_review'])['map_path'] == item['map_path']), manifest)
        overview.open_map(scene_manifest, item['lod_review'])
        check = overview.validate_current(scene_manifest, item['lod_review'])
        if not check['passed']:
            raise RuntimeError('Scene read-back failed before delivery: '+item['map_path'])
        _, layout, _ = overview.prepare(scene_manifest, item['lod_review'])
        scenes.append(dict(item, cells=layout['cells'], expected_actor_count=check['expected_actor_count']))
    profile, config = manifest['profile'], proposal['delivery_settings']
    base = Path(config['output_directory']) if config['output_directory'] else Path(u.Paths.project_saved_dir()).resolve()/'AssetPackPipeline/Deliveries'
    name = project_name(profile)
    from .final_output import export_root
    if (base/'FinalProject').resolve().is_relative_to(Path(u.Paths.project_content_dir()).resolve()):
        raise ValueError('Delivery output must be outside the authoring Content directory')
    project = (export_root(base)/(name+'_Project')).resolve()
    content = Path(u.Paths.project_content_dir()).resolve()
    if project.is_relative_to(content):
        raise ValueError('Delivery output must be outside the authoring Content directory')
    project.mkdir(parents=True, exist_ok=False)
    for filename in proposal['files']:
        path = Path(filename)
        target = project/'Content'/path.relative_to(content)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if discovery.digest(path)!=discovery.digest(target):
            raise RuntimeError('Package changed while copying: '+str(path))
    engine = u.SystemLibrary.get_engine_version().split('-')[0].split('.')
    descriptor = {'FileVersion':3, 'EngineAssociation':'.'.join(engine[:2]), 'Category':'Asset Packs',
                  'Description':profile['pack_id']+' content project', 'DisableEnginePluginsByDefault':True,
                  'Plugins':[{'Name':'Interchange', 'Enabled':True}, {'Name':'InterchangeEditor','Enabled':True},
                             {'Name':'ContentBrowserAssetDataSource', 'Enabled':True},
                             {'Name':'ContentBrowserClassDataSource', 'Enabled':True}]}
    uproject = project/(name+'.uproject')
    uproject.write_text(json.dumps(descriptor, indent=2), encoding='utf-8')
    configs = project/'Config'
    configs.mkdir()
    map_path = scenes[0]['map_path'] if scenes else '/Engine/Maps/Entry'
    (configs/'DefaultEngine.ini').write_text('[/Script/EngineSettings.GameMapsSettings]\nEditorStartupMap='+map_path+'\nGameDefaultMap='+map_path+'\n\n'
        '[Animation.DefaultObjectSettings]\nBoneCompressionSettings=/Engine/Animation/DefaultAnimBoneCompressionSettings\n'
        'CurveCompressionSettings=/Engine/Animation/DefaultAnimCurveCompressionSettings\n'
        + ('\n[/Script/WindowsTargetPlatform.WindowsTargetSettings]\nDefaultGraphicsRHI=DefaultGraphicsRHI_DX12\n'
           '-D3D12TargetedShaderFormats=PCD3D_SM5\n+D3D12TargetedShaderFormats=PCD3D_SM6\n'
           '\n[/Script/Engine.RendererSettings]\nr.Nanite.ProjectEnabled=True\nr.Nanite=1\n'
           if any(a.get('representation') == 'Nanite' for a in manifest['assets']) or profile.get('nanite_enabled') else ''), encoding='utf-8')
    (configs/'DefaultGame.ini').write_text('[/Script/EngineSettings.GeneralProjectSettings]\nProjectName='+name+'\n', encoding='utf-8')
    technical = {'pack_id':profile['pack_id'], 'engine_version':u.SystemLibrary.get_engine_version(),
                 'assets':[{'id':a['id'], 'representation':a.get('representation', 'Nanite' if c['nanite'] else 'LOD'),
                            'mesh_path':a['mesh_path'], 'source_files':[lod['file'] for lod in a['lods']],
                            'triangles':c['triangles'], 'screen_sizes':c['screen_sizes'],
                            'material_scalars':c['material_scalars'], 'nanite':c['nanite'],
                            'nanite_triangles':c.get('nanite_triangles',0), 'source_kind':a.get('source_kind','LOD'),
                            'strict_passed':c.get('strict_passed',c['passed']), 'warnings':c.get('warnings',[]),
                            'source_triangles':c.get('source_triangles',c['triangles'])} for a,c in zip(manifest['assets'],proposal['asset_checks'])],
                 'validation_policy':profile.get('validation_policy','warn'),
                 'quality_passed':all(c.get('strict_passed',c['passed']) for c in proposal['asset_checks']),
                 'visual_review':'deferred_by_user' if manifest.get('variants') else 'pending', 'publication_ready':False}
    (project/'TechnicalManifest.json').write_text(json.dumps(technical, indent=2), encoding='utf-8')
    if manifest.get('variants'):
        docs = project/'Documentation'
        docs.mkdir()
        (docs/'GettingStarted.md').write_text(
            '# '+profile['pack_id']+'\n\nOne product, two representations of each unique model.\n\n'
            'StaticMeshes/LOD: five authored LODs, Nanite off.\n'
            'StaticMeshes/Nanite: MID/HIGH sources, Nanite on, one source LOD.\n'
            'Materials and textures are shared by both representations.\n'
            'Maps/Overview_LOD and Maps/Overview_Nanite show the same models in each mode.\n'
            'Use the Content Browser Migrate action to transfer assets with dependencies.\n'
            'No AssetPackPipeline or MCP installation is required.\n'
            'Artistic acceptance is deferred; technical quality warnings remain in TechnicalManifest.json.\n', encoding='utf-8')
    hashes = {str(p.relative_to(project)):discovery.digest(p) for p in project.rglob('*') if p.is_file()}
    return dict(proposal, project_path=str(uproject), project_directory=str(project), file_hashes=hashes,
                verification_spec={'pack_id':profile['pack_id'], 'assets':manifest['assets'],
                                   'asset_checks':proposal['asset_checks'], 'scenes':scenes,
                                   'shared_representations':bool(manifest.get('variants'))},
                fresh_project_verification='pending', passed=True)


def combine(manifests):
    """Bundle representations using one pack root and shared material/texture paths."""
    import copy
    if len(manifests) != 2:
        raise ValueError('Combined delivery requires LOD and Nanite profiles')
    first = manifests[0]['profile']
    ids = sorted(a['id'] for a in manifests[0]['assets'])
    if {m['profile'].get('nanite_enabled', False) for m in manifests} != {False, True}:
        raise ValueError('Expected one LOD and one Nanite representation')
    paths = []
    for manifest in manifests:
        profile = manifest['profile']
        if any(profile[k] != first[k] for k in ('pack_id', 'destination_root', 'source_root')):
            raise ValueError('Representations must share pack, Content root and sources')
        if sorted(a['id'] for a in manifest['assets']) != ids:
            raise ValueError('Both representations must retain the same complete model list')
        if settings(profile)['maps'] != 'overview':
            raise ValueError('Combined delivery expects one overview map per representation')
        for asset in manifest['assets']:
            paths.append(asset['mesh_path'])
    if len(paths) != len(set(paths)):
        raise ValueError('Representation mesh paths overlap; set mesh_subdirectory')
    from . import overview
    if len({overview.settings(m['profile'])['map_path'] for m in manifests}) != 2:
        raise ValueError('Representation overview maps must have different names')
    merged = copy.deepcopy(manifests[0])
    merged['variants'] = manifests
    merged['assets'] = [dict(a, representation='Nanite' if m['profile'].get('nanite_enabled') else 'LOD')
                        for m in manifests for a in m['assets']]
    return merged


def verify_files(report):
    project = Path(report['project_directory']).resolve()
    for relative, expected in report['file_hashes'].items():
        path = (project/relative).resolve()
        if not path.is_relative_to(project) or not path.is_file() or discovery.digest(path)!=expected:
            raise RuntimeError('Delivery file missing/changed: '+relative)
    descriptor = discovery.read_json(report['project_path'])
    forbidden = ('AssetPackPipeline','ModelContextProtocol','AllToolsets','ToolsetRegistry','PythonScriptPlugin')
    text = json.dumps(descriptor)
    if any(name in text for name in forbidden) or descriptor.get('AdditionalPluginDirectories'):
        raise RuntimeError('Delivery references authoring plugins')
    if (project/'Plugins').exists():
        raise RuntimeError('Unexpected Plugins directory in clean delivery')
    descriptor_path=Path(report['project_path']).resolve()
    if {p.relative_to(project/'Content').parts[0] for p in (project/'Content').rglob('*') if p.is_file()}!={descriptor_path.stem} or descriptor_path.parent!=project:
        raise RuntimeError('Project name and the single Content folder must match')
    return True


def launch_verifier(delivery_report, run_folder):
    import unreal as u
    verify_files(delivery_report)
    folder = Path(run_folder)
    folder.mkdir(parents=True, exist_ok=True)
    script = folder/'verify_project.py'
    shutil.copyfile(Path(__file__).with_name('delivery_verify.py'), script)
    (folder/'spec.json').write_text(json.dumps(delivery_report['verification_spec']), encoding='utf-8')
    binary = Path(u.Paths.engine_dir()).resolve()/'Binaries/Win64/UnrealEditor.exe'
    args = [str(binary), Path(delivery_report['project_path']).as_posix(), '-EnablePlugins=PythonScriptPlugin,EditorScriptingUtilities',
            '-ExecutePythonScript='+script.as_posix(), '-unattended', '-nosplash', '-nullrhi', '-nosound',
            '-abslog='+(folder/'editor.log').as_posix()]
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            startupinfo=info, creationflags=subprocess.CREATE_NO_WINDOW)


def package(report):
    verify_files(report)
    if report.get('fresh_project_verification')!='passed':
        raise RuntimeError('Run the fresh-project verification before packaging')
    project = Path(report['project_directory'])
    target = project.parent/(project.name+'.zip')
    if target.exists():
        raise RuntimeError('Delivery ZIP already exists')
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(report['file_hashes']):
            archive.write(project/relative, project.name+'/'+Path(relative).as_posix())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip():
            raise RuntimeError('Delivery ZIP integrity check failed')
    return {'zip_path':str(target), 'zip_sha256':discovery.digest(target), 'publication_ready':False}


def launch_cook(report,folder):
    import unreal as u
    verify_files(report)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    maps=[s['map_path'] for s in report['verification_spec']['scenes']]
    if not maps:raise ValueError('Cooking requires a delivered map')
    binary=Path(u.Paths.engine_dir()).resolve()/'Binaries/Win64/UnrealEditor-Cmd.exe'
    args=[str(binary),report['project_path'],'-run=cook','-TargetPlatform=Windows','-Map='+'+'.join(maps),
          '-unattended','-NullRHI','-NoP4','-SkipZenStore','-UTF8Output','-abslog='+str(folder/'cook.log')]
    info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=0
    return subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                            startupinfo=info,creationflags=subprocess.CREATE_NO_WINDOW)


def inspect_cook(source,folder,exit_code):
    path=Path(folder)/'cook.log'
    log=path.read_text(encoding='utf-8',errors='replace') if path.is_file() else ''
    errors=[line for line in log.splitlines() if ': Error:' in line or 'Fatal error:' in line]
    warnings=[line for line in log.splitlines() if ': Warning:' in line]
    cooked=Path(source['project_directory'])/'Saved/Cooked/Windows'
    files=list(cooked.rglob('*.umap'))
    requested=[s['map_path'] for s in source['verification_spec']['scenes']]
    maps={name:any(p.as_posix().endswith('/Content/'+name.removeprefix('/Game/')+'.umap') for p in files) for name in requested}
    return {'passed':exit_code==0 and not errors and all(maps.values()),'exit_code':exit_code,
            'cooked_maps':maps,'errors':errors,'warnings':warnings,'log_path':str(path),
            'target_platform':'Windows','loose_file_count':sum(p.is_file() for p in cooked.rglob('*')),
            'publication_ready':False}
