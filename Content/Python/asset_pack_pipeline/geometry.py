"""Read-only FBX/glTF triangle diagnostics, independent of Unreal and DCC SDKs.

Binary FBX 7.x and uncompressed GLB triangle lists only. Geometry is measured
in source-local space; near-zero thresholds are descriptive, not UE weld rules.
"""
import json
import math
import struct
import zlib
from pathlib import Path


def binary_fbx(path):
    data = Path(path).read_bytes()
    if len(data) < 27 or data[:23] != b'Kaydara FBX Binary  \x00\x1a\x00':
        raise ValueError('Only binary FBX is supported by the source diagnostic reader')
    version = struct.unpack_from('<I', data, 23)[0]
    if not 7000 <= version < 8000:
        raise ValueError('Only binary FBX 7.x is supported')
    header, sentinel = ('<QQQB', 25) if version >= 7500 else ('<IIIB', 13)

    def node(offset, depth=0):
        if depth > 64 or offset + sentinel > len(data):
            raise ValueError('Invalid FBX node bounds/depth')
        end, count, prop_bytes, name_size = struct.unpack_from(header, data, offset)
        if end == 0:
            return None, offset + sentinel
        if not offset < end <= len(data):
            raise ValueError('Invalid FBX end offset')
        cursor = offset + sentinel
        name = data[cursor:cursor+name_size].decode('utf-8', errors='replace')
        cursor += name_size
        prop_end = cursor + prop_bytes
        if prop_end > end:
            raise ValueError('Invalid FBX property bounds')
        props = []
        for _ in range(count):
            kind = chr(data[cursor])
            cursor += 1
            if kind in 'YCIFDL':
                fmt = {'Y':'h', 'C':'?', 'I':'i', 'F':'f', 'D':'d', 'L':'q'}[kind]
                props.append(struct.unpack_from('<'+fmt, data, cursor)[0])
                cursor += struct.calcsize(fmt)
            elif kind in 'SR':
                length = struct.unpack_from('<I', data, cursor)[0]
                cursor += 4
                value = data[cursor:cursor+length]
                props.append(value.decode('utf-8', errors='replace') if kind == 'S' else None)
                cursor += length
            elif kind in 'fdlibc':
                length, encoding, size = struct.unpack_from('<III', data, cursor)
                cursor += 12
                fmt = {'f':'f', 'd':'d', 'l':'q', 'i':'i', 'b':'b', 'c':'b'}[kind]
                expected = length*struct.calcsize(fmt)
                if expected > 256*1024*1024 or cursor+size > prop_end:
                    raise ValueError('FBX array exceeds diagnostic reader bounds')
                raw = data[cursor:cursor+size]
                if encoding == 1:
                    decoder = zlib.decompressobj()
                    raw = decoder.decompress(raw, expected+1)
                    if not decoder.eof or decoder.unused_data:
                        raise ValueError('Invalid/truncated FBX compressed array')
                elif encoding != 0:
                    raise ValueError('Unsupported FBX array encoding')
                if len(raw) != expected:
                    raise ValueError('Invalid FBX array length')
                props.append([x[0] for x in struct.iter_unpack('<'+fmt, raw)])
                cursor += size
            else:
                raise ValueError(f'Unsupported FBX property: {kind}')
            if cursor > prop_end:
                raise ValueError('Truncated FBX properties')
        if cursor != prop_end:
            raise ValueError('FBX property length mismatch')
        children = []
        while cursor < end-sentinel:
            child, cursor = node(cursor, depth+1)
            if child is None:
                break
            children.append(child)
        return {'name': name, 'props': props, 'children': children}, end

    nodes, offset = [], 27
    while offset + sentinel < len(data):
        item, offset = node(offset)
        if item is None:
            break
        nodes.append(item)
    return nodes


def _child(node, name):
    return next((x for x in node['children'] if x['name'] == name), None)


def _value(node, name, default=None):
    child = _child(node, name)
    return child['props'][0] if child and child['props'] else default


