"""Small real MRQ regression in the isolated HostProject (24 frames)."""
import json
import time
import uuid
from pathlib import Path
import unreal as u
from asset_pack_pipeline import api,guided
u.EditorPythonScripting.set_keep_python_script_alive(True)
assert Path(u.Paths.get_project_file_path()).stem=='HostProject'
base=json.loads((Path(__file__).resolve().parents[3]/'Plugins/AssetPackPipeline/Content/Profiles/profile.example.json').read_text())
run=uuid.uuid4().hex
out=Path(u.Paths.project_saved_dir())/'AssetPackPipeline/FlightRegression'/run
out.mkdir(parents=True)
profiles,_=guided.prepare(base,r'D:\Work\3D Stocks\3D Asset Packs\!NewAssetPack\15_Containers_Ready\!Unreal',
                         'FlightRegression_'+run[:8],'FBX','LOD')
p=profiles['LOD']; p['asset_ids']=['Containers_01_02']
p['flythrough']={'seconds':2,'fps':12,'width':256,'height':256,'yaw_start':65,'yaw_end':115,'pitch':25,'fov':50}
path=out/'profile.json'; path.write_text(json.dumps(p,indent=2),encoding='utf-8')
session=guided.Session(api,{'LOD':str(path)},[('LOD','import'),('LOD','validate')])
started=time.monotonic(); last=0; busy=False; flight=None
result={'passed':False,'expected_frames':24}
def finish():
    u.unregister_slate_post_tick_callback(handle)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    u.SystemLibrary.quit_editor()
def tick(delta):
    global last,busy,flight
    now=time.monotonic()
    if busy or now-last<.5:return
    busy=True;last=now
    try:
        if not session.done:session.tick()
        elif session.error:raise RuntimeError(session.error)
        elif flight is None:
            flight=api.start_flythrough(str(path))
            result['run_id']=flight
        else:
            report=api.status(flight)
            if report['status']!='running':
                frames=list(Path(report['output_directory']).glob('frame_*.png'))
                result.update(status=report['status'],frames=len(frames),report_path=report['report_path'],seconds=now-started)
                result['passed']=report['status']=='passed' and len(frames)==24
                finish()
        if now-started>600:raise RuntimeError('Flight regression timeout')
    except Exception as error:
        result['error']=str(error);finish()
    finally:busy=False
handle=u.register_slate_post_tick_callback(tick)
