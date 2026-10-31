import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Content' / 'Python'))
from asset_pack_pipeline import geometry, diagnostics


def fbx_property(value):
    if isinstance(value, str):
        data = value.encode()
        return b'S' + struct.pack('<I', len(data)) + data
    if isinstance(value, int):
        return b'L' + struct.pack('<q', value)
    kind, values = value
    raw = struct.pack('<'+kind*len(values), *values)
    compressed = zlib.compress(raw)
    return kind.encode() + struct.pack('<III', len(values), 1, len(compressed)) + compressed


def fbx_node(node, start, wide):
    name, props, children = node
    header = '<QQQB' if wide else '<IIIB'
    size = struct.calcsize(header)
    properties = b''.join(fbx_property(p) for p in props)
    prefix = name.encode() + properties
    content = b''
    for child in children:
        content += fbx_node(child, start+size+len(prefix)+len(content), wide)
    content += b'\0'*size
    end = start+size+len(prefix)+len(content)
    return struct.pack(header, end, len(props), len(properties), len(name)) + prefix + content


def fbx_fixture(wide=False):
    vertices = [0.,0.,0., 1.,0.,0., 0.,1.,0., 0.,0.,0.]
    geometry_node = ('Geometry', [1, 'Mesh\0\x01Geometry', 'Mesh'], [
        ('Vertices', [('d', vertices)], []),
        ('PolygonVertexIndex', [('i', [0,1,-3,0,3,-2])], []),
        ('LayerElementUV', [0], [('MappingInformationType', ['ByPolygonVertex'], []),
                                ('ReferenceInformationType', ['Direct'], []),
                                ('UV', [('d', [0.,0.,1.,0.,0.,1.,0.,0.,0.,0.,1.,0.])], [])])])
    root = ('Objects', [], [geometry_node])
    return b'Kaydara FBX Binary  \0\x1a\0' + struct.pack('<I', 7500 if wide else 7400) + fbx_node(root, 27, wide) + b'\0'*(25 if wide else 13)


def glb_fixture():
    vertices = [(0,0,0,999), (1,0,0,999), (0,1,0,999), (0,0,0,999)]
    raw = b''.join(struct.pack('<4f', *v) for v in vertices) + struct.pack('<6H', 0,1,2,0,3,1)
    raw += struct.pack('<8f', 0,0,1,0,0,1,0,0)
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(raw)}],
           'bufferViews': [{'buffer':0,'byteOffset':0,'byteLength':64,'byteStride':16},
                           {'buffer':0,'byteOffset':64,'byteLength':12},
                           {'buffer':0,'byteOffset':76,'byteLength':32}],
           'accessors': [{'bufferView':0,'componentType':5126,'count':4,'type':'VEC3'},
                         {'bufferView':1,'componentType':5123,'count':6,'type':'SCALAR'},
                         {'bufferView':2,'componentType':5126,'count':4,'type':'VEC2'}],
           'nodes':[{'name':'Mesh','mesh':0}],
           'meshes':[{'primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':2},'indices':1}]}]}
    text = json.dumps(doc).encode()
    text += b' ' * (-len(text)%4)
    return struct.pack('<III', 0x46546c67, 2, 12+8+len(text)+8+len(raw)) + struct.pack('<II',len(text),0x4e4f534a)+text + struct.pack('<II',len(raw),0x004e4942)+raw


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_binary_fbx_compressed_arrays_both_headers(self):
        for wide in (False, True):
            path = self.root / 'mesh.fbx'
            path.write_bytes(fbx_fixture(wide))
            stats = geometry.analyze(path)[0]
            self.assertEqual(stats['triangles'], 2)
            self.assertEqual(stats['zero_area_triangles'], 1)
            self.assertEqual(stats['zero_uv_area_triangles'], 1)

    def test_glb_strided_positions_and_uv(self):
        path = self.root / 'mesh.glb'
        path.write_bytes(glb_fixture())
        stats = geometry.analyze(path, 'Mesh')[0]
        self.assertEqual(stats['triangles'], 2)
        self.assertEqual(stats['zero_area_triangles'], 1)
        self.assertEqual(stats['zero_uv_area_triangles'], 1)
        with self.assertRaises(ValueError):
            geometry.analyze(path, 'Unknown')

    def test_near_zero_is_distinct_from_exact_zero(self):
        stats = geometry.statistics({'name':'tiny','positions':[(0,0,0),(1,0,0),(1,1e-12,0)],
                                     'triangles':[[0,1,2]],'uv_faces':None})
        self.assertEqual(stats['zero_area_triangles'], 0)
        self.assertEqual(stats['near_zero_area_triangles'], 1)

    def test_malformed_and_unsupported_files(self):
        path = self.root / 'invalid.fbx'
        path.write_bytes(b'; ASCII FBX')
        with self.assertRaises(ValueError):
            geometry.analyze(path)
        path = self.root / 'invalid.glb'
        path.write_bytes(glb_fixture()[:-4])
        with self.assertRaises(ValueError):
            geometry.analyze(path)

    def test_nonfinite_geometry_and_indices(self):
        for vertices, indices in [([(float('nan'),0,0)], [[0,0,0]]), ([(0,0,0)], [[0,1,2]])]:
            with self.assertRaises(ValueError):
                geometry.statistics({'name':'bad','positions':vertices,'triangles':indices,'uv_faces':None})

    def test_source_report_and_classification_without_unreal(self):
        (self.root/'mesh.fbx').write_bytes(fbx_fixture())
        (self.root/'mesh.glb').write_bytes(glb_fixture())
        (self.root/'MeshInfo.json').write_text(json.dumps({'meshes':[{'asset':'Asset_01','name':'Mesh','role':'LOD',
                                                                   'lod_index':0,'triangles':2,
                                                                   'files':{'FBX':'mesh.fbx','GLB':'mesh.glb'}}]}))
        manifest = {'profile':{'source_root':str(self.root)},
                    'assets':[{'id':'Asset_01','lods':[{'index':0,'triangles':2}]}]}
        source = diagnostics.source_report(manifest)
        self.assertTrue(source['assets'][0]['has_source_defects'])
        self.assertEqual(len(diagnostics.cases(source)), 4)
        self.assertEqual(source['assets'][0]['formats']['FBX'][0]['zero_area_examples'][0]['triangle_index'], 1)
        report = {'run_id':'test','status':'passed','source_analysis':source,'assets':[]}
        diagnostics.finish_report(report)
        self.assertTrue(report['source_files_unchanged'])
        self.assertIn('подтверждён дефект', report['conclusions'][0]['evidence'][0])
        (self.root/'mesh.fbx').write_bytes(b'changed')
        diagnostics.finish_report(report)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['source_files_unchanged'])


if __name__ == '__main__':
    unittest.main()
