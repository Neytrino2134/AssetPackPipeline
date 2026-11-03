"""Per-model stills, framed from bounds, in an isolated owned studio map."""
import copy
import math
import time
from . import previews


def settings(profile):
    from . import lighting, render_views
    profile = dict(profile, lod_screen_sizes=[1.0]) if profile.get('nanite_enabled', False) else profile
    value=dict(profile.get('media',{}))
    value['view_modes']=render_views.settings(profile.get('previews',{}).get('view_modes'))
    value.setdefault('yaw_angles',[90,120])
    # Upgrade shipped rear-facing presets; other explicit views remain custom.
    if value['yaw_angles'] == [-60,120]:value['yaw_angles']=[90,120]
    elif value['yaw_angles'] == [-60]:value['yaw_angles']=[90]
    if not isinstance(value['yaw_angles'],list) or not 1<=len(value['yaw_angles'])<=12:
        raise ValueError('media.yaw_angles requires 1..12 angles')
    for angle in value['yaw_angles']:
        if isinstance(angle,bool) or not isinstance(angle,(int,float)) or not math.isfinite(angle) or not -360<=angle<=360:
            raise ValueError('Media yaw angles must be finite degrees in [-360,360]')
    for key,default,low,high in [('pitch',15,0,65),('fov',40,15,90),('margin',1.18,1.05,2)]:
        number=float(value.get(key,default))
        if not math.isfinite(number) or not low<=number<=high:raise ValueError('Invalid media '+key)
        value[key]=number
    value.update(lighting.settings(profile))
    value.setdefault('include_invalid',False)
    value.setdefault('lod_index',0)
    if not isinstance(value['include_invalid'],bool):raise ValueError('media.include_invalid must be boolean')
    if isinstance(value['lod_index'],bool) or not isinstance(value['lod_index'],int) or not 0<=value['lod_index']<len(profile['lod_screen_sizes']):
        raise ValueError('Invalid media LOD index')
    indices=value.get('lod_indices',[value['lod_index']])
    if (not isinstance(indices,list) or not indices or len(indices)!=len(set(str(i) for i in indices)) or
        any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(profile['lod_screen_sizes']) for i in indices)):
        raise ValueError('media.lod_indices must contain distinct valid LOD indices')
    value['lod_indices']=indices
    return value


def frame_rows(assets,checks,config,folder,studio):
    from pathlib import Path
    rows=[]
    for asset,check in zip(assets,checks):
        for i,angle in enumerate(config['yaw_angles']):
            for lod in config['lod_indices']:
                suffix=(f'_LOD{lod}' if len(config['lod_indices'])>1 else '')+f'_v{i:02d}'
                rows.append({'id':asset['id']+suffix,'asset_id':asset['id'],'yaw':angle,'view_index':i,
                    'lod_index':lod,'status':'pending','map_path':studio,
                    'output_path':str(Path(folder)/(asset['id']+('_diagnostic' if not check.get('strict_passed',check['passed']) else '')+suffix+'.png'))})
    from . import render_views
    return render_views.expand(rows,config.get('view_modes'),config.get('frame_views'))


def _backdrop(actors,profile,studio):
    import unreal as u
    from . import runtime,overview
    material,fresh=runtime._create(studio.rsplit('/',1)[0]+'/M_Backdrop',u.Material,u.MaterialFactoryNew(),profile['pack_id'])
    if fresh:
        material.set_editor_property('two_sided',True)
        material.set_editor_property('shading_model',u.MaterialShadingModel.MSM_UNLIT)
        mel=u.MaterialEditingLibrary
        color=mel.create_material_expression(material,u.MaterialExpressionConstant3Vector,-250,0)
        color.constant=u.LinearColor(.035,.045,.065,1)
        mel.connect_material_property(color,'',u.MaterialProperty.MP_EMISSIVE_COLOR)
        errors=list(mel.recompile_material(material))
        if errors:raise RuntimeError('Studio background material: '+str(errors))
        runtime.save(material)
    actor=overview._spawn(actors,profile,'StudioBackdrop',u.StaticMeshActor,[0,0,0])
    actor.static_mesh_component.set_static_mesh(u.load_asset('/Engine/BasicShapes/Sphere'))
    actor.static_mesh_component.set_material(0,material)
    actor.set_actor_enable_collision(False)
    actor.static_mesh_component.set_collision_profile_name('NoCollision')
    actor.static_mesh_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    actor.static_mesh_component.set_editor_property('cast_shadow',False)
    actor.set_actor_scale3d(u.Vector(200,200,200))


