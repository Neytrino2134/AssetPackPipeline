"""Saved camera animation and full-rate Movie Render Queue frames, with an isolated queue."""
import copy
import json
import math
import re
import time
from pathlib import Path


def settings(profile):
    value=dict(profile.get('flythrough',{}))
    if value.get('yaw_start') == -115 and value.get('yaw_end') == -65:
        value.update(yaw_start=65,yaw_end=115)
    for key,default,low,high in [('fps',24,12,60),('width',1280,256,3840),('height',720,256,2160)]:
        n=value.get(key,default)
        if isinstance(n,bool) or not isinstance(n,int) or not low<=n<=high:raise ValueError('Invalid flythrough '+key)
        value[key]=n
    for key,default,low,high in [('seconds',8,2,60),('yaw_start',65,-180,180),('yaw_end',115,-180,180),
                               ('pitch',25,10,60),('fov',50,25,80),('margin',1.2,1.1,2)]:
        n=value.get(key,default)
        if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not low<=n<=high:
            raise ValueError('Invalid flythrough '+key)
        value[key]=float(n)
    if abs(value['yaw_end']-value['yaw_start'])<5 or abs(value['yaw_end']-value['yaw_start'])>170:
        raise ValueError('Flythrough yaw sweep must be 5..170 degrees')
    value['frame_count']=round(value['seconds']*value['fps'])
    value['seconds']=value['frame_count']/value['fps']
    if value['frame_count']>1800:raise ValueError('Flythrough exceeds 1800 frames')
    value['timeout_seconds']=max(600,value['seconds']*60)
    return value


def poses(lo,hi,config):
    from . import media
    center=[(a+b)*.5 for a,b in zip(lo,hi)]
    result=[]
    for i in range(config['frame_count']):
        t=i/(config['frame_count']-1)
        yaw=config['yaw_start']+(config['yaw_end']-config['yaw_start'])*t
        framing=media.frame(lo,hi,yaw,config['pitch'],config['fov'],config['width']/config['height'],config['margin'])
        # media.frame assumes a mesh centered on XY and grounded at Z=0.
        p=framing['position'];p=[p[0]+center[0],p[1]+center[1],p[2]+lo[2]]
        d=[c-v for c,v in zip(center,p)]
        look_yaw=math.degrees(math.atan2(d[1],d[0]))
        if result:
            previous=result[-1]['rotation'][2]
            while look_yaw-previous>180:look_yaw-=360
            while look_yaw-previous<-180:look_yaw+=360
        result.append({'frame':i,'position':p,'rotation':[0,math.degrees(math.atan2(d[2],math.hypot(d[0],d[1]))),look_yaw]})
    return result


