"""UEFN adapter: native migration handoff and independent destination read-back.

Scripts stay in the authoring plugin; never install them in UEFN Source content.
"""
import copy
import json
from pathlib import Path


def context(project_file):
    path = Path(project_file).resolve()
    if path.suffix != '.uefnproject' or not path.is_file():
        raise ValueError('Select an existing .uefnproject')
    descriptor = json.loads(path.read_text(encoding='utf-8-sig'))
    roots = [p['name'] for p in descriptor.get('plugins', []) if p.get('bIsRoot')]
    if len(roots) != 1 or '/' in roots[0] or '\\' in roots[0] or roots[0] in ('.', '..'):
        raise ValueError('Expected exactly one local UEFN root content plugin')
    plugin = path.parent/(roots[0]+'.uplugin')
    if not plugin.is_file() or not (path.parent/'Content').is_dir():
        raise ValueError('UEFN root plugin/Content missing')
    return {'project_file': str(path), 'content_directory': str(path.parent/'Content'),
            'mount': '/'+roots[0], 'compatibility_version': descriptor.get('compatibilityVersion'),
            'title': descriptor.get('title', path.stem)}


def is_uefn():
    import unreal as u
    return 'Fortnite' in u.SystemLibrary.get_engine_version()


def environment(project_file):
    import unreal as u
    result = context(project_file)
    result.update(host_is_uefn=is_uefn(), engine_version=u.SystemLibrary.get_engine_version(),
                  engine_project_dir=u.Paths.project_dir(), publication_ready=False)
    result['api'] = {name: hasattr(u, name) for name in ('StaticMeshEditorSubsystem', 'EditorAssetLibrary',
        'MaterialEditingLibrary', 'EditorActorSubsystem', 'EditorValidatorSubsystem', 'ToolsetDefinition')}
    result['validation_api'] = {name: str(getattr(u.EditorValidatorSubsystem, name).__doc__)
        for name in ('validate_assets_with_settings', 'validate_assets')
        if hasattr(u, 'EditorValidatorSubsystem') and hasattr(u.EditorValidatorSubsystem, name)}
    return result


def make_plan(delivery_report, project_file, asset_ids):
    """Pure plan: include both representations, preserve IDs and dependency migration."""
    ctx = context(project_file)
    spec = delivery_report['verification_spec']
    ids = set(asset_ids)
    if not ids or ids-set(a['id'] for a in spec['assets']):
        raise ValueError('Select existing unique model IDs')
    assets = []
    for asset, checks in zip(spec['assets'], spec['asset_checks']):
        if asset['id'] not in ids:
            continue
        if not asset['mesh_path'].startswith('/Game/'):
            raise ValueError('Donor must be a clean UE Content project')
        target = ctx['mount']+'/'+asset['mesh_path'][len('/Game/'):]
        assets.append({'id': asset['id'], 'representation': 'Nanite' if checks['nanite'] else 'LOD',
                       'source_path': asset['mesh_path'], 'target_path': target,
                       'expected': copy.deepcopy(checks), 'lod_sources': copy.deepcopy(asset['lods'])})
    for model in ids:
        if {a['representation'] for a in assets if a['id'] == model} != {'LOD', 'Nanite'}:
            raise ValueError('Each selected model must have LOD and Nanite representations')
    return {'schema_version': 1, 'kind': 'uefn_transfer', 'target': ctx,
            'source_project': delivery_report['project_path'], 'assets': assets,
            'unique_model_ids': sorted(ids), 'publication_ready': False, 'artistic_review': 'deferred_by_user'}


def migrate(plan):
    """Run in the clean donor UE editor. Native Migrate remaps packages to UEFN."""
    import unreal as u
    if is_uefn():
        raise RuntimeError('Run migration from the donor UE project')
    actual = Path(u.Paths.get_project_file_path()).resolve()
    if actual != Path(plan['source_project']).resolve():
        raise RuntimeError('Wrong donor project')
    target = context(plan['target']['project_file'])
    if target != plan['target']:
        raise RuntimeError('UEFN project identity changed')
    # Native migration handles references; never copy/rename .uasset files manually.
    options = u.MigrationOptions()
    options.set_editor_property('prompt', False)
    options.set_editor_property('ignore_dependencies', False)
    options.set_editor_property('asset_conflict', u.AssetMigrationConflict.SKIP)
    u.AssetToolsHelpers.get_asset_tools().migrate_packages(
        [u.Name(a['source_path']) for a in plan['assets']], target['content_directory'], options)
    return {'migration_invoked': True, 'destination_readback': 'required', 'publication_ready': False}


def inspect(plan):
    """Technical read-back only. Does not equate this with Fortnite validation."""
    import unreal as u
    if not is_uefn():
        raise RuntimeError('Destination read-back must run in UEFN')
    target = context(plan['target']['project_file'])
    if target != plan['target']:
        raise RuntimeError('UEFN project changed')
    registry = u.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([target['mount']], force_rescan=True)
    smes = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    mel = u.MaterialEditingLibrary
    rows = []
    instances = {}
    for asset in plan['assets']:
        mesh = u.load_asset(asset['target_path'])
        checks = {'loaded': isinstance(mesh, u.StaticMesh)}
        row = {'id': asset['id'], 'representation': asset['representation'], 'path': asset['target_path'], 'checks': checks}
        expected = asset['expected']
        if mesh:
            row.update(triangles=[mesh.get_num_triangles(i) for i in range(smes.get_lod_count(mesh))],
                       nanite_triangles=mesh.get_num_nanite_triangles() if expected['nanite'] else 0)
            checks['triangles'] = row['triangles'] == expected['triangles']
            checks['nanite'] = bool(mesh.get_editor_property('nanite_settings').enabled) == expected['nanite']
            if expected['nanite']:
                checks['nanite_source'] = row['nanite_triangles'] == expected['nanite_triangles'] > 0
            checks['collision'] = smes.get_simple_collision_count(mesh)+smes.get_convex_collision_count(mesh) == expected['simple_collision_count']
            mi = mesh.get_material(0)
            checks['material'] = isinstance(mi, u.MaterialInstanceConstant)
            if mi:
                instances.setdefault(asset['id'], []).append(mi.get_path_name())
                checks['local_instance'] = mi.get_path_name().startswith(target['mount']+'/')
                parent = mi.get_editor_property('parent')
                checks['local_master'] = bool(parent and parent.get_path_name().startswith(target['mount']+'/'))
                checks['scalars'] = all(abs(mel.get_material_instance_scalar_parameter_value(mi, k)-v) < 1e-5
                                         for k,v in expected['material_scalars'].items())
                for channel in ('BaseColor', 'Normal', 'ORM'):
                    texture = mel.get_material_instance_texture_parameter_value(mi, channel)
                    checks[channel] = isinstance(texture, u.Texture2D) and texture.get_path_name().startswith(target['mount']+'/')
        row['passed'] = all(checks.values())
        rows.append(row)
    shared = all(len(instances.get(model, [])) == 2 and len(set(instances[model])) == 1 for model in plan['unique_model_ids'])
    return {'kind': 'uefn_readback', 'assets': rows, 'shared_instances': shared,
            'passed': shared and all(r['passed'] for r in rows), 'fortnite_validation': 'not_run',
            'fortnite_session': 'not_run', 'publication_ready': False}
