"""Unreal-only operations. Imported lazily so discovery remains testable."""
from pathlib import Path
import shutil
import json
import uuid
import unreal as u

OWNER = 'AssetPackPipeline.Owner'
_commandlet_smes = None


def smes():
    global _commandlet_smes
    subsystem = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    if subsystem:
        return subsystem
    if '-run=pythonscript' in u.SystemLibrary.get_command_line().lower():
        if _commandlet_smes is None:
            _commandlet_smes = u.new_object(u.StaticMeshEditorSubsystem)
        return _commandlet_smes
    raise RuntimeError('StaticMeshEditorSubsystem is unavailable')


def assert_editor_idle():
    if u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world():
        raise RuntimeError('Stop PIE before running AssetPackPipeline')


def owned(obj, pack):
    return str(u.EditorAssetLibrary.get_metadata_tag(obj, OWNER)) == pack


def mark(obj, pack):
    u.EditorAssetLibrary.set_metadata_tag(obj, OWNER, pack)


def _paths(manifest, asset):
    root = manifest['profile']['destination_root']
    pack = manifest['profile']['pack_id']
    return [asset['mesh_path'], f'{root}/Textures/T_{pack}_ORM_Default', f'{root}/Materials/Master/M_{pack}_Master',
            f'{root}/Materials/Instances/MI_{asset["id"]}'] + [
                f'{root}/Textures/T_{asset["id"]}_{channel}' for channel in asset['textures']]


def conflicts(manifest):
    result = []
    pack = manifest['profile']['pack_id']
    for asset in manifest['assets']:
        for path in _paths(manifest, asset):
            obj = u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None
            if obj and not owned(obj, pack):
                result.append(path)
            if isinstance(obj, u.Material):
                from . import materials
                version = str(u.EditorAssetLibrary.get_metadata_tag(obj, materials.GRAPH_TAG))
                if version not in ('', '1', materials.GRAPH_VERSION):
                    raise RuntimeError(f'Unsupported material graph version at {path}: {version}')
    return sorted(set(result))


def backup(manifest, destination):
    """Keep previous on-disk packages before any replacing import."""
    paths = set(path for asset in manifest['assets'] for path in _paths(manifest, asset))
    dirty = {p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    if dirty & paths:
        raise RuntimeError('Save or revert dirty target packages before starting a job')
    content = Path(u.Paths.project_content_dir()).resolve()
    for path in paths:
        relative = path.removeprefix('/Game/')
        for suffix in ('.uasset', '.uexp', '.ubulk'):
            original = content / (relative + suffix)
            if original.is_file():
                target = destination / (relative + suffix)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(original, target)


def assert_targets_clean(manifest):
    paths = set(path for asset in manifest['assets'] for path in _paths(manifest, asset))
    dirty = {p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    if dirty & paths:
        raise RuntimeError('Save or revert dirty target packages before starting a job')


def save(obj):
    if not u.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
        raise RuntimeError(f'Failed to save {obj.get_path_name()}')


def _create(path, cls, factory, pack):
    if u.EditorAssetLibrary.does_asset_exist(path):
        obj = u.load_asset(path)
        if not isinstance(obj, cls) or not owned(obj, pack):
            raise RuntimeError(f'Conflicting asset at {path}')
        return obj, False
    folder, name = path.rsplit('/', 1)
    obj = u.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)
    if not obj:
        raise RuntimeError(f'Cannot create {path}')
    mark(obj, pack)
    return obj, True


def import_file(filename, folder, name='', options=None, factory=None):
    task = u.AssetImportTask()
    task.filename = filename
    task.destination_path = folder
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.async_ = False
    if options:
        task.options = options
    if factory:
        task.factory = factory
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    objects = list(task.get_objects())
    if not objects:
        objects = [u.load_asset(p) for p in task.imported_object_paths]
    if not objects:
        raise RuntimeError(f'Import returned no assets: {filename}')
    return objects


def _textures(manifest, asset):
    pack = manifest['profile']['pack_id']
    root = manifest['profile']['destination_root']
    result = {}
    for channel, filename in asset['textures'].items():
        name = f'T_{asset["id"]}_{channel}'
        objects = import_file(filename, f'{root}/Textures', name, factory=u.TextureFactory())
        texture = next((obj for obj in objects if isinstance(obj, u.Texture2D)), None)
        if texture is None:
            raise RuntimeError(f'No Texture2D: {filename}')
        texture.set_editor_property('srgb', channel == 'BaseColor')
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_NORMALMAP if channel == 'Normal'
                                    else u.TextureCompressionSettings.TC_MASKS if channel == 'ORM'
                                    else u.TextureCompressionSettings.TC_DEFAULT)
        mark(texture, pack)
        save(texture)
        result[channel] = texture
    return result


