"""Real Unreal context/native lifecycle for update integration; no remote install."""
import json
import sys
from pathlib import Path
import unreal as u
from asset_pack_pipeline import updater,ui
plugin=Path(__file__).resolve().parents[1];project=plugin.parents[1]
assert Path(u.Paths.get_project_file_path()).resolve().is_relative_to(project/'Saved')
result={'passed':False}
try:
    context=updater.engine_context()
    metadata=json.loads((project/'Releases/AssetPackPipeline-update.json').read_text())
    assert context['build_id']==metadata['build_id']
    assert context['engine_version']==metadata['engine_version']
    assert Path(context['python']).is_file()
    ui.register()
    u.AssetPackPipelineNative.open_window();assert u.AssetPackPipelineNative.is_window_open()
    u.AssetPackPipelineNative.close_window()
    assert 'tkinter' not in sys.modules
    result.update(passed=True,context=context,native_lifecycle=True,unreal_tkinter_loaded=False)
except Exception:
    import traceback
    result['error']=traceback.format_exc()
(project/'Saved/UpdaterProcessSmoke/UnrealResult.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
u.SystemLibrary.quit_editor()