def build(manifest,run_id,config,backup):
    import unreal as u
    from . import overview,runtime
    scene=copy.deepcopy(manifest)
    scene['profile'].setdefault('overview',{}).update(map_path_override=f'/Game/AssetPackPipeline_Previews/{run_id}/Studio',
                                                   pilot_camera=False,require_valid_assets=True)
    built=overview.build(scene,backup)
    if not built['passed']:raise RuntimeError('Flythrough overview did not pass read-back')
    actors=overview._actors(scene['profile'])
    expected={a['id']:a['mesh_path'] for a in manifest['assets']}
    actual={key[5:]:actor.static_mesh_component.static_mesh.get_path_name().split('.')[0]
            for key,actor in actors.items() if key.startswith('Mesh_')}
    if actual!=expected:raise RuntimeError('Flythrough scene does not contain every catalog mesh')
    for key,actor in actors.items():
        if key.startswith('Mesh_'):
            actor.static_mesh_component.set_forced_lod_model(0)
            if actor.static_mesh_component.get_editor_property('forced_lod_model')!=0:raise RuntimeError('Automatic LOD setup failed')
    cells=built['layout']['cells']
    lo=[min(c['min'][i]+c['location'][i] for c in cells) for i in range(3)]
    hi=[max(c['max'][i]+c['location'][i] for c in cells) for i in range(3)]
    hi[2]+=90 # include title/labels, in addition to the complete model bounds
    route=poses(lo,hi,config)
    camera=u.get_editor_subsystem(u.EditorActorSubsystem).spawn_actor_from_class(u.CameraActor,u.Vector(*route[0]['position']))
    camera.set_actor_label('APP_FlythroughCamera')
    camera.set_actor_rotation(u.Rotator(pitch=route[0]['rotation'][1],yaw=route[0]['rotation'][2],roll=0),False)
    camera.tags=[u.Name('APP_Flythrough_'+run_id)]
    camera.camera_component.set_field_of_view(config['fov'])
    camera.camera_component.set_editor_property('constrain_aspect_ratio',True)
    camera.camera_component.set_editor_property('aspect_ratio',config['width']/config['height'])
    path=f'/Game/AssetPackPipeline_Previews/{run_id}/LS_Flythrough'
    sequence=u.AssetToolsHelpers.get_asset_tools().create_asset('LS_Flythrough',path.rsplit('/',1)[0],u.LevelSequence,u.LevelSequenceFactoryNew())
    if not sequence:raise RuntimeError('Could not create flythrough sequence')
    runtime.mark(sequence,manifest['profile']['pack_id'])
    sequence.set_display_rate(u.FrameRate(config['fps'],1))
    sequence.set_playback_start(0);sequence.set_playback_end(config['frame_count'])
    binding=sequence.add_possessable(camera)
    section=binding.add_track(u.MovieScene3DTransformTrack).add_section()
    section.set_range(0,config['frame_count'])
    channels=u.MovieSceneSectionExtensions.get_all_channels(section)
    if len(channels)!=9:raise RuntimeError('Unexpected camera transform channel layout')
    for pose in route:
        values=pose['position']+pose['rotation']+[1,1,1]
        for channel,value in zip(channels,values):
            channel.add_key(u.FrameNumber(pose['frame']),value,interpolation=u.MovieSceneKeyInterpolation.LINEAR)
    cut=sequence.add_track(u.MovieSceneCameraCutTrack).add_section()
    cut.set_range(0,config['frame_count']);cut.set_camera_binding_id(sequence.get_binding_id(binding))
    runtime.save(sequence)
    if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Cannot save flythrough map')
    return {'map_path':scene['profile']['overview']['map_path_override'],'sequence_path':path,
            'model_ids':list(expected),'route':route,'bounds_min':lo,'bounds_max':hi,
            'source_asset_checks':built['asset_checks']}


def launch(report,state):
    import unreal as u
    config=report['flythrough_settings']
    subsystem=u.get_editor_subsystem(u.MoviePipelineQueueSubsystem)
    if subsystem.is_rendering():raise RuntimeError('Movie Render Queue is already rendering')
    queue=u.new_object(u.MoviePipelineQueue)
    job=queue.allocate_new_job(u.MoviePipelineExecutorJob)
    job.job_name='AssetPackFlythrough'
    job.map=u.SoftObjectPath(report['map_path']);job.sequence=u.SoftObjectPath(report['sequence_path'])
    preset=job.get_configuration()
    output=preset.find_or_add_setting_by_class(u.MoviePipelineOutputSetting)
    output.output_directory=u.DirectoryPath(report['output_directory'])
    output.file_name_format='frame_{frame_number}'
    output.output_resolution=u.IntPoint(config['width'],config['height'])
    output.use_custom_frame_rate=True;output.output_frame_rate=u.FrameRate(config['fps'],1)
    output.output_frame_step=1;output.zero_pad_frame_numbers=4
    output.override_existing_output=False;output.flush_disk_writes_per_shot=True
    preset.find_or_add_setting_by_class(u.MoviePipelineImageSequenceOutput_PNG)
    preset.find_or_add_setting_by_class(u.MoviePipelineDeferredPassBase)
    from . import render_quality
    render_quality.movie_pipeline(preset)
    executor=u.new_object(u.MoviePipelinePIEExecutor)
    def finished(obj,success):state.update(finished=True,success=bool(success))
    def errored(obj,pipeline,fatal,message):
        report.setdefault('render_messages',[]).append({'fatal':bool(fatal),'message':str(message)})
    executor.on_executor_finished_delegate.add_callable(finished)
    executor.on_executor_errored_delegate.add_callable(errored)
    state.update(queue=queue,executor=executor,callbacks=(finished,errored),started=time.monotonic())
    subsystem.render_queue_instance_with_executor_instance(queue,executor)


