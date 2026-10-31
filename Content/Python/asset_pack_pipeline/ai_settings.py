"""Per-user AI preferences. Secrets are session-only or Windows DPAPI encrypted."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

MODELS = ('gpt-6.1-sol', 'gpt-6-astra', 'gpt-6.1-terra', 'gpt-6-luna')
_session_key = ''


def location():
    return Path(os.environ.get('LOCALAPPDATA') or Path.home())/'AssetPackPipeline'/'ai-settings.json'


def load():
    try:
        value = json.loads(location().read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, RuntimeError):
        return {}


def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Сохранение ключа поддерживается только в Windows. Используйте ключ на время сеанса.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError('Windows не смогла защитить или открыть сохранённый ключ.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(target.data)


def get_key():
    if _session_key:
        return _session_key
    stored = load().get('protected_key')
    if stored:
        try:
            return crypt(base64.b64decode(stored), True).decode('utf-8')
        except Exception:
            pass
    return os.environ.get('OPENAI_API_KEY', '').strip()


def save(model, key='', remember=False, forget=False):
    global _session_key
    if not model.strip() or len(model) > 150 or any(c.isspace() for c in model):
        raise ValueError('Укажите корректный ID модели.')
    if key and (any(c.isspace() for c in key.strip()) or len(key.strip()) > 1024):
        raise ValueError('Некорректный формат ключа.')
    config = load()
    config['model'] = model.strip()
    if forget:
        config.pop('protected_key', None)
    elif key.strip() and remember:
        config['protected_key'] = base64.b64encode(crypt(key.strip().encode())).decode('ascii')
    elif key.strip():
        # Session replacement must not resurrect an older saved key on restart.
        config.pop('protected_key', None)
    path = location()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(config, indent=2), encoding='utf-8')
    temporary.replace(path)
    if key.strip() or forget:
        _session_key = '' if forget else key.strip()


def model_options(ids):
    """Only known tool-capable chat families; /models does not publish capabilities."""
    allowed = sorted({m for m in ids if isinstance(m, str) and
                      any(m == prefix or m.startswith(prefix+'-') for prefix in MODELS)})
    return [m for m in MODELS if m in allowed]+[m for m in allowed if m not in MODELS]
