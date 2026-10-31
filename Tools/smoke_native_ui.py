"""In-editor Slate lifecycle smoke. No imports, renders, deletions or API calls."""
import json
import sys
import base64
import time
from pathlib import Path
import unreal as u
u.EditorPythonScripting.set_keep_python_script_alive(True)

result = {'passed':False, 'iterations':0}
path = Path(u.Paths.project_saved_dir())/'AssetPackPipeline/NativeSmoke.json'
path.parent.mkdir(parents=True,exist_ok=True)
from asset_pack_pipeline import native_bridge
for action, expected in (('queue','queue'),('load_profile','professional_fields')):
    native_bridge.submit_b64(base64.b64encode(json.dumps({'action':action}).encode()).decode())
    value = json.loads((path.parent/'Native/state.json').read_text(encoding='utf-8'))
    assert expected in value, value
result['bridge_readonly'] = True
ticks = 0
ready_at = time.monotonic()+3
def tick(delta):
    global ticks
    try:
        if time.monotonic()<ready_at:
            return
        ticks += 1
        if ticks % 10 == 1:
            u.AssetPackPipelineNative.open_window()
        if ticks % 10 == 5:
            assert u.AssetPackPipelineNative.is_window_open(), 'Native tab is not open'
            assert u.AssetPackPipelineNative.run_ui_regression_step(result['iterations']), 'Native widget exercise failed'
            assert 'tkinter' not in sys.modules, 'Tkinter unexpectedly imported'
            u.AssetPackPipelineNative.close_window()
            result['iterations'] += 1
        if ticks >= 100:
            result.update(passed=True, tkinter_loaded='tkinter' in sys.modules)
            finish()
    except Exception as error:
        result['error'] = str(error)
        finish()
def finish():
    u.unregister_slate_post_tick_callback(handle)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    u.SystemLibrary.quit_editor()
handle = u.register_slate_post_tick_callback(tick)