def _materials(manifest, asset, textures):
    from . import materials, profiles
    profile = manifest['profile']
    root, pack = profile['destination_root'], profile['pack_id']
    neutral = materials.neutral_texture(profile)
    master, _ = _create(f'{root}/Materials/Master/M_{pack}_Master', u.Material, u.MaterialFactoryNew(), pack)
    if materials.build_graph(master, textures, neutral):
        save(master)
    instance, _ = _create(f'{root}/Materials/Instances/MI_{asset["id"]}', u.MaterialInstanceConstant,
                          u.MaterialInstanceConstantFactoryNew(), pack)
    mel = u.MaterialEditingLibrary
    mel.set_material_instance_parent(instance, master)
    # UE 5.8 stores usage on instances. Set it before rendering/building the
    # Nanite mesh, otherwise automatic usage detection dirties a saved MI later.
    if profile.get('nanite_enabled', False):
        mel.set_material_usage_override(instance, u.MaterialUsage.MATUSAGE_NANITE, True, True)
    # Explicitly reset ORM binding and scalar values when an override is removed.
    for channel in ('BaseColor', 'Normal', 'ORM'):
        texture = textures.get(channel, neutral)
        mel.set_material_instance_texture_parameter_value(instance, channel, texture)
        if mel.get_material_instance_texture_parameter_value(instance, channel) != texture:
            raise RuntimeError(f'Cannot set {channel} parameter')
    for name, value in profiles.material_scalars(profile, 'ORM' in textures).items():
        mel.set_material_instance_scalar_parameter_value(instance, name, value)
    mel.update_material_instance(instance)
    save(instance)
    return instance


def _fbx(manifest, asset, instance, run_id=None):
    profile = manifest['profile']
    path = asset['mesh_path']
    folder, name = path.rsplit('/', 1)
    options = u.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.import_mesh = True
    options.import_as_skeletal = False
    options.mesh_type_to_import = u.FBXImportType.FBXIT_STATIC_MESH
    options.original_import_type = u.FBXImportType.FBXIT_STATIC_MESH
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False
    data = options.static_mesh_import_data
    data.combine_meshes = False
    data.import_mesh_lo_ds = False
    data.auto_generate_collision = False
    data.remove_degenerates = profile.get('remove_degenerates', True)
    data.normal_import_method = u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    subsystem = smes()
    stage_run = run_id or uuid.uuid4().hex
    stage = f'/Game/AssetPackPipeline_Staging/{stage_run}/FBX/{asset["id"]}'
    if not profile.get('remove_degenerates', True) and u.EditorAssetLibrary.does_directory_exist(stage):
        if u.EditorAssetLibrary.list_assets(stage, recursive=True, include_folder=False):
            raise RuntimeError(f'Staging folder must be empty: {stage}')
    if profile.get('remove_degenerates', True):
        mesh = next(obj for obj in import_file(asset['lods'][0]['file'], folder, name, options, u.FbxFactory())
                    if isinstance(obj, u.StaticMesh))
    else:
        # Reimport can retain the destination's previous LOD0 build settings.
        # A fresh staged base avoids that hidden state, including after changing
        # a formerly remove=True profile to remove=False.
        source0 = next(obj for obj in import_file(asset['lods'][0]['file'], stage, asset['lods'][0]['node'], options, u.FbxFactory())
                       if isinstance(obj, u.StaticMesh))
        source0.set_material(0, instance)
        mesh = u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else u.EditorAssetLibrary.duplicate_asset(source0.get_path_name(), path)
        if mesh is None:
            raise RuntimeError('Could not create FBX destination mesh')
        subsystem.remove_lods(mesh)
        mesh.set_material(0, instance)
        if subsystem.set_lod_from_static_mesh(mesh, 0, source0, 0, True) != 0:
            raise RuntimeError('Could not copy staged FBX LOD0')
    mark(mesh, profile['pack_id'])
    subsystem.remove_lods(mesh)
    mesh.set_material(0, instance)
    for lod in asset['lods'][1:]:
        if profile.get('remove_degenerates', True):
            index = subsystem.import_lod(mesh, lod['index'], lod['file'])
        else:
            # UE's ImportLOD creates its own FBX options; it re-enabled removal
            # on LOD1+ despite the base FbxImportUI flag. Use explicit options
            # for every source level when the profile requests preservation.
            source = next(obj for obj in import_file(lod['file'], stage, lod['node'], options, u.FbxFactory())
                          if isinstance(obj, u.StaticMesh))
            source.set_material(0, instance)
            index = subsystem.set_lod_from_static_mesh(mesh, lod['index'], source, 0, True)
        if index != lod['index']:
            raise RuntimeError(f'LOD import index {index} != {lod["index"]}')
    u.EditorAssetLibrary.set_metadata_tag(mesh, 'AssetPackPipeline.LODSources', json.dumps(asset['lods']))
    if not profile.get('remove_degenerates', True):
        from . import cleanup
        cleanup.mark_staging(stage, profile['pack_id'], stage_run)
    return mesh


