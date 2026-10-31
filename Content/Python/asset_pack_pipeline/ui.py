"""Manual menu entry points invoke exactly the same API as MCP."""
import json
from pathlib import Path
import unreal
from . import api


def profile():
    path = Path(unreal.Paths.project_saved_dir()).resolve() / 'AssetPackPipeline' / 'active_profile.json'
    if not path.is_file():
        raise RuntimeError(f'Create your local active profile first: {path}')
    return str(path)


def open_window():
    if not hasattr(unreal, 'AssetPackPipelineNative'):
        raise RuntimeError('Native UI module is not built. Install the compiled plugin for this Unreal version. Tk fallback is disabled for stability.')
    return unreal.AssetPackPipelineNative.open_window()


def open_custom_window():
    from . import custom_server
    return custom_server.launch()


def invoke(action):
    try:
        if action == 'readiness':
            result = api.readiness()
        elif action == 'plan':
            result = api.plan(profile())
        elif action == 'start':
            result = {'run_id': api.start(profile())}
        elif action == 'validate':
            result = api.validate(profile())
        elif action == 'cancel':
            run_id = api.readiness()['active_run']
            result = api.cancel(run_id) if run_id else {'status': 'idle'}
        else:
            run_id = api.readiness()['active_run']
            result = api.status(run_id) if run_id else {'status': 'idle'}
        unreal.log(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        unreal.log_error(f'AssetPackPipeline: {error}')


def register():
    menus = unreal.ToolMenus.get()
    owner = 'AssetPackPipeline'
    menus.unregister_owner_by_name(owner)
    parent = menus.extend_menu('LevelEditor.MainMenu.Tools')
    menu = parent.add_sub_menu(owner, 'AssetPackPipeline', 'AssetPackPipeline', 'Asset Pack Pipeline')
    custom = unreal.ToolMenuEntry(name='AssetPackPipeline.CustomWindow',type=unreal.MultiBlockType.MENU_ENTRY)
    custom.set_label('Открыть Custom UI (отдельное окно)…')
    custom.set_string_command(unreal.ToolMenuStringCommandType.PYTHON,'','from asset_pack_pipeline import ui; ui.open_custom_window()')
    menu.add_menu_entry('Window',custom)
    entry = unreal.ToolMenuEntry(name='AssetPackPipeline.OpenWindow', type=unreal.MultiBlockType.MENU_ENTRY)
    entry.set_label('Открыть Unreal UI (Slate)…')
    entry.set_string_command(unreal.ToolMenuStringCommandType.PYTHON, '',
                             'from asset_pack_pipeline import ui; ui.open_window()')
    menu.add_menu_entry('Window', entry)
    for action, label in [('readiness', 'Readiness'), ('plan', 'Scan and Plan'),
                          ('start', 'Run Import + Materials + LODs'),
                          ('status', 'Current Job Status'), ('cancel', 'Cancel at Next Asset'),
                          ('validate', 'Validate Assets')]:
        entry = unreal.ToolMenuEntry(name=f'AssetPackPipeline.{action}',
                                     type=unreal.MultiBlockType.MENU_ENTRY)
        entry.set_label(label)
        entry.set_string_command(unreal.ToolMenuStringCommandType.PYTHON, '',
                                 f"from asset_pack_pipeline import ui; ui.invoke('{action}')")
        menu.add_menu_entry('Actions', entry)
    menus.refresh_all_widgets()
