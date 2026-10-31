"""Maximum-quality render state for stills and flythroughs.

Editor captures otherwise inherit the editor's scalability, texture streaming
pool and viewport screen percentage, so textures arrive at low mips and the
image is upscaled/blurred. Values are restored after the capture job."""

# Order matters: sg.* resets dependent r.* values, so it is applied first.
CVARS = {
    'sg.TextureQuality': 4, 'sg.ShadowQuality': 4, 'sg.PostProcessQuality': 4,
    'sg.EffectsQuality': 4, 'sg.ViewDistanceQuality': 4, 'sg.ReflectionQuality': 4,
    'sg.GlobalIlluminationQuality': 4, 'sg.AntiAliasingQuality': 4,
    'r.Streaming.FullyLoadUsedTextures': 1, 'r.Streaming.MipBias': 0,
    'r.Streaming.LimitPoolSizeToVRAM': 0, 'r.MipMapLODBias': 0, 'r.MaxAnisotropy': 16,
    'r.ScreenPercentage': 100, 'r.Editor.Viewport.ScreenPercentage': 100,
    'r.SecondaryScreenPercentage.GameViewport': 100,
}
# LOD selection cvars are deliberately untouched: LOD review captures measure them.

_saved = None
_saved_throttle = None


THROTTLE_PROPERTY = 'bThrottleCPUWhenNotForeground'


def _performance_settings():
    # Not exported as a Python type; load the class by path. get_editor_property
    # looks the name up on the real UClass, so the C++ property name works.
    import unreal as u
    cls = u.load_class(None, '/Script/UnrealEd.EditorPerformanceSettings')
    if cls is None:
        raise RuntimeError('EditorPerformanceSettings class not found')
    return u.get_default_object(cls)


def _keep_rendering_in_background():
    """With 'Use Less CPU when in Background' the editor disables every viewport
    while another app (e.g. Custom UI) has focus, so screenshot tasks never finish
    (EditorEngine.cpp: !FApp::HasFocus() && bThrottleCPUWhenNotForeground).
    Turn it off for the job and un-minimise the editor without taking focus."""
    global _saved_throttle
    import unreal as u
    try:
        settings = _performance_settings()
        if _saved_throttle is None:
            _saved_throttle = bool(settings.get_editor_property(THROTTLE_PROPERTY))
        settings.set_editor_property(THROTTLE_PROPERTY, False)
    except Exception as error:
        # Best effort: without it the capture still works while Unreal has focus.
        u.log_warning(f'AssetPackPipeline: cannot keep rendering in background: {error}')
    try:
        _restore_minimised_editor()
    except Exception as error:
        u.log_warning(f'AssetPackPipeline: cannot restore minimised editor: {error}')


def _restore_minimised_editor():
    import os, sys
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32')
    user.IsIconic.argtypes = user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pid = os.getpid()
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(hwnd) and user.IsIconic(hwnd):
            user.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE: restore behind the focused app
        return True
    user.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit), 0)


def _world():
    import unreal as u
    return u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()


def apply():
    """Idempotent; the first call of a capture job records the original values."""
    global _saved
    import unreal as u
    world = _world()
    if _saved is None:
        _saved = {name: u.SystemLibrary.get_console_variable_float_value(name) for name in CVARS}
    for name, value in CVARS.items():
        u.SystemLibrary.execute_console_command(world, f'{name} {value}')
    _keep_rendering_in_background()


def restore():
    global _saved, _saved_throttle
    if _saved_throttle is not None:
        import unreal as u
        try:
            _performance_settings().set_editor_property(THROTTLE_PROPERTY, _saved_throttle)
        except Exception as error:
            u.log_warning(f'AssetPackPipeline: cannot restore background CPU setting: {error}')
        _saved_throttle = None
    if _saved is None:
        return
    import unreal as u
    world = _world()
    for name, value in _saved.items():
        u.SystemLibrary.execute_console_command(world, f'{name} {value:g}')
    _saved = None


def prestream(actors, seconds):
    """Ask streaming to keep full mips of the captured meshes resident."""
    import unreal as u
    # Only mesh components expose PrestreamTextures (labels are TextRenderComponents).
    # Best effort: FullyLoadUsedTextures already covers anything missed here.
    for actor in actors:
        for component in actor.get_components_by_class(u.MeshComponent):
            try:
                component.prestream_textures(max(1.0, seconds + 5), False)
            except (AttributeError, TypeError):
                pass


def movie_pipeline(preset, samples=8):
    """Offline AA accumulation and the same cvars for Movie Render Queue jobs."""
    import unreal as u
    aa = preset.find_or_add_setting_by_class(u.MoviePipelineAntiAliasingSetting)
    aa.spatial_sample_count = 1
    aa.temporal_sample_count = samples
    aa.override_anti_aliasing = True
    aa.anti_aliasing_method = u.AntiAliasingMethod.AAM_NONE
    aa.engine_warm_up_count = 32
    aa.render_warm_up_count = 32
    aa.use_camera_cut_for_warm_up = False
    cvars = preset.find_or_add_setting_by_class(u.MoviePipelineConsoleVariableSetting)
    for name, value in CVARS.items():
        cvars.add_or_update_console_variable(name, float(value))