def _glb(manifest, asset, instance, run_id):
    folder = f'/Game/AssetPackPipeline_Staging/{run_id}/{asset["id"]}'
    if u.EditorAssetLibrary.does_directory_exist(folder) and u.EditorAssetLibrary.list_assets(folder, recursive=True, include_folder=False):
        raise RuntimeError(f'Staging folder must be empty: {folder}')
    # The default Interchange path preserves individual source meshes. Discovery
    # and strict mapping below reject merged/ambiguous importer results.
    paths = sorted(set(lod['file'] for lod in asset['lods']))
    imported = []
    for filename in paths:
        imported.extend(import_file(filename, folder))
    meshes = [obj for obj in imported if isinstance(obj, u.StaticMesh)]
    mapping = {}
    for lod in asset['lods']:
        candidates = [obj for obj in meshes if obj.get_name() == lod['node']]
        if len(candidates) != 1:
            raise RuntimeError(f'GLB node mapping failed: {lod["node"]}; got {[m.get_name() for m in meshes]}')
        mapping[lod['index']] = candidates[0]
        mapping[lod['index']].set_material(0, instance)
    path = asset['mesh_path']
    if u.EditorAssetLibrary.does_asset_exist(path):
        mesh = u.load_asset(path)
    else:
        mesh = u.EditorAssetLibrary.duplicate_asset(mapping[0].get_path_name(), path)
    if not mesh:
        raise RuntimeError('Cannot create destination GLB mesh')
    mark(mesh, manifest['profile']['pack_id'])
    subsystem = smes()
    subsystem.remove_lods(mesh)
    for lod in asset['lods']:
        index = subsystem.set_lod_from_static_mesh(mesh, lod['index'], mapping[lod['index']], 0, True)
        if index != lod['index']:
            raise RuntimeError(f'GLB LOD copy failed: {index}')
    from . import cleanup
    cleanup.mark_staging(folder, manifest['profile']['pack_id'], run_id)
    return mesh