def fbx_meshes(path):
    nodes = binary_fbx(path)
    objects = next(x for x in nodes if x['name'] == 'Objects')
    meshes = []
    for node in objects['children']:
        if node['name'] != 'Geometry' or node['props'][-1] != 'Mesh':
            continue
        raw = _value(node, 'Vertices', [])
        positions = [tuple(raw[i:i+3]) for i in range(0, len(raw), 3)]
        polygons, polygon, corners, corner = [], [], [], 0
        for index in _value(node, 'PolygonVertexIndex', []):
            polygon.append(-index-1 if index < 0 else index)
            if index < 0:
                polygons.append(polygon)
                corners.append(list(range(corner, corner+len(polygon))))
                corner += len(polygon)
                polygon = []
        if polygon:
            raise ValueError('Unterminated FBX polygon')
        if any(len(poly) != 3 for poly in polygons):
            raise ValueError('FBX source is not triangulated; exact importer triangulation cannot be inferred')
        layer = _child(node, 'LayerElementUV')
        uvs = None
        if layer:
            values = _value(layer, 'UV', [])
            mapping = _value(layer, 'MappingInformationType')
            reference = _value(layer, 'ReferenceInformationType')
            indices = _value(layer, 'UVIndex', [])
            uvs = []
            for poly, face_corners in zip(polygons, corners):
                face = []
                for vertex, index in zip(poly, face_corners):
                    lookup = index if mapping == 'ByPolygonVertex' else vertex if mapping in ('ByVertice', 'ByControlPoint') else None
                    if lookup is None or reference not in ('Direct', 'IndexToDirect'):
                        raise ValueError('Unsupported FBX UV mapping')
                    direct = indices[lookup] if reference == 'IndexToDirect' else lookup
                    face.append(tuple(values[direct*2:direct*2+2]))
                uvs.append(face)
        meshes.append({'name': node['props'][1].split('\x00')[0], 'positions': positions,
                       'triangles': polygons, 'uv_faces': uvs})
    if not meshes:
        raise ValueError('No FBX mesh geometry')
    return meshes


def glb_meshes(path, node_name=None):
    data = Path(path).read_bytes()
    if len(data) < 20 or struct.unpack_from('<III', data) != (0x46546C67, 2, len(data)):
        raise ValueError('Invalid GLB header')
    chunks, offset = {}, 12
    while offset+8 <= len(data):
        size, kind = struct.unpack_from('<II', data, offset)
        if offset+8+size > len(data):
            raise ValueError('Truncated GLB chunk')
        chunks[kind] = data[offset+8:offset+8+size]
        offset += 8+size
    doc, blob = json.loads(chunks[0x4E4F534A]), chunks.get(0x004E4942, b'')

    def accessor(index):
        entry = doc['accessors'][index]
        if 'sparse' in entry or 'bufferView' not in entry:
            raise ValueError('Sparse/accessor-less GLB is not supported by diagnostics')
        view = doc['bufferViews'][entry['bufferView']]
        if view.get('buffer', 0) != 0 or 'extensions' in view:
            raise ValueError('External/compressed GLB buffers are not supported')
        fmt = {5120:'b', 5121:'B', 5122:'h', 5123:'H', 5125:'I', 5126:'f'}[entry['componentType']]
        width = {'SCALAR':1, 'VEC2':2, 'VEC3':3, 'VEC4':4}[entry['type']]
        size = struct.calcsize(fmt)*width
        stride = view.get('byteStride', size)
        start = view.get('byteOffset', 0) + entry.get('byteOffset', 0)
        if stride < size or start+(entry['count']-1)*stride+size > view.get('byteOffset', 0)+view['byteLength']:
            raise ValueError('Invalid GLB accessor bounds')
        values = [struct.unpack_from('<'+fmt*width, blob, start+i*stride) for i in range(entry['count'])]
        if entry.get('normalized') and fmt != 'f':
            divisor = {5120:127, 5121:255, 5122:32767, 5123:65535, 5125:4294967295}[entry['componentType']]
            values = [tuple(max(-1.0, x/divisor) for x in value) for value in values]
        return values

    meshes = []
    for node in doc.get('nodes', []):
        if 'mesh' not in node or node_name and node.get('name') != node_name:
            continue
        mesh = doc['meshes'][node['mesh']]
        positions, triangles, uvs = [], [], []
        for primitive in mesh['primitives']:
            if primitive.get('mode', 4) != 4 or 'extensions' in primitive:
                raise ValueError('Only uncompressed GLB triangle lists supported')
            vertices = accessor(primitive['attributes']['POSITION'])
            indices = [x[0] for x in accessor(primitive['indices'])] if 'indices' in primitive else list(range(len(vertices)))
            if len(indices) % 3:
                raise ValueError('GLB index count is not a triangle list')
            uv = accessor(primitive['attributes']['TEXCOORD_0']) if 'TEXCOORD_0' in primitive['attributes'] else None
            base = len(positions)
            positions.extend(vertices)
            for i in range(0, len(indices), 3):
                face = indices[i:i+3]
                triangles.append([base+x for x in face])
                uvs.append([uv[x] for x in face] if uv else None)
        meshes.append({'name': node.get('name', mesh.get('name', 'mesh')), 'positions': positions,
                       'triangles': triangles, 'uv_faces': uvs, 'node_transform': {k:node[k] for k in
                           ('matrix', 'translation', 'rotation', 'scale') if k in node}})
    if not meshes:
        raise ValueError(f'No GLB node matched: {node_name}')
    return meshes


