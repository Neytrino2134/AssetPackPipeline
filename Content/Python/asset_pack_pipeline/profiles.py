"""Shared defaults and strict per-model overrides, independent of Unreal."""
import copy
import math
import re

DEFAULTS = {'collision': 'none', 'remove_degenerates': True, 'roughness': 0.85,
            'metallic': 0.0, 'normal_strength': 1.0, 'uv_scale': 1.0, 'orm_texture': '', 'nanite_source': 'AUTO'}
OVERRIDE_KEYS = set(DEFAULTS) | {'lod_screen_sizes'}


def validate_settings(profile):
    subdir = profile.get('mesh_subdirectory', '')
    if not isinstance(subdir, str) or (subdir and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', subdir)):
        raise ValueError('mesh_subdirectory must be a simple directory name or empty')
    if profile.get('validation_policy', 'warn') not in ('warn', 'strict'):
        raise ValueError('validation_policy must be warn or strict')
    if not isinstance(profile.get('skip_invalid_sources', False), bool):
        raise ValueError('skip_invalid_sources must be a boolean')
    if not isinstance(profile.get('nanite_enabled',False),bool):
        raise ValueError('nanite_enabled must be a boolean')
    if profile.get('nanite_source','AUTO') not in ('AUTO','MID','HIGH'):
        raise ValueError('nanite_source must be AUTO, MID or HIGH')
    if not isinstance(profile.get('incremental', True), bool):
        raise ValueError('incremental must be a boolean')
    sizes = profile['lod_screen_sizes']
    if not isinstance(sizes, list) or not sizes or any(isinstance(x, bool) or not isinstance(x, (int, float))
            or not math.isfinite(x) or not 0 < x <= 1 for x in sizes):
        raise ValueError('LOD screen sizes must be finite numbers in (0,1]')
    if any(a <= b for a, b in zip(sizes, sizes[1:])):
        raise ValueError('LOD screen sizes must decrease strictly')
    if profile.get('collision', 'none') not in ('none', 'box'):
        raise ValueError('collision must be none or box')
    if not isinstance(profile.get('remove_degenerates', True), bool):
        raise ValueError('remove_degenerates must be a boolean')
    for key, low, high in [('roughness', 0, 1), ('metallic', 0, 1), ('normal_strength', 0, 4), ('uv_scale', .01, 100)]:
        value = profile.get(key, DEFAULTS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{key} must be a finite number in [{low}, {high}]')
    if not isinstance(profile.get('orm_texture', ''), str):
        raise ValueError('orm_texture must be a relative path string or empty')


def effective(profile, asset_id):
    result = copy.deepcopy(profile)
    overrides = result.pop('asset_overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError('asset_overrides must be an object keyed by asset_id')
    values = overrides.get(asset_id, {})
    if not isinstance(values, dict) or set(values) - OVERRIDE_KEYS:
        raise ValueError(f'{asset_id}: unsupported override fields')
    result.update(values)
    for key, value in DEFAULTS.items():
        result.setdefault(key, value)
    validate_settings(result)
    if result.get('nanite_enabled',False):result['lod_screen_sizes']=[1.0]
    return result


def for_asset(manifest, asset):
    return dict(manifest, profile=effective(manifest['profile'], asset['id']))


def material_scalars(profile, has_orm):
    return {'Roughness': profile.get('roughness', .85), 'Metallic': profile.get('metallic', 0),
            'NormalStrength': profile.get('normal_strength', 1), 'UVScale': profile.get('uv_scale', 1),
            'UseORM': float(has_orm)}