def _settings(manifest, mesh, instance):
    profile = manifest['profile']
    subsystem = smes()
    if profile['source_format'].upper() == 'FBX':
        for index in range(subsystem.get_lod_count(mesh)):
            options = subsystem.get_lod_build_settings(mesh, index)
            options.remove_degenerates = profile.get('remove_degenerates', True)
            subsystem.set_lod_build_settings(mesh, index, options)
    for index in range(len(mesh.static_materials)):
        mesh.set_material(index, instance)
    nanite = mesh.get_editor_property('nanite_settings')
    nanite.enabled = profile.get('nanite_enabled', False)
    subsystem.set_nanite_settings(mesh, nanite, True)
    subsystem.remove_collisions(mesh)
    collision = profile.get('collision', 'none')
    if collision == 'box':
        if subsystem.add_simple_collisions(mesh, u.ScriptingCollisionShapeType.BOX) < 0:
            raise RuntimeError('Failed to create box collision')
    elif collision != 'none':
        raise ValueError('Only collision none/box supported in 0.1')
    # Collision edits rebuild render data. Save waits for pending mesh compilation;
    # apply thresholds only after that rebuild has completed.
    save(mesh)
    if not subsystem.set_lod_screen_sizes(mesh, profile['lod_screen_sizes']):
        raise RuntimeError('Failed to set LOD screen sizes')
    save(mesh)
    save(instance)