def finish(report):
    from . import previews
    config=report['flythrough_settings'];folder=Path(report['output_directory'])
    frames=sorted(folder.glob('frame_*.png'))
    indices=[int(re.fullmatch(r'frame_(\d+)\.png',p.name)[1]) for p in frames]
    if indices!=list(range(config['frame_count'])):raise RuntimeError('Flythrough frames are missing, duplicated or out of range')
    rows=[dict(previews.inspect_png(p,config['width'],config['height']),frame=i,file=p.name) for i,p in enumerate(frames)]
    if len({r['sha256'] for r in rows})<len(rows)*.9:raise RuntimeError('Flythrough output is static or has repeated frames')
    report['frames']=rows
    verify_originals(report)
    data={'fps':config['fps'],'frames':[r['file'] for r in rows],'model_ids':report['model_ids'],
          'source_asset_checks':report['source_asset_checks'],'publication_ready':False}
    (folder/'playback.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    html='''<!doctype html><meta charset="utf-8"><title>Asset Pack — continuous flythrough</title><style>body{background:#171a20;color:#eee;font:16px system-ui;margin:24px}img{display:block;max-width:100%;max-height:75vh}button,input{margin:10px}input{width:min(75vw,1000px)}pre{white-space:pre-wrap}</style><h1>Continuous camera flythrough</h1><p>All catalog models remain present, including models with geometry warnings. Every output frame was rendered by Unreal Movie Render Queue; this is a PNG sequence player, not an encoded video. Appearance/publication approval is pending.</p><img id="frame"><button id="play">Play / pause</button><input id="seek" type="range" min="0" value="0"><span id="time"></span><details><summary>Models and warnings</summary><pre id="checks"></pre></details><script>const data=__DATA__;const img=document.getElementById('frame'),seek=document.getElementById('seek');seek.max=data.frames.length-1;let playing=false,start=0;function show(i){seek.value=i;img.src=data.frames[i];document.getElementById('time').textContent=(i/data.fps).toFixed(2)+' s / '+(data.frames.length/data.fps).toFixed(2)+' s';for(let j=1;j<=3;j++){let next=new Image();next.src=data.frames[(i+j)%data.frames.length]}}function tick(t){if(playing)show(Math.floor((t-start)*data.fps/1000)%data.frames.length);requestAnimationFrame(tick)}document.getElementById('play').onclick=()=>{playing=!playing;start=performance.now()-Number(seek.value)*1000/data.fps};seek.oninput=()=>{playing=false;show(Number(seek.value))};document.getElementById('checks').textContent=JSON.stringify({models:data.model_ids,checks:data.source_asset_checks},null,2);show(0);requestAnimationFrame(tick);</script>'''
    (folder/'playback.html').write_text(html.replace('__DATA__',json.dumps(data).replace('</','<\\/')),encoding='utf-8')
    report['playback_page']=str(folder/'playback.html')


def advance(report,state):
    if report['cancel_requested'] and not state.get('cancel_sent'):
        state['executor'].cancel_all_jobs();state['cancel_sent']=True
    if time.monotonic()-state['started']>report['flythrough_settings']['timeout_seconds'] and not state.get('timed_out'):
        state['executor'].cancel_all_jobs();state['timed_out']=True
    if not state.get('finished'):return False
    if state.get('timed_out'):raise RuntimeError('Flythrough rendering timed out')
    if report['cancel_requested']:
        verify_originals(report)
        return True
    if not state.get('success') or any(r['fatal'] for r in report.get('render_messages',[])):
        raise RuntimeError('Movie Render Queue reported a rendering failure')
    finish(report)
    return True


def verify_originals(report):
    from . import discovery
    report['source_files_unchanged']=all(Path(p).is_file() and discovery.digest(p)==sha for p,sha in report['manifest']['source_hashes'].items())
    report['original_packages_unchanged']=all(Path(p).is_file() and discovery.digest(p)==sha for p,sha in report['original_package_hashes'].items())
    if not report['source_files_unchanged'] or not report['original_packages_unchanged']:raise RuntimeError('Original inputs changed during flythrough')


def release(state):
    if state.get('callbacks'):
        finished,errored=state.pop('callbacks')
        state['executor'].on_executor_finished_delegate.remove_callable(finished)
        state['executor'].on_executor_errored_delegate.remove_callable(errored)
