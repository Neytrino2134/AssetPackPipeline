"""Asynchronous screenshots of saved, validated plugin maps; no map generation."""
import hashlib
import math
import struct
import time
from pathlib import Path


def settings(profile):
    config = dict(profile.get('previews', {}))
    for key, default in [('width', 1920), ('height', 1080)]:
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 256 <= value <= 8192:
            raise ValueError(f'Preview {key} must be an integer from 256 to 8192')
        config[key] = value
    if config['width'] * config['height'] > 33554432:
        raise ValueError('Preview exceeds 32 megapixels')
    config.setdefault('mode', 'overview')
    config.setdefault('camera', 'overview')
    if config['mode'] not in ('overview', 'lod_review', 'both'):
        raise ValueError('Preview mode must be overview, lod_review or both')
    if config['camera'] not in ('overview', 'detail'):
        raise ValueError('Preview camera must be overview or detail')
    for key, default in [('warmup_seconds', 5), ('timeout_seconds', 120)]:
        value = float(config.get(key, default))
        if not math.isfinite(value) or not (0 <= value <= 300 if key == 'warmup_seconds' else 10 <= value <= 600):
            raise ValueError(f'Invalid preview {key}')
        config[key] = value
    output = str(config.get('output_directory', '')).strip()
    if output and not Path(output).is_absolute():
        raise ValueError('Preview output directory must be absolute or empty')
    config['output_directory'] = output
    return config


def inspect_png(path, width, height):
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise RuntimeError(f'Missing or invalid PNG: {path}')
    actual = struct.unpack('>II', data[16:24])
    if actual != (width, height):
        raise RuntimeError(f'Wrong preview dimensions: {actual}, expected {(width, height)}')
    return {'path': str(path), 'width': width, 'height': height, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def advance(report, state):
    """One editor tick. Keep screenshot task alive until it has completed."""
    import unreal as u
    from . import overview
    config = report['preview_settings']
    item = next((a for a in report['assets'] if a['status'] in ('pending', 'running')), None)
    if item is None:
        return True
    if report['cancel_requested'] and 'task' not in state:
        for row in report['assets']:
            if row['status'] in ('pending', 'running'):
                row['status'] = 'cancelled'
        return True
    now = time.monotonic()
    if item['status'] == 'pending':
        overview.open_map(report['manifest'], item['lod_review'])
        validation = overview.validate_current(report['manifest'], item['lod_review'])
        if not validation['passed']:
            raise RuntimeError('Saved scene failed read-back; regenerate it before exporting')
        item.update(status='running', scene_validation=validation)
        state.update(started=now, warm_until=now+config['warmup_seconds'])
        return False
    if now-state['started'] > config['timeout_seconds']:
        # An active screenshot cannot be cancelled by this API; retain exclusivity
        # until completion, then report the timeout rather than start another shot.
        state['timed_out'] = True
    if 'task' not in state:
        if state.get('timed_out'):
            raise RuntimeError('Preview warmup timed out')
        if now < state['warm_until']:
            return False
        overview._safe_to_switch()
        if overview._current()[1] != item['map_path']:
            raise RuntimeError('Active map changed during preview export')
        actors = overview._actors(report['manifest']['profile'])
        camera = actors.get('Camera_'+config['camera'].title())
        if camera is None:
            raise RuntimeError('Requested preview camera is missing')
        task = u.AutomationLibrary.take_high_res_screenshot(
            config['width'], config['height'], item['output_path'], camera, delay=1)
        if not task or not task.is_valid_task():
            raise RuntimeError('Unreal rejected screenshot task; an interactive RHI viewport is required')
        state['task'] = task
        return False
    if not state['task'].is_task_done():
        return False
    state.pop('task')
    if overview._current()[1] != item['map_path']:
        raise RuntimeError('Active map changed during capture; preview rejected')
    if state.get('timed_out'):
        raise RuntimeError('Preview capture exceeded timeout')
    item.update(inspect_png(item['output_path'], config['width'], config['height']), status='passed')
    state.clear()
    return False
