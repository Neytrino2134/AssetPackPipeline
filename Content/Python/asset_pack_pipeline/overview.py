"""Deterministic overview/forced-LOD maps. Only tagged generated actors are updated."""
import math
import gc
import re
import shutil
from pathlib import Path


def backdrop_floor_size(width, depth, camera_distance):
    """A cheap cube, at least 2 km wide, well beyond both camera frusta."""
    return max(200000.0, 20.0*max(width, depth, camera_distance))


def settings(profile, lod_review=False):
    if lod_review and profile.get('nanite_enabled', False):
        raise ValueError('Forced LOD review requires Nanite OFF; use the overview for Nanite meshes')
    config = dict(profile.get('overview', {}))
    columns = config.get('columns', 4)
    if isinstance(columns, bool) or not isinstance(columns, int) or not 1 <= columns <= 12:
        raise ValueError('Overview columns must be an integer from 1 to 12')
    for key, default, low, high in [('spacing', 100.0, 20, 2000), ('label_size', 5.0, 1, 40)]:
        value = float(config.get(key, default))
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'Overview {key} must be in [{low}, {high}]')
        config[key] = value
    key = 'lod_map_name' if lod_review else 'map_name'
    name = config.get(key, ('LOD_Review_' if lod_review else 'Overview_') + profile['pack_id'])
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', name):
        raise ValueError('Overview map name must use English letters, digits and underscores')
    path = profile['destination_root'].rstrip('/') + '/Maps/' + name
    if 'map_path_override' in config:
        path = config['map_path_override']
        if not re.fullmatch(r'/Game/AssetPackPipeline_Previews/[0-9a-f]{32}/Studio', path):
            raise ValueError('Map override is reserved for isolated media studios')
    config.update(columns=columns, map_path=path)
    config.setdefault('require_valid_assets', True)
    config.setdefault('pilot_camera', True)
    if any(not isinstance(config[key], bool) for key in ('require_valid_assets', 'pilot_camera')):
        raise ValueError('Overview require_valid_assets and pilot_camera must be booleans')
    return config