def frame(bounds_min,bounds_max,yaw,pitch,fov,aspect,margin):
    ext=[(b-a)/2 for a,b in zip(bounds_min,bounds_max)]
    if any(not math.isfinite(v) or v<=0 for v in ext):raise ValueError('Invalid framing bounds')
    az,el=math.radians(yaw),math.radians(pitch)
    width=abs(math.sin(az))*ext[0]+abs(math.cos(az))*ext[1]
    depth=abs(math.cos(az))*ext[0]+abs(math.sin(az))*ext[1]
    height=ext[2]*math.cos(el)+depth*math.sin(el)
    tangent=math.tan(math.radians(fov)/2)
    distance=max(width/tangent,height*aspect/tangent)*margin+depth*math.cos(el)+ext[2]*math.sin(el)
    # Studio layout centres the bounds at X/Y=0 and rests the bottom at Z=0.
    target=[0,0,ext[2]]
    position=[distance*math.cos(el)*math.cos(az),distance*math.cos(el)*math.sin(az),target[2]+distance*math.sin(el)]
    return {'position':position,'target':target,'distance':distance}


def collision_audit(camera,actor,floor,expected=True):
    import unreal as u
    origin,extent=actor.get_actor_bounds(False)
    # A multi-hull collider may have a legitimate hole at the mesh bounds centre.
    body=actor.static_mesh_component.static_mesh.get_editor_property('body_setup')
    convex=body.get_editor_property('agg_geom').get_editor_property('convex_elems')
    probe='bounds_center'
    if expected and convex:
        centroid=u.AssetPackPipelineNative.get_collision_probe(actor.static_mesh_component.static_mesh)
        origin=u.MathLibrary.transform_location(actor.get_actor_transform(),centroid)
        probe='convex_hull_centroid'
    checks=[]
    for axis in range(3):
        a=[origin.x,origin.y,origin.z];b=list(a)
        reach=[extent.x,extent.y,extent.z][axis]*2+10
        a[axis]-=reach;b[axis]+=reach
        values=u.SystemLibrary.line_trace_single(camera,u.Vector(*a),u.Vector(*b),
            u.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[floor],u.DrawDebugTrace.NONE,True)
        data=values if isinstance(values,u.HitResult) else next((v for v in (values or []) if isinstance(v,u.HitResult)),None)
        hit=False
        hit_actor=None
        if data:
            parts=data.to_tuple()
            hit=bool(parts[0])
            hit_actor=next((v for v in parts if isinstance(v,u.Actor)),None)
        checks.append({'axis':'XYZ'[axis],'blocking_hit':hit,'expected_actor':hit_actor==actor,
                       'hit_actor':hit_actor.get_path_name() if hit_actor else None})
    return {'simple_collision_traces':checks,'expected_blocking':expected,'probe':probe,
            'passed':all(c['blocking_hit'] and c['expected_actor'] if expected else not c['blocking_hit'] for c in checks)}


