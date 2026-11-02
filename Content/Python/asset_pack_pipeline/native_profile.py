"""Typed native form mapping, independent of Unreal and legacy Tk UI."""
import copy
import re
from . import profiles

FIELDS = {
    'mesh_info':('mesh_info', str), 'texture_directory':('texture_directory',str),
    'roughness':('roughness',float), 'metallic':('metallic',float),
    'normal_strength':('normal_strength',float), 'uv_scale':('uv_scale',float),
    'orm_texture':('orm_texture',str), 'collision':('collision',str),
    'convex_hull_count':('convex_collision.hull_count',int),
    'convex_max_hull_verts':('convex_collision.max_hull_verts',int),
    'convex_precision':('convex_collision.precision',int),
    'nanite_source':('nanite_source',str), 'destination_root':('destination_root',str),
    'overview_columns':('overview.columns',int), 'overview_spacing':('overview.spacing',float),
    'overview_label_size':('overview.label_size',float), 'preview_width':('previews.width',int),
    'preview_height':('previews.height',int), 'preview_warmup':('previews.warmup_seconds',float),
    'media_pitch':('media.pitch',float), 'media_fov':('media.fov',float),
    'media_margin':('media.margin',float), 'media_exposure':('media.exposure_bias',float),
    'flythrough_seconds':('flythrough.seconds',float), 'flythrough_fps':('flythrough.fps',int),
    'flythrough_width':('flythrough.width',int), 'flythrough_height':('flythrough.height',int),
    'flythrough_yaw_start':('flythrough.yaw_start',float), 'flythrough_yaw_end':('flythrough.yaw_end',float),
    'flythrough_pitch':('flythrough.pitch',float), 'flythrough_fov':('flythrough.fov',float),
}


def form_values(profile):
    result = {}
    for key,(path,_) in FIELDS.items():
        value = profile
        for part in path.split('.'):
            value = value.get(part, '') if isinstance(value,dict) else ''
        result[key] = str(value)
    result['lod_screen_sizes'] = ', '.join(map(str,profile.get('lod_screen_sizes',[])))
    result['asset_ids'] = ', '.join(profile.get('asset_ids',[]))
    return result


def apply_fields(base, values):
    p = copy.deepcopy(base)
    for key,value in values.items():
        if key in ('asset_ids','lod_screen_sizes'):
            continue
        if key not in FIELDS:
            raise ValueError('Unknown professional field: '+key)
        path, convert = FIELDS[key]
        if not value.strip() and convert != str:
            continue
        current = p
        parts = path.split('.')
        for part in parts[:-1]:
            current = current.setdefault(part,{})
        if value.strip() or convert == str:
            current[parts[-1]] = convert(value.strip())
    if 'lod_screen_sizes' in values:
        p['lod_screen_sizes'] = [float(v) for v in re.split(r'[,;\s]+',values['lod_screen_sizes'].strip()) if v]
    if 'asset_ids' in values:
        ids = [v for v in re.split(r'[,;\s]+',values['asset_ids'].strip()) if v]
        if ids: p['asset_ids'] = ids
        else: p.pop('asset_ids',None)
    if not re.fullmatch(r'/Game/[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)*',p['destination_root']):
        raise ValueError('Назначение должно быть папкой /Game/Pack, не корнем /Game.')
    profiles.validate_settings(p)
    from . import overview, previews, media, flythrough
    overview.settings(p); previews.settings(p); media.settings(p); flythrough.settings(p)
    return p


def edit_override(base, asset_id, fields, remove=False):
    if not re.fullmatch(r'[A-Za-z0-9_]+',asset_id):
        raise ValueError('Укажите корректный ID модели.')
    result = copy.deepcopy(base)
    overrides = result.setdefault('asset_overrides',{})
    if remove:
        overrides.pop(asset_id,None)
        return result
    values = {}
    for key, text in fields.items():
        if key not in profiles.OVERRIDE_KEYS:
            raise ValueError('Unsupported override '+key)
        text = text.strip()
        if not text or text=='inherit': continue
        if key=='lod_screen_sizes':
            value = [float(v) for v in re.split(r'[,;\s]+',text) if v]
            if len(value)!=len(base['lod_screen_sizes']): raise ValueError('Нельзя менять количество LOD одной модели.')
        elif key=='remove_degenerates':
            if text not in ('true','false'): raise ValueError('Remove Degenerates: inherit / true / false')
            value = text=='true'
        elif key in ('roughness','metallic','normal_strength','uv_scale'): value = float(text)
        else: value = '' if key=='orm_texture' and text=='-' else text
        values[key] = value
    if values: overrides[asset_id] = values
    else: overrides.pop(asset_id,None)
    profiles.effective(result,asset_id)
    return result
