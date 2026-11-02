"""Standalone clean-project smoke. Intentionally imports no AssetPackPipeline code."""
import gc
import importlib.util
import json
from pathlib import Path
import unreal as u

folder = Path(__file__).resolve().parent
spec = json.loads((folder/'spec.json').read_text())
result = {'checks':{}, 'assets':[], 'scenes':[]}
try:
    descriptor = json.loads(Path(u.Paths.get_project_file_path()).read_text(encoding='utf-8-sig'))
    result['checks']['no_authoring_descriptor'] = not descriptor.get('AdditionalPluginDirectories') and not any(
        p.get('Name') in ('AssetPackPipeline','ModelContextProtocol','AllToolsets','ToolsetRegistry') for p in descriptor.get('Plugins',[]))
    result['checks']['no_pipeline_import'] = importlib.util.find_spec('asset_pack_pipeline') is None
    result['checks']['no_mcp_module'] = u.find_object(None,'/Script/ModelContextProtocol') is None
    result['checks']['no_toolset_module'] = u.find_object(None,'/Script/ToolsetRegistry') is None
    browser = u.get_editor_subsystem(u.ContentBrowserDataSubsystem)
    sources = [str(name) for name in browser.get_active_data_sources()] if browser else []
    result['content_browser_sources'] = sources
    result['checks']['content_browser_asset_source'] = any('AssetData' in name for name in sources)
    if any(c.get('nanite') for c in spec['asset_checks']):
        config_text = (Path(u.Paths.get_project_file_path()).parent/'Config/DefaultEngine.ini').read_text()
        result['checks']['nanite_render_config'] = all(value in config_text for value in (
            'DefaultGraphicsRHI=DefaultGraphicsRHI_DX12', '+D3D12TargetedShaderFormats=PCD3D_SM6',
            'r.Nanite.ProjectEnabled=True'))
    smes = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    mel = u.MaterialEditingLibrary
    for asset, expected in zip(spec['assets'],spec['asset_checks']):
        mesh = u.load_asset(asset['mesh_path'])
        checks = {'loaded': isinstance(mesh,u.StaticMesh)}
        if mesh:
            checks['triangles'] = [mesh.get_num_triangles(i) for i in range(smes.get_lod_count(mesh))] == expected['triangles']
            sizes = list(smes.get_lod_screen_sizes(mesh))
            checks['screen_sizes'] = len(sizes)==len(expected['screen_sizes']) and all(abs(a-b)<1e-5 for a,b in zip(sizes,expected['screen_sizes']))
            checks['nanite_mode'] = bool(mesh.get_editor_property('nanite_settings').enabled) == expected.get('nanite', False)
            if expected.get('nanite'):
                checks['nanite_data'] = mesh.get_num_nanite_triangles() == expected['nanite_triangles'] and expected['nanite_triangles'] > 0
                imported = list(mesh.get_editor_property('asset_import_data').extract_filenames())
                checks['detail_source_filename'] = bool(imported) and Path(imported[0]).name.lower() == Path(asset['lods'][0]['file']).name.lower()
                result.setdefault('nanite_source_evidence', []).append({'id': asset['id'],
                    'mesh_path': asset['mesh_path'], 'import_filenames': imported,
                    'expected_source': asset['lods'][0]['file'], 'nanite_triangles': mesh.get_num_nanite_triangles(),
                    'fallback_triangles': mesh.get_num_triangles(0)})
            checks['collision'] = smes.get_simple_collision_count(mesh)+smes.get_convex_collision_count(mesh)==expected['simple_collision_count']
            mi = mesh.get_material(0)
            checks['material'] = isinstance(mi,u.MaterialInstanceConstant) and isinstance(mi.get_editor_property('parent'),u.Material)
            checks['scalars'] = checks['material'] and all(abs(mel.get_material_instance_scalar_parameter_value(mi,k)-v)<1e-5
                                                          for k,v in expected['material_scalars'].items())
            checks['textures'] = checks['material'] and all(isinstance(mel.get_material_instance_texture_parameter_value(mi,k),u.Texture2D)
                                                           for k in ('BaseColor','Normal','ORM'))
        result['assets'].append({'id':asset['id'], 'checks':checks, 'passed':all(checks.values())})
    if spec.get('shared_representations'):
        grouped = {}
        for asset in spec['assets']:
            grouped.setdefault(asset['id'], []).append(u.load_asset(asset['mesh_path']))
        result['checks']['both_representations'] = all(len(pair) == 2 and all(pair) for pair in grouped.values())
        result['checks']['shared_instances'] = all(len(pair) == 2 and pair[0].get_material(0) == pair[1].get_material(0)
                                                   for pair in grouped.values())
        content = Path(u.Paths.project_content_dir())
        result['checks']['one_master'] = len(list(content.rglob('M_*_Master.uasset'))) == 1
        result['checks']['one_instance_per_model'] = len(list(content.rglob('MI_*.uasset'))) == len(grouped)
    for scene in spec['scenes']:
        gc.collect()
        les = u.get_editor_subsystem(u.LevelEditorSubsystem)
        if not les.load_level(scene['map_path']):
            raise RuntimeError('Could not open copied map: '+scene['map_path'])
        actors = {}
        for actor in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors():
            if 'APP_Overview_'+spec['pack_id'] in [str(tag) for tag in actor.tags]:
                for tag in actor.tags:
                    if str(tag).startswith('APP_Key_'):
                        actors[str(tag)[8:]] = actor
        checks = {'actor_count':len(actors)==scene['expected_actor_count']}
        for cell in scene['cells']:
            actor = actors.get('Mesh_'+cell['id'])
            checks[cell['id']] = bool(actor and actor.static_mesh_component.static_mesh == u.load_asset(cell['mesh_path'])
                and actor.static_mesh_component.get_editor_property('forced_lod_model') == (0 if cell['lod'] is None else cell['lod']+1))
        result['scenes'].append({'map_path':scene['map_path'], 'checks':checks, 'passed':all(checks.values())})
        actors.clear()
    result['passed'] = all(result['checks'].values()) and all(a['passed'] for a in result['assets']+result['scenes'])
except Exception as error:
    import traceback
    result.update(passed=False, error=str(error), traceback=traceback.format_exc())
    u.log_error(result['traceback'])
(folder/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
