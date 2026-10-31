"""Versioned owned master graph and per-instance material controls."""
import struct
import zlib
from pathlib import Path
import unreal as u

GRAPH_VERSION = '2'
GRAPH_TAG = 'AssetPackPipeline.MaterialGraphVersion'


def neutral_path(profile):
    return f"{profile['destination_root']}/Textures/T_{profile['pack_id']}_ORM_Default"


def neutral_texture(profile):
    from . import runtime
    path = neutral_path(profile)
    fresh = not u.EditorAssetLibrary.does_asset_exist(path)
    if not fresh:
        obj = u.load_asset(path)
        if not isinstance(obj, u.Texture2D) or not runtime.owned(obj, profile['pack_id']):
            raise RuntimeError(f'Foreign ORM helper: {path}')
    else:
        folder = Path(u.Paths.project_saved_dir()).resolve()/'AssetPackPipeline/Generated'
        folder.mkdir(parents=True, exist_ok=True)
        file = folder/'neutral_orm.png'
        def chunk(kind, data):
            return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data)&0xffffffff)
        file.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0))
                         +chunk(b'IDAT', zlib.compress((b'\0'+bytes([255, 255, 0])*2)*2))+chunk(b'IEND', b''))
        objects = runtime.import_file(str(file), path.rsplit('/', 1)[0], path.rsplit('/', 1)[1], factory=u.TextureFactory())
        obj = next((o for o in objects if isinstance(o, u.Texture2D)), None)
        if obj is None:
            raise RuntimeError('Could not create neutral ORM helper')
        runtime.mark(obj, profile['pack_id'])
    changed = fresh or obj.get_editor_property('srgb') or obj.get_editor_property('compression_settings') != u.TextureCompressionSettings.TC_MASKS
    if changed:
        obj.set_editor_property('srgb', False)
        obj.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_MASKS)
        runtime.save(obj)
    return obj


def build_graph(master, textures, neutral):
    """Rebuild legacy owned graphs in place, retaining the master asset identity."""
    mel = u.MaterialEditingLibrary
    version = str(u.EditorAssetLibrary.get_metadata_tag(master, GRAPH_TAG))
    if version == GRAPH_VERSION:
        return False
    if version not in ('', '1'):
        raise RuntimeError(f'Unsupported material graph version: {version}')
    mel.delete_all_material_expressions(master)
    def node(cls, x, y, **props):
        obj = mel.create_material_expression(master, cls, x, y)
        if obj is None:
            raise RuntimeError(f'Cannot create graph node {cls}')
        for name, value in props.items():
            obj.set_editor_property(name, value)
        return obj
    def connect(src, output, dst, pin):
        if not mel.connect_material_expressions(src, output, dst, pin):
            raise RuntimeError(f'Cannot connect graph input {pin}')
    def property_(src, output, prop):
        if not mel.connect_material_property(src, output, prop):
            raise RuntimeError(f'Cannot connect material property {prop}')
    def scalar(name, value, x, y):
        return node(u.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value)
    coord = node(u.MaterialExpressionTextureCoordinate, -1200, -300)
    uvscale = scalar('UVScale', 1., -1200, -100)
    uv = node(u.MaterialExpressionMultiply, -1000, -300)
    connect(coord, '', uv, 'A'); connect(uvscale, '', uv, 'B')
    samples = {}
    for i, channel in enumerate(('BaseColor', 'Normal', 'ORM')):
        sampler = {'BaseColor': u.MaterialSamplerType.SAMPLERTYPE_COLOR,
                   'Normal': u.MaterialSamplerType.SAMPLERTYPE_NORMAL,
                   'ORM': u.MaterialSamplerType.SAMPLERTYPE_MASKS}[channel]
        samples[channel] = node(u.MaterialExpressionTextureSampleParameter2D, -800, i*350,
                                parameter_name=channel, texture=textures.get(channel, neutral), sampler_type=sampler)
        connect(uv, '', samples[channel], 'UVs')
    property_(samples['BaseColor'], 'RGB', u.MaterialProperty.MP_BASE_COLOR)
    strength = scalar('NormalStrength', 1., -800, 200)
    mask = node(u.MaterialExpressionComponentMask, -500, 300, r=True, g=True, b=False, a=False)
    connect(samples['Normal'], 'RGB', mask, '')
    scaled = node(u.MaterialExpressionMultiply, -300, 300)
    connect(mask, '', scaled, 'A'); connect(strength, '', scaled, 'B')
    append = node(u.MaterialExpressionAppendVector, -100, 300)
    connect(scaled, '', append, 'A'); connect(samples['Normal'], 'B', append, 'B')
    normal = node(u.MaterialExpressionNormalize, 100, 300)
    connect(append, '', normal, '')
    property_(normal, '', u.MaterialProperty.MP_NORMAL)
    rough = scalar('Roughness', .85, -500, 800)
    metal = scalar('Metallic', 0., -500, 1000)
    use = scalar('UseORM', 0., -500, 1200)
    rough_map = node(u.MaterialExpressionMultiply, -300, 650)
    connect(samples['ORM'], 'G', rough_map, 'A'); connect(rough, '', rough_map, 'B')
    ao = node(u.MaterialExpressionConstant, -500, 1400, r=1.)
    for i, (fallback, source, output, prop) in enumerate([
            (rough, rough_map, '', u.MaterialProperty.MP_ROUGHNESS),
            (metal, samples['ORM'], 'B', u.MaterialProperty.MP_METALLIC),
            (ao, samples['ORM'], 'R', u.MaterialProperty.MP_AMBIENT_OCCLUSION)]):
        lerp = node(u.MaterialExpressionLinearInterpolate, 100, 650+i*200)
        connect(fallback, '', lerp, 'A'); connect(source, output, lerp, 'B'); connect(use, '', lerp, 'Alpha')
        property_(lerp, '', prop)
    errors = list(mel.recompile_material(master))
    if errors:
        raise RuntimeError(f'Master material compile errors: {errors}')
    u.EditorAssetLibrary.set_metadata_tag(master, GRAPH_TAG, GRAPH_VERSION)
    return True