def advance(report,state):
    import unreal as u
    from . import overview
    from . import render_quality
    row=next((a for a in report['assets'] if a['status'] in ('pending','running')),None)
    if row is None:render_quality.restore();return True
    if report['cancel_requested'] and 'task' not in state:
        for item in report['assets']:
            if item['status'] in ('pending','running'):item['status']='cancelled'
        render_quality.restore()
        return True
    config=report['media_settings'];capture=report['preview_settings'];now=time.monotonic()
    if 'task' in state:render_quality.select_view(row.get('render_view','lit'))
    if row['status']=='pending':
        render_quality.select_view(row.get('render_view','lit'))
        asset=next(a for a in report['manifest']['assets'] if a['id']==row['asset_id'])
        check=next(a for a in report['source_asset_checks'] if a['id']==row['asset_id'])
        manifest=copy.deepcopy(report['manifest'])
        manifest['assets']=[asset]
        manifest['profile']['asset_ids']=[asset['id']]
        manifest['profile'].setdefault('overview',{}).update(columns=1,spacing=60,require_valid_assets=not config['include_invalid'],
             pilot_camera=False,map_path_override=row['map_path'])
        if state.get('asset_id')!=asset['id']:
            built=overview.build(manifest,report['studio_backup'])
            if not built['passed']:raise RuntimeError('Studio generation failed')
            state['asset_id']=asset['id']
        overview._safe_to_switch()
        actors=overview._actors(manifest['profile'])
        for key,actor in actors.items():
            if key=='Title' or key.startswith('Label_'):
                actor.set_actor_hidden_in_game(True)
                actor.set_is_temporarily_hidden_in_editor(True)
        camera=actors['Camera_Overview']
        framing=frame(check['bounds_min'],check['bounds_max'],row['yaw'],config['pitch'],config['fov'],
                      capture['width']/capture['height'],config['margin'])
        if row.get('automatic_lod'):
            from . import auto_lod
            length=auto_lod.distance(check['sphere_radius'],row['target_screen_size'])
            direction=[(p-t)/framing['distance'] for p,t in zip(framing['position'],framing['target'])]
            framing.update(position=[t+d*length for t,d in zip(framing['target'],direction)],distance=length)
        position=u.Vector(*framing['position']);target=u.Vector(*framing['target'])
        camera.set_actor_location(position,False,False)
        camera.set_actor_rotation(u.MathLibrary.find_look_at_rotation(position,target),False)
        camera.camera_component.set_editor_property('field_of_view',config['fov'])
        camera.camera_component.set_editor_property('aspect_ratio',capture['width']/capture['height'])
        if report.get('automatic_lod_review'):camera.camera_component.set_editor_property('constrain_aspect_ratio',True)
        mesh=actors['Mesh_'+asset['id']]
        forced=0 if row.get('automatic_lod') or manifest['profile'].get('nanite_enabled', False) else row['lod_index']+1
        mesh.static_mesh_component.set_forced_lod_model(forced)
        if mesh.static_mesh_component.get_editor_property('forced_lod_model')!=forced:
            raise RuntimeError('Forced LOD read-back failed')
        light=actors['KeyLight']
        from .lighting import apply_key
        apply_key(light,camera,u)
        light.get_component_by_class(u.DirectionalLightComponent).set_intensity(config['key_intensity'])
        actors['SkyLight'].get_component_by_class(u.SkyLightComponent).set_intensity(config['sky_intensity'])
        actors['Floor'].set_actor_scale3d(u.Vector(1000,1000,.1))
        _backdrop(actors,manifest['profile'],row['map_path'])
        if report.get('automatic_lod_review'):
            for key in ('Floor','StudioBackdrop'):
                actors[key].set_actor_hidden_in_game(row['capture_mode']=='lod_color')
                actors[key].set_is_temporarily_hidden_in_editor(row['capture_mode']=='lod_color')
        post=actors['Exposure'].get_editor_property('settings')
        post.set_editor_property('override_auto_exposure_bias',True)
        post.set_editor_property('auto_exposure_bias',config['exposure_bias'])
        actors['Exposure'].set_editor_property('settings',post)
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Could not save studio')
        u.get_editor_subsystem(u.LevelEditorSubsystem).pilot_level_actor(camera)
        render_quality.apply()
        render_quality.prestream([mesh],capture['warmup_seconds'])
        row.update(status='running',camera=framing,source_asset_valid=check.get('strict_passed',check['passed']),
                   diagnostic=not check.get('strict_passed',check['passed']),warnings=check.get('warnings',[]),
                   representation='Nanite' if check['nanite'] else 'LOD',
                   forced_lod_verified=True,forced_lod_model=forced,collision_expected=check['simple_collision_count']>0)
        state.update(started=now,warm_until=now+capture['warmup_seconds'])
        return False
    if now-state['started']>capture['timeout_seconds']:state['timed_out']=True
    if 'task' not in state:
        if state.get('timed_out'):raise RuntimeError('Media warmup timeout')
        if now<state['warm_until']:return False
        overview._safe_to_switch()
        if overview._current()[1]!=row['map_path']:raise RuntimeError('Studio map changed')
        camera=overview._actors(report['manifest']['profile'])['Camera_Overview']
        actors=overview._actors(report['manifest']['profile'])
        if report.get('automatic_lod_review') and not row.get('actual_lod_verified'):
            from . import auto_lod
            try:
                if not auto_lod.advance_stats(report,row,state,camera):return False
            except Exception as error:
                row.update(status='failed',error=str(error));raise
        if 'collision_audit' not in row:
            try:row['collision_audit']=collision_audit(camera,actors['Mesh_'+row['asset_id']],actors['Floor'],row['collision_expected'])
            except Exception as error:row['collision_audit']={'passed':False,'unverified':True,'error':str(error)}
        if not row['collision_audit']['passed']:raise RuntimeError('Studio collision audit failed: '+str(row['collision_audit']))
        row['viewport_mode_verified']=render_quality.select_view(row.get('render_view','lit'))
        task=u.AutomationLibrary.take_high_res_screenshot(capture['width'],capture['height'],row['output_path'],camera,delay=1,
            force_game_view=not(report.get('automatic_lod_review') and row['capture_mode']=='lod_color'))
        if not task or not task.is_valid_task():raise RuntimeError('Unreal rejected media screenshot')
        state['task']=task
        render_quality.select_view(row.get('render_view','lit'))
        return False
    if not state['task'].is_task_done():
        if now-state['started']>capture['timeout_seconds']+previews.STALL_GRACE_SECONDS:raise RuntimeError(previews.STALL_MESSAGE)
        return False
    state.pop('task')
    if state.get('timed_out') or overview._current()[1]!=row['map_path']:raise RuntimeError('Media capture timed out or map changed')
    row.update(previews.inspect_png(row['output_path'],capture['width'],capture['height']),status='passed')
    state.pop('timed_out',None)
    return False
