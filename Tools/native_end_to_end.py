"""Isolated real-asset regression. Never run in the user's authoring project."""
import json
import sys
import time
import uuid
from pathlib import Path
import unreal as u
from asset_pack_pipeline import api, guided, cleanup

u.EditorPythonScripting.set_keep_python_script_alive(True)
assert Path(u.Paths.get_project_file_path()).stem=='HostProject', 'Isolated HostProject required'
run = uuid.uuid4().hex
out = Path(u.Paths.project_saved_dir()).resolve()/'AssetPackPipeline'/'E2E'/run
out.mkdir(parents=True)
base = json.loads((Path(__file__).resolve().parents[3]/'Plugins/AssetPackPipeline/Content/Profiles/profile.example.json').read_text())
pack = 'NativeRegression_'+run[:8]
profiles, steps = guided.prepare(base, r'D:\Work\3D Stocks\3D Asset Packs\!NewAssetPack\15_Containers_Ready\!Unreal',
    pack,'FBX',renders=['overview'],finalize=True,output=str(out/'Deliveries'))
paths = {}
for name,p in profiles.items():
    if '-pipelinefullpack' not in u.SystemLibrary.get_command_line().lower():
        p['asset_ids'] = ['Containers_01_02']
    p['previews'].update(width=1280,height=720,warmup_seconds=2)
    path = out/(name+'.json')
    path.write_text(json.dumps(p,indent=2),encoding='utf-8')
    paths[name] = str(path)
session = guided.Session(api,paths,steps)
start = time.monotonic()
last = 0
busy = False
result = {'pack':pack,'passed':False,'tkinter_loaded':False,'cycles':0}

def finish():
    u.unregister_slate_post_tick_callback(handle)
    result['passed'] = result['passed'] and not session.error
    result.update(seconds=time.monotonic()-start,stage=session.label,error=session.error,result=session.result)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (out.parent/'latest.json').write_text(json.dumps({'report':str(out/'result.json')},indent=2),encoding='utf-8')
    u.SystemLibrary.quit_editor()

def tick(delta):
    global last, busy
    if busy: return
    now=time.monotonic()
    if now-last<.5: return
    last=now
    busy=True
    try:
        assert 'tkinter' not in sys.modules
        session.tick()
        (out/'progress.json').write_text(json.dumps({'stage':session.label,'seconds':now-start}),encoding='utf-8')
        if not api.readiness()['active_run']:
            u.AssetPackPipelineNative.open_window()
            assert u.AssetPackPipelineNative.is_window_open()
            u.AssetPackPipelineNative.close_window()
            result['cycles']+=1
        if session.done:
            if not session.error:
                assert session.result and Path(session.result['zip_path']).is_file()
                assert session.result['renders']['count']==1
                # Only delete our generated pack, after moving away from its generated map.
                u.EditorLoadingAndSavingUtils.new_blank_map(False)
                assert u.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
                manifest={'profile':{'pack_id':pack,'destination_root':'/Game/'+pack}}
                proposal=cleanup.plan(manifest,imported=True)
                result['cleanup']=cleanup.execute(manifest,out/'cleanup_backup',imported=True,expected=proposal['delete_packages'])
                assert result['cleanup']['passed']
                result['passed']=True
            finish()
        elif now-start>1200:
            session.cancel(); session.error='E2E timeout'; finish()
    except Exception as error:
        session.error=str(error)
        finish()
    finally:
        busy=False
handle=u.register_slate_post_tick_callback(tick)