def statistics(mesh):
    positions, triangles, uvs = mesh['positions'], mesh['triangles'], mesh['uv_faces']
    if not positions or any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in positions):
        raise ValueError('Empty or non-finite source positions')
    lo = [min(v[i] for v in positions) for i in range(3)]
    hi = [max(v[i] for v in positions) for i in range(3)]
    extent = max(b-a for a,b in zip(lo, hi)) or 1
    zero, near, uv_zero, samples = 0, 0, 0, []
    zero_examples, uv_examples = [], []
    min_edge = math.inf
    for index, face in enumerate(triangles):
        if any(not 0 <= i < len(positions) for i in face):
            raise ValueError('Source index out of bounds')
        a,b,c = (positions[i] for i in face)
        ab, ac = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        cross = [ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0]]
        area2 = math.sqrt(sum(x*x for x in cross))
        zero += area2 == 0
        if area2 == 0 and len(zero_examples) < 32:
            zero_examples.append({'triangle_index': index, 'vertex_indices': face, 'positions': [a,b,c]})
        near += area2/(extent*extent) <= 1e-10
        if area2/(extent*extent) <= 1e-10 and len(samples) < 12:
            samples.append(index)
        for p,q in ((a,b),(b,c),(c,a)):
            min_edge = min(min_edge, math.sqrt(sum((p[i]-q[i])**2 for i in range(3))))
        uv = uvs[index] if uvs else None
        if uv:
            if len(uv) != 3 or any(len(v) != 2 or not all(math.isfinite(x) for x in v) for v in uv):
                raise ValueError('Invalid/non-finite source UV coordinates')
            det = (uv[1][0]-uv[0][0])*(uv[2][1]-uv[0][1]) - (uv[1][1]-uv[0][1])*(uv[2][0]-uv[0][0])
            uv_zero += abs(det) <= 1e-12
            if abs(det) <= 1e-12 and len(uv_examples) < 32:
                uv_examples.append(index)
    return {'name': mesh['name'], 'vertices': len(positions), 'triangles': len(triangles),
            'bounds_min': lo, 'bounds_max': hi, 'zero_area_triangles': zero,
            'near_zero_area_triangles': near, 'near_zero_relative_threshold': 1e-10,
            'zero_uv_area_triangles': uv_zero, 'uv_checked': bool(uvs),
            'min_edge_source_units': min_edge if triangles else None, 'example_triangle_indices': samples,
            'zero_area_examples': zero_examples, 'zero_uv_example_indices': uv_examples, 'triangle_index_base': 0,
            'coordinate_space': 'source_local', 'node_transform': mesh.get('node_transform', {})}


def analyze(path, node_name=None):
    meshes = fbx_meshes(path) if Path(path).suffix.lower() == '.fbx' else glb_meshes(path, node_name)
    return [statistics(mesh) for mesh in meshes]
