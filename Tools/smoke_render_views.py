"""Actual GPU captures in a copied project, starting from Wireframe."""
import copy
import json
import sys
import time
from pathlib import Path
import unreal as u
plugin=Path(__file__).resolve().parents[1];project=plugin.parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import api,render_views
folder=project/'Saved/RenderViewsSmoke'
assert Path(u.Paths.get_project_file_path()).resolve().is_relative_to(folder)
u.EditorPythonScripting.set_keep_python_script_alive(True)
data=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
profile=copy.deepcopy(data['manifest']['variants'][0]['profile'])
profile['previews'].update(width=640,height=360,warmup_seconds=1,timeout_seconds=90,view_modes=list(render_views.MODES))
profile['media']=dict(profile.get('media',{}),yaw_angles=[90],lod_indices=[0])
overview_path=folder/'overview.json';overview_path.write_text(json.dumps(profile),encoding='utf-8')
single=copy.deepcopy(profile);single['asset_ids']=['Containers_01_02']
single_path=folder/'single.json';single_path.write_text(json.dumps(single),encoding='utf-8')
nanite=copy.deepcopy(data['manifest']['variants'][1]['profile'])
nanite['previews']=copy.deepcopy(profile['previews']);nanite['media']=copy.deepcopy(profile['media']);nanite['asset_ids']=['Containers_01_02']
nanite_path=folder/'nanite.json';nanite_path.write_text(json.dumps(nanite),encoding='utf-8')
started=time.monotonic();phase=0;run=None;busy=False
result={'passed':False,'jobs':[]}
def finish():
    u.unregister_slate_post_tick_callback(handle)
    (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    u.SystemLibrary.quit_editor()
def tick(delta):
    global phase,run,busy
    if busy:return
    busy=True
    try:
        if time.monotonic()-started<3:return
        if time.monotonic()-started>420:raise TimeoutError('GPU render modes test timeout')
        if run:
            report=api.status(run)
            if report['status']=='running':return
            assert report['status']=='passed',report.get('error',report['status'])
            assert len(report['assets'])==4
            assert {a['render_view'] for a in report['assets']}==set(render_views.MODES)
            assert all(a.get('viewport_mode_verified') for a in report['assets'])
            assert u.AutomationLibrary.get_editor_active_viewport_view_mode()==u.ViewModeIndex.VMI_WIREFRAME
            by_mode={a['render_view']:a for a in report['assets']}
            assert by_mode['lit']['sha256']!=by_mode['wireframe']['sha256']
            result['jobs'].append({'kind':report['kind'],'run_id':run,'output':report['output_directory'],
                'restored_wireframe':True,'frames':[{'file':a['output_path'],'view':a['render_view'],'sha256':a['sha256']} for a in report['assets']]})
            run=None;phase+=1
        if phase==3:
            result.update(passed=True,seconds=time.monotonic()-started);finish();return
        u.AutomationLibrary.set_editor_active_viewport_view_mode(u.ViewModeIndex.VMI_WIREFRAME)
        run=api.start_previews(str(overview_path)) if phase==0 else api.start_media(str(single_path if phase==1 else nanite_path))
    except Exception:
        import traceback
        result['error']=traceback.format_exc();finish()
    finally:busy=False
handle=u.register_slate_post_tick_callback(tick)
