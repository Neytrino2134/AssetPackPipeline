"""Real process-isolation and reconnect smoke, restricted to HostProject."""
import json
import sys
import time
import uuid
from pathlib import Path
import unreal as u
from asset_pack_pipeline import custom_server as server
from asset_pack_pipeline import guided,api,native_bridge,cleanup
u.EditorPythonScripting.set_keep_python_script_alive(True)
assert Path(u.Paths.get_project_file_path()).stem=='HostProject'
assert Path(u.Paths.get_project_file_path()).resolve().is_relative_to(Path(__file__).resolve().parents[3]/'Saved'), 'Project must be an isolated workspace Saved test host'
out=Path(u.Paths.project_saved_dir())/'AssetPackPipeline/CustomSmoke.json'
out.parent.mkdir(parents=True,exist_ok=True)
result={'passed':False}
pack='CustomRegression_'+uuid.uuid4().hex[:8]
base=json.loads((Path(__file__).resolve().parents[3]/'Plugins/AssetPackPipeline/Content/Profiles/profile.example.json').read_text())
profiles,_=guided.prepare(base,r'D:\Work\3D Stocks\3D Asset Packs\!NewAssetPack\15_Containers_Ready\!Unreal',pack,'FBX')
paths={}
for name,p in profiles.items():
    p['asset_ids']=['Containers_01_02']
    path=out.parent/(pack+'_'+name+'.json');path.write_text(json.dumps(p),encoding='utf-8');paths[name]=str(path)
steps=[(name,'import') for name in paths]+[(name,'validate') for name in paths]
started=time.monotonic();phase=0;busy=False
def tick(delta):
    global phase,busy,started
    if busy:return
    busy=True
    try:
        assert 'tkinter' not in sys.modules,'Tkinter loaded in Unreal'
        if phase==0:
            result['first']=server.launch({'paths':paths,'steps':steps});phase=1
        marker=server.directory()/'client-status.json'
        if phase==1 and marker.is_file():
            status=json.loads(marker.read_text())
            assert status['pid']==server._process.pid
            assert status['tkinter_loaded'] and not status['unreal_loaded'] and status.get('rpc_connected')
            assert status['probe_started']
            result['isolated']=status
            assert server.launch()['already_open']
            # Simulate only our test Custom UI process failing; Unreal must survive.
            server._process.terminate();server._process.wait(timeout=5)
            marker.unlink();phase=2
        elif phase==2:
            result['second']=server.launch();phase=3
        elif phase==3 and marker.is_file():
            status=json.loads(marker.read_text())
            assert status['pid']==server._process.pid and status['pid']!=result['first']['pid']
            result.update(reconnected=status,unreal_tkinter_loaded='tkinter' in sys.modules)
            server._process.terminate();server._process.wait(timeout=5)
            phase=4
        elif phase==4 and native_bridge._session and native_bridge._session.done:
            assert not native_bridge._session.error,native_bridge._session.error
            assert all(api.validate(p)['passed'] for p in paths.values())
            u.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)
            manifest={'profile':{'pack_id':pack,'destination_root':'/Game/'+pack}}
            proposal=cleanup.plan(manifest,imported=True)
            result['cleanup']=cleanup.execute(manifest,out.parent/'CustomSmokeBackup'/pack,imported=True,expected=proposal['delete_packages'])
            result.update(passed=result['cleanup']['passed'],job_survived_gui_exit=True,seconds=time.monotonic()-started)
            finish()
        if time.monotonic()-started>90:raise RuntimeError('Custom UI startup/reconnect timeout; see custom-ui.log')
    except Exception as error:
        result['error']=str(error);finish()
    finally:busy=False
def finish():
    u.unregister_slate_post_tick_callback(handle)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    u.SystemLibrary.quit_editor()
handle=u.register_slate_post_tick_callback(tick)
