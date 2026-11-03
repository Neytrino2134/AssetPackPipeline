"""Custom UI session memory: window placement, pin, mode/tab and unsaved form values.

Stored per project in Saved/AssetPackPipeline/UI/custom_window.json. Profile files
are never written here; unsaved form edits come back as an unsaved ('изменён') draft."""
import json
import re
import sys

SCHEMA = 1
FILE_NAME = 'custom_window.json'
_GEOMETRY = re.compile(r'(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$')


def path(window):
    return window.saved/'UI'/FILE_NAME


def _value(var):
    try:
        return var.get()
    except Exception:
        return None


def _assign(var, value):
    """Set only real changes so restoring an unchanged draft does not mark the profile dirty."""
    if value is None or _value(var) == value:
        return False
    try:
        var.set(value)
    except Exception:
        return False
    return True


def capture(window):
    chrome = getattr(window, 'chrome', None)
    zoomed = window.root.state() == 'zoomed'
    geometry = (chrome.normal_geometry if chrome and chrome.normal_geometry else None) if zoomed else window.root.geometry()
    try:
        tab = window.tabs.index('current')
    except Exception:
        tab = 0
    return {
        'schema': SCHEMA,
        'geometry': geometry,
        'zoomed': zoomed,
        'pinned': bool(chrome and chrome.pinned),
        'mode': _value(window.mode),
        'tab': tab,
        'guide_step': getattr(window, 'guide_step', 0),
        'guide': {'variants': _value(window.guide_variants), 'lod': _value(window.guide_lod),
                  'finalize': _value(window.guide_finalize),
                  'smart_normals': _value(getattr(window, 'guide_smart_normals', None)),
                  'renders': {k: _value(v) for k, v in window.guide_renders.items()},
                  'view_modes': {k: _value(v) for k, v in getattr(window, 'guide_view_modes', {}).items()}},
        'profile_path': str(window.profile_path) if window.profile_path else None,
        'form': {k: _value(v) for k, v in window.variables.items()},
    }


def save(window, state=None):
    state = state or capture(window)
    target = path(window)
    text = json.dumps(state, ensure_ascii=False, indent=2)
    try:
        if target.is_file() and target.read_text(encoding='utf-8') == text:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(target)
        return True
    except OSError:
        return False


def load(window):
    try:
        state = json.loads(path(window).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) and state.get('schema') == SCHEMA else None


def on_screen(x, y, width, height):
    """True when the title bar area lands on a connected monitor (monitors may change between sessions)."""
    if sys.platform != 'win32':
        return True
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32')
    user.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
    user.MonitorFromRect.restype = wintypes.HMONITOR
    title = wintypes.RECT(x+40, y, x+max(41, width-160), y+40)
    return bool(user.MonitorFromRect(ctypes.byref(title), 0))  # MONITOR_DEFAULTTONULL


def restore_geometry(window, state):
    """Call after the window is mapped and its native caption removed: Windows
    replaces a pre-map position with its cascade position, and without the caption
    Tk reads the size back slightly larger than set, so measure and correct once."""
    root = window.root
    match = _GEOMETRY.match(state.get('geometry') or '')
    if match:
        width, height = max(int(match[1]), 640), max(int(match[2]), 480)
        x, y = int(match[3]), int(match[4])
        place = f'{x:+d}{y:+d}' if on_screen(x, y, width, height) else ''
        root.geometry(f'{width}x{height}{place}')
        root.update_idletasks()
        actual = _GEOMETRY.match(root.geometry())
        if actual and (int(actual[1]), int(actual[2])) != (width, height):
            root.geometry(f'{2*width-int(actual[1])}x{2*height-int(actual[2])}{place}')
    if state.get('zoomed'):
        window.root.after_idle(lambda: window.root.state('zoomed'))
    if state.get('pinned') and getattr(window, 'chrome', None):
        window.chrome.set_pinned(True)


def restore(window, state):
    """Apply a loaded state (geometry separately, see restore_geometry)."""
    guide = state.get('guide') or {}
    _assign(window.guide_variants, guide.get('variants'))
    _assign(window.guide_lod, guide.get('lod'))
    _assign(window.guide_finalize, guide.get('finalize'))
    if getattr(window, 'guide_smart_normals', None) is not None:
        _assign(window.guide_smart_normals, guide.get('smart_normals'))
    for group, values in (('guide_renders', guide.get('renders')), ('guide_view_modes', guide.get('view_modes'))):
        for key, value in (values or {}).items():
            var = getattr(window, group, {}).get(key)
            if var is not None:
                _assign(var, value)
    # Unsaved form edits only belong to the profile they were made on.
    if state.get('profile_path') and window.profile_path and state['profile_path'] == str(window.profile_path):
        for key, value in (state.get('form') or {}).items():
            var = window.variables.get(key)
            if var is not None:
                _assign(var, value)
    if state.get('mode') in ('Быстрый старт', 'Мастер', 'Профессиональный'):
        window.mode.set(state['mode'])
    step = state.get('guide_step')
    if isinstance(step, int) and 0 <= step <= 3:
        window.guide_step = step
    window.switch_mode()
    tab = state.get('tab')
    if isinstance(tab, int) and 0 <= tab < window.tabs.index('end'):
        window.tabs.select(tab)
