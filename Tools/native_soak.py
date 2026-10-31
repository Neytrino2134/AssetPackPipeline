"""20-minute native widget soak in an isolated HostProject; no content/network actions."""
import json
import sys
import time
from pathlib import Path
import unreal as u
u.EditorPythonScripting.set_keep_python_script_alive(True)
assert Path(u.Paths.get_project_file_path()).stem=='HostProject'
out=Path(u.Paths.project_saved_dir())/'AssetPackPipeline/NativeSoak.json'
out.parent.mkdir(parents=True,exist_ok=True)
started=time.monotonic()
last=started
busy=False
result={'passed':False,'steps':0,'reopen_cycles':0,'target_seconds':1200,'kind':'programmatic_widget_soak'}
def tick(delta):
    global last,busy
    now=time.monotonic()
    if busy or now-last<1 or now-started<3: return
    busy=True; last=now
    try:
        n=result['steps']
        if n%20==0:
            u.AssetPackPipelineNative.close_window()
            u.AssetPackPipelineNative.open_window()
            result['reopen_cycles']+=1
        assert u.AssetPackPipelineNative.is_window_open(), 'Native tab missing'
        assert u.AssetPackPipelineNative.run_ui_regression_step(n), 'Native text read-back mismatch'
        assert 'tkinter' not in sys.modules, 'Tkinter loaded'
        result.update(steps=n+1,seconds=now-started,tkinter_loaded=False)
        if now-started>=1200:
            result['passed']=True
            finish()
        else: out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    except Exception as error:
        result['error']=str(error)
        finish()
    finally: busy=False
def finish():
    u.unregister_slate_post_tick_callback(handle)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    u.SystemLibrary.quit_editor()
handle=u.register_slate_post_tick_callback(tick)