def layout(items, columns=4, spacing=100):
    """Place differently sized meshes without overlap, independent of their pivots."""
    if not items:
        raise ValueError('Cannot build an empty overview')
    columns = min(columns, len(items))
    rows = math.ceil(len(items) / columns)
    width = max(x['max'][0] - x['min'][0] for x in items)
    depth = max(x['max'][1] - x['min'][1] for x in items)
    height = max(x['max'][2] - x['min'][2] for x in items)
    cell_x, cell_y = width + spacing, depth + spacing
    cells = []
    for index, item in enumerate(items):
        cx = (index % columns - (columns - 1) / 2) * cell_x
        cy = (index // columns - (rows - 1) / 2) * cell_y
        lo, hi = item['min'], item['max']
        cells.append(dict(item, location=[cx - (lo[0]+hi[0])/2, cy - (lo[1]+hi[1])/2, -lo[2]],
                          label_location=[cx, cy + depth/2 + spacing*0.28, 3]))
    return {'cells': cells, 'width': columns*cell_x, 'depth': rows*cell_y,
            'height': height, 'columns': columns, 'rows': rows}


def _engine():
    import unreal
    return unreal


def _current():
    u = _engine()
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    level = u.get_editor_subsystem(u.LevelEditorSubsystem).get_current_level()
    return world, level.get_outermost().get_name() if level else ''


def _safe_to_switch():
    u = _engine()
    from . import runtime
    runtime.assert_editor_idle()
    dirty = u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    if dirty:
        raise RuntimeError('Save or revert dirty maps before creating/opening an overview: ' +
                           ', '.join(p.get_name() for p in dirty))


def _owner(profile):
    return 'APP_Overview_' + profile['pack_id']


def _key(actor):
    keys = [str(t)[8:] for t in actor.tags if str(t).startswith('APP_Key_')]
    if len(keys) != 1:
        raise RuntimeError(f'Missing/duplicate generated actor key: {actor.get_actor_label()}')
    return keys[0]


def _actors(profile):
    u = _engine()
    result = {}
    for actor in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors():
        if _owner(profile) not in [str(t) for t in actor.tags]:
            continue
        key = _key(actor)
        if key in result:
            raise RuntimeError(f'Duplicate overview actor key: {key}')
        result[key] = actor
    return result


def _spawn(existing, profile, key, cls, location, rotation=None, folder='Scene'):
    u = _engine()
    actor = existing.get(key)
    if actor and not isinstance(actor, cls):
        raise RuntimeError(f'Overview actor type conflict: {key}')
    if actor is None:
        actor = u.get_editor_subsystem(u.EditorActorSubsystem).spawn_actor_from_class(cls, u.Vector(*location))
        if not actor:
            raise RuntimeError(f'Cannot spawn {key}')
        actor.tags = [u.Name(_owner(profile)), u.Name('APP_Key_' + key)]
        existing[key] = actor
    actor.modify()
    actor.set_actor_location(u.Vector(*location), False, False)
    actor.set_actor_rotation(rotation or u.Rotator(), False)
    actor.set_folder_path('AssetPackPipeline/' + folder)
    actor.set_actor_label(key)
    return actor


def _floor_material(profile):
    u = _engine()
    from . import runtime
    material, fresh = runtime._create(profile['destination_root'] + '/Materials/Overview/M_' +
                                      profile['pack_id'] + '_OverviewFloor', u.Material, u.MaterialFactoryNew(), profile['pack_id'])
    if fresh:
        mel = u.MaterialEditingLibrary
        color = mel.create_material_expression(material, u.MaterialExpressionConstant3Vector, -250, 0)
        color.constant = u.LinearColor(0.10, 0.12, 0.16, 1)
        mel.connect_material_property(color, '', u.MaterialProperty.MP_BASE_COLOR)
        roughness = mel.create_material_expression(material, u.MaterialExpressionConstant, -250, 150)
        roughness.r = 0.85
        mel.connect_material_property(roughness, '', u.MaterialProperty.MP_ROUGHNESS)
        errors = list(mel.recompile_material(material))
        if errors:
            raise RuntimeError(f'Overview floor material: {errors}')
        runtime.save(material)
    return material


def prepare(manifest, lod_review=False):
    """Validate every dependency and layout before touching the current map."""
    u = _engine()
    from . import runtime
    profile = manifest['profile']
    config = settings(profile, lod_review)
    items, checks = [], []
    for asset in manifest['assets']:
        check = runtime.inspect(manifest, asset)
        checks.append(check)
        if config['require_valid_assets'] and not check['passed']:
            raise RuntimeError(f'{asset["id"]}: asset validation failed; fix it or explicitly enable a diagnostic overview')
        mesh = u.load_asset(asset['mesh_path'])
        if not mesh or not runtime.owned(mesh, profile['pack_id']):
            raise RuntimeError(f'Missing or foreign mesh: {asset["mesh_path"]}')
        lo, hi = check['bounds_min'], check['bounds_max']
        if not all(math.isfinite(v) for v in lo + hi) or any(a >= b for a,b in zip(lo, hi)):
            raise ValueError(f'Invalid mesh bounds: {asset["id"]}')
        for lod in range(check['lod_count']) if lod_review else [None]:
            key = asset['id'] + (f'_LOD{lod}' if lod is not None else '')
            items.append({'id': key, 'mesh_path': asset['mesh_path'], 'lod': lod, 'min': lo, 'max': hi})
    # In review mode keep all levels of each asset on one row.
    columns = max(c['lod_count'] for c in checks) if lod_review else config['columns']
    planned = layout(items, columns, config['spacing'])
    path = config['map_path']
    if u.EditorAssetLibrary.does_asset_exist(path):
        world = u.load_asset(path)
        if not isinstance(world, u.World) or not runtime.owned(world, profile['pack_id']):
            raise RuntimeError(f'Foreign map conflict: {path}')
    floor_path = profile['destination_root'] + '/Materials/Overview/M_' + profile['pack_id'] + '_OverviewFloor'
    if u.EditorAssetLibrary.does_asset_exist(floor_path):
        floor = u.load_asset(floor_path)
        if not isinstance(floor, u.Material) or not runtime.owned(floor, profile['pack_id']):
            raise RuntimeError(f'Foreign floor material conflict: {floor_path}')
    return config, planned, checks


def build(manifest, backup_folder, lod_review=False):
    u = _engine()
    from . import runtime
    profile = manifest['profile']
    config, planned, checks = prepare(manifest, lod_review)
    _safe_to_switch()
    path = config['map_path']
    les = u.get_editor_subsystem(u.LevelEditorSubsystem)
    eas = u.get_editor_subsystem(u.EditorActorSubsystem)
    exists = u.EditorAssetLibrary.does_asset_exist(path)
    if exists:
        relative = path.removeprefix('/Game/')
        content = Path(u.Paths.project_content_dir()).resolve()
        for suffix in ('.umap', '_BuiltData.uasset'):
            original = content / (relative + suffix)
            if original.is_file():
                target = Path(backup_folder) / (relative + suffix)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
    if _current()[1] != path:
        gc.collect()
        if not (les.load_level(path) if exists else les.new_level(path)):
            raise RuntimeError(f'Cannot open/create {path}')
    world, current = _current()
    if current != path:
        raise RuntimeError(f'Unexpected current level: {current}')
    existing = _actors(profile)
    for key, actor in existing.items():
        if any(_owner(profile) not in [str(t) for t in child.tags] for child in actor.get_attached_actors()):
            raise RuntimeError(f'User actor attached to generated actor; detach it before regeneration: {key}')
    world.modify()
    runtime.mark(world, profile['pack_id'])
    expected_keys = set()
    for cell in planned['cells']:
        key = cell['id']
        expected_keys.update(('Mesh_' + key, 'Label_' + key))
        actor = _spawn(existing, profile, 'Mesh_' + key, u.StaticMeshActor, cell['location'], folder='Meshes')
        actor.static_mesh_component.set_static_mesh(u.load_asset(cell['mesh_path']))
        actor.static_mesh_component.set_forced_lod_model(0 if cell['lod'] is None else cell['lod'] + 1)
        actor.set_actor_scale3d(u.Vector(1, 1, 1))
        label = _spawn(existing, profile, 'Label_' + key, u.TextRenderActor, cell['label_location'],
                       u.Rotator(pitch=0, yaw=90, roll=0), folder='Labels')
        text = label.get_component_by_class(u.TextRenderComponent)
        text.set_text(key)
        text.set_world_size(config['label_size'])
        text.set_horizontal_alignment(u.HorizTextAligment.EHTA_CENTER)
        text.set_text_render_color(u.Color(210, 224, 247, 255))
    expected_keys.update(('Floor', 'KeyLight', 'SkyLight', 'Camera_Overview', 'Camera_Detail', 'Title', 'Exposure'))
    floor = _spawn(existing, profile, 'Floor', u.StaticMeshActor, [0, 0, -5])
    floor.static_mesh_component.set_static_mesh(u.load_asset('/Engine/BasicShapes/Cube'))
    floor.static_mesh_component.set_material(0, _floor_material(profile))
    light = _spawn(existing, profile, 'KeyLight', u.DirectionalLight, [0, 0, planned['height'] + 300],
                   u.Rotator(pitch=-45, yaw=60, roll=0))
    component = light.get_component_by_class(u.DirectionalLightComponent)
    component.set_mobility(u.ComponentMobility.MOVABLE)
    component.set_intensity(6.0)
    component.set_light_color(u.LinearColor(1, 0.94, 0.86, 1))
    sky = _spawn(existing, profile, 'SkyLight', u.SkyLight, [0, 0, planned['height'] + 200])
    sky_component = sky.get_component_by_class(u.SkyLightComponent)
    sky_component.set_mobility(u.ComponentMobility.MOVABLE)
    sky_component.set_editor_property('source_type', u.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    sky_component.set_editor_property('cubemap', u.load_asset('/Engine/MapTemplates/Sky/DaylightAmbientCubemap'))
    sky_component.set_intensity(1.1)
    exposure = _spawn(existing, profile, 'Exposure', u.PostProcessVolume, [0, 0, 0])
    exposure.set_editor_property('unbound', True)
    post = exposure.get_editor_property('settings')
    post.set_editor_property('override_auto_exposure_method', True)
    post.set_editor_property('auto_exposure_method', u.AutoExposureMethod.AEM_MANUAL)
    post.set_editor_property('override_auto_exposure_apply_physical_camera_exposure', True)
    post.set_editor_property('auto_exposure_apply_physical_camera_exposure', False)
    exposure.set_editor_property('settings', post)
    title = _spawn(existing, profile, 'Title', u.TextRenderActor,
                   [0, -planned['depth']/2 + config['spacing']*0.4, planned['height'] + 50],
                   u.Rotator(pitch=0, yaw=90, roll=0), folder='Labels')
    text = title.get_component_by_class(u.TextRenderComponent)
    text.set_text(profile['pack_id'] + (' | LOD REVIEW' if lod_review else ' | OVERVIEW'))
    text.set_world_size(config['label_size']*4)
    text.set_horizontal_alignment(u.HorizTextAligment.EHTA_CENTER)
    tan_horizontal = math.tan(math.radians(25))
    tan_vertical = tan_horizontal / (16/9)
    projected_height = planned['depth']*0.49 + (planned['height']+90)*0.87
    distance = max(planned['width']/2/tan_horizontal, projected_height/2/tan_vertical)*1.12 + planned['depth']*0.45
    target = u.Vector(0, 0, planned['height']*0.45)
    cameras = []
    for key, dist in [('Camera_Overview', distance), ('Camera_Detail', max(250, distance*0.5))]:
        position = u.Vector(0, dist*0.87, target.z+dist*0.49)
        rotation = u.MathLibrary.find_look_at_rotation(position, target)
        camera = _spawn(existing, profile, key, u.CameraActor, [position.x, position.y, position.z], rotation, folder='Cameras')
        camera.camera_component.set_editor_property('field_of_view', 50.0)
        camera.camera_component.set_editor_property('aspect_ratio', 16/9)
        cameras.append(camera)
    side = backdrop_floor_size(planned['width']+config['spacing'], planned['depth']+config['spacing'], distance)
    floor.set_actor_scale3d(u.Vector(side/100, side/100, 0.1))
    for key in set(existing) - expected_keys:
        actor = existing[key]
        if any(_owner(profile) not in [str(t) for t in child.tags] for child in actor.get_attached_actors()):
            raise RuntimeError(f'User actor attached to obsolete generated actor: {key}')
        if not eas.destroy_actor(actor):
            raise RuntimeError(f'Cannot remove obsolete actor: {key}')
    if not les.save_current_level():
        raise RuntimeError('Could not save overview map')
    if config['pilot_camera']:
        les.pilot_level_actor(cameras[0])
    result = validate_current(manifest, lod_review)
    result.update(layout=planned, asset_checks=checks, diagnostic=not all(c.get('strict_passed',c['passed']) for c in checks),
                  source_assets_valid=all(c.get('strict_passed',c['passed']) for c in checks), publication_ready=False,
                  visual_review='pending', lighting_validation='pending', backup_folder=str(backup_folder))
    return result


def open_map(manifest, lod_review=False):
    u = _engine()
    from . import runtime
    path = settings(manifest['profile'], lod_review)['map_path']
    _safe_to_switch()
    world = u.load_asset(path)
    if not world or not runtime.owned(world, manifest['profile']['pack_id']):
        raise RuntimeError(f'Overview missing or not owned by plugin: {path}')
    # Holding a World Python wrapper while LoadLevel reloads that package can
    # trigger UE's fatal world-leak check. Keep only the path across this call.
    del world
    gc.collect()
    les = u.get_editor_subsystem(u.LevelEditorSubsystem)
    if _current()[1] != path and not les.load_level(path):
        raise RuntimeError(f'Could not load overview: {path}')
    # Upgrade owned maps made by older versions, including render-only runs.
    ensure_backdrop_floor(manifest, lod_review)
    camera = _actors(manifest['profile']).get('Camera_Overview')
    if camera:
        les.pilot_level_actor(camera)
    return {'map_path': path, 'opened': True}


def ensure_backdrop_floor(manifest, lod_review=False):
    u = _engine()
    actors = _actors(manifest['profile'])
    floor = actors.get('Floor')
    if not floor:
        raise RuntimeError('Overview floor is missing; regenerate the scene')
    positions = [actor.get_actor_location() for key,actor in actors.items()
                 if key in ('Camera_Overview','Camera_Detail')]
    distance = max((math.sqrt(p.x*p.x+p.y*p.y+p.z*p.z) for p in positions),default=0)
    side = backdrop_floor_size(0, 0, distance)
    scale = floor.get_actor_scale3d()
    if scale.x*100+1 >= side and scale.y*100+1 >= side:return False
    floor.modify()
    floor.set_actor_scale3d(u.Vector(max(scale.x,side/100),max(scale.y,side/100),scale.z))
    if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
        raise RuntimeError('Could not save enlarged overview floor')
    return True


def validate_current(manifest, lod_review=False):
    u = _engine()
    config, planned, checks = prepare(manifest, lod_review)
    if _current()[1] != config['map_path']:
        raise RuntimeError('Open the target overview map before validating it')
    actors = _actors(manifest['profile'])
    cells = []
    for cell in planned['cells']:
        mesh = actors.get('Mesh_' + cell['id'])
        label = actors.get('Label_' + cell['id'])
        location = mesh.get_actor_location() if mesh else None
        position_ok = location is not None and all(abs(a-b) < 0.05 for a,b in zip(
            [location.x, location.y, location.z], cell['location']))
        mesh_ok = bool(mesh and mesh.static_mesh_component.static_mesh == u.load_asset(cell['mesh_path']))
        lod_ok = bool(mesh and mesh.static_mesh_component.get_editor_property('forced_lod_model') ==
                      (0 if cell['lod'] is None else cell['lod'] + 1))
        text = label.get_component_by_class(u.TextRenderComponent) if label else None
        label_ok = (text is not None and str(text.get_editor_property('text')) == cell['id']
                    and abs(label.get_actor_rotation().yaw - 90) < .05
                    and abs(label.get_actor_location().y - cell['label_location'][1]) < .05)
        cells.append({'id': cell['id'], 'status': 'passed' if mesh_ok and lod_ok and position_ok and label_ok else 'failed',
                      'mesh_ok': mesh_ok, 'forced_lod_ok': lod_ok, 'position_ok': position_ok, 'label_ok': label_ok,
                      'forced_lod': cell['lod']})
    expected = len(planned['cells'])*2 + 7
    infrastructure = all(k in actors for k in ('Floor', 'KeyLight', 'SkyLight', 'Camera_Overview', 'Camera_Detail', 'Title', 'Exposure'))
    orientation_ok = infrastructure and all(actors[k].get_actor_location().y > 0 and
        abs(actors[k].get_actor_rotation().yaw + 90) < .05 for k in ('Camera_Overview', 'Camera_Detail'))
    orientation_ok = orientation_ok and abs(actors['Title'].get_actor_rotation().yaw - 90) < .05
    return {'map_path': config['map_path'], 'owned_actor_count': len(actors), 'expected_actor_count': expected,
            'assets': cells, 'camera_text_orientation_ok': orientation_ok,
            'passed': infrastructure and orientation_ok and len(actors) == expected and all(c['status'] == 'passed' for c in cells),
            'visual_review': 'pending', 'lighting_validation': 'pending'}