def inspect(manifest, asset):
    if asset.get('preflight_error'):
        raise ValueError(asset['preflight_error'])
    from . import profiles, materials
    manifest = profiles.for_asset(manifest, asset)
    mesh = u.load_asset(asset['mesh_path'])
    if not isinstance(mesh, u.StaticMesh):
        raise ValueError('Missing destination StaticMesh')
    profile = manifest['profile']
    subsystem = smes()
    count = subsystem.get_lod_count(mesh)
    triangles = [mesh.get_num_triangles(i) for i in range(count)]
    sizes = list(subsystem.get_lod_screen_sizes(mesh))
    expected = [lod['triangles'] for lod in asset['lods']]
    root = profile['destination_root']
    mi = u.load_asset(f'{root}/Materials/Instances/MI_{asset["id"]}')
    master = u.load_asset(f'{root}/Materials/Master/M_{profile["pack_id"]}_Master')
    material_ok = mi is not None and all(mesh.get_material(i) == mi for i in range(len(mesh.static_materials)))
    parent_ok = mi is not None and mi.get_editor_property('parent') == master
    texture_ok = True
    for channel in asset['textures']:
        texture = u.load_asset(f'{root}/Textures/T_{asset["id"]}_{channel}')
        texture_ok &= texture is not None and texture.get_editor_property('srgb') == (channel == 'BaseColor')
        compression = (u.TextureCompressionSettings.TC_NORMALMAP if channel == 'Normal' else
                       u.TextureCompressionSettings.TC_MASKS if channel == 'ORM' else u.TextureCompressionSettings.TC_DEFAULT)
        texture_ok &= texture is not None and texture.get_editor_property('compression_settings') == compression
        if mi and texture:
            texture_ok &= u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(mi, channel) == texture
    expected_scalars = profiles.material_scalars(profile, 'ORM' in asset['textures'])
    scalars = {name: u.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(mi, name)
               for name in expected_scalars} if mi else {}
    scalars_ok = len(scalars) == len(expected_scalars) and all(abs(scalars[k]-v) < 1e-5 for k,v in expected_scalars.items())
    graph_version = str(u.EditorAssetLibrary.get_metadata_tag(master, materials.GRAPH_TAG)) if master else ''
    graph_ok = graph_version == materials.GRAPH_VERSION
    if 'ORM' not in asset['textures']:
        neutral = u.load_asset(materials.neutral_path(profile))
        texture_ok &= bool(neutral and not neutral.get_editor_property('srgb') and
                           neutral.get_editor_property('compression_settings') == u.TextureCompressionSettings.TC_MASKS and mi and
                           u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(mi, 'ORM') == neutral)
    thresholds_ok = len(sizes) == len(profile['lod_screen_sizes']) and all(
        abs(a-b) < 1e-5 for a,b in zip(sizes, profile['lod_screen_sizes']))
    nanite = bool(mesh.get_editor_property('nanite_settings').enabled)
    nanite_expected = profile.get('nanite_enabled', False)
    nanite_triangles = mesh.get_num_nanite_triangles() if nanite else 0
    source_triangles = [nanite_triangles] if nanite_expected else triangles
    remove_flags = [subsystem.get_lod_build_settings(mesh, i).remove_degenerates for i in range(count)]
    fbx_flags_ok = profile['source_format'].upper() != 'FBX' or all(v == profile.get('remove_degenerates', True) for v in remove_flags)
    collision_count = subsystem.get_simple_collision_count(mesh)
    collision_ok = collision_count == (1 if profile.get('collision', 'none') == 'box' else 0)
    bounds = mesh.get_bounding_box()
    from . import diagnostics
    mismatches = diagnostics.explain_mismatches(manifest, asset, source_triangles)
    summary = '; '.join(f"LOD{x['lod_index']}: {x['expected_triangles']} → {x['imported_triangles']}. " + x.get('message', x.get('error', ''))
                        for x in mismatches)
    preparation_ok = bool(thresholds_ok and material_ok and parent_ok and texture_ok and scalars_ok and graph_ok and nanite == nanite_expected and collision_ok and fbx_flags_ok and count == len(expected) and all(n > 0 for n in source_triangles))
    strict_ok = preparation_ok and source_triangles == expected and not asset.get('source_warnings')
    warnings = list(asset.get('source_warnings', [])) + [dict(row, code='IMPORTED_TRIANGLE_MISMATCH', stage='mesh_readback') for row in mismatches]
    passed = preparation_ok and (strict_ok or profile.get('validation_policy', 'warn') == 'warn')
    return {'id': asset['id'], 'mesh_path': mesh.get_path_name(), 'lod_count': count,
            'triangles': triangles, 'expected_triangles': expected, 'screen_sizes': sizes,
            'source_triangles': source_triangles, 'nanite_triangles': nanite_triangles,
            'source_kind': asset.get('source_kind', 'LOD'),
            'material_slots': len(mesh.static_materials), 'materials_ok': bool(material_ok),
            'parent_ok': bool(parent_ok), 'textures_ok': bool(texture_ok),
            'material_scalars': scalars, 'expected_material_scalars': expected_scalars,
            'material_scalars_ok': scalars_ok, 'material_graph_version': graph_version, 'material_graph_ok': graph_ok,
            'effective_settings': {k: profile[k] for k in profiles.OVERRIDE_KEYS},
            'bounds_min': [bounds.min.x, bounds.min.y, bounds.min.z],
            'bounds_max': [bounds.max.x, bounds.max.y, bounds.max.z], 'nanite': nanite,
            'simple_collision_count': collision_count, 'collision_count_ok': collision_ok,
            'triangle_mismatches': mismatches,
            'preparation_passed': preparation_ok, 'strict_passed': strict_ok, 'warnings': warnings,
            'effective_remove_degenerates': remove_flags, 'fbx_flags_ok': fbx_flags_ok,
            'validation_summary': summary or ('' if preparation_ok else 'Read-back values disagree with material, texture, LOD, Nanite or collision settings'),
            'passed': passed,
            'visual_review': 'pending'}


def process_asset(manifest, index, run_id, settings_only=False):
    assert_editor_idle()
    if conflicts(manifest):
        raise RuntimeError('Destination ownership changed since job preflight')
    asset = manifest['assets'][index]
    if asset.get('preflight_error'):
        raise ValueError(asset['preflight_error'])
    from . import profiles
    manifest = profiles.for_asset(manifest, asset)
    if settings_only:
        mesh = u.load_asset(asset['mesh_path'])
        if not isinstance(mesh, u.StaticMesh) or not owned(mesh, manifest['profile']['pack_id']):
            raise RuntimeError('Settings update requires an existing owned mesh; import it first')
        if smes().get_lod_count(mesh) != len(asset['lods']):
            raise RuntimeError('Settings update cannot change LOD count; reimport the mesh')
    textures = _textures(manifest, asset)
    instance = _materials(manifest, asset, textures)
    if not settings_only:
        mesh = _fbx(manifest, asset, instance, run_id) if manifest['profile']['source_format'].upper() == 'FBX' else _glb(manifest, asset, instance, run_id)
    _settings(manifest, mesh, instance)
    result = inspect(manifest, asset)
    return result
