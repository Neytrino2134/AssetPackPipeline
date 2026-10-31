"""Collect bounded, secret-free evidence for the native migration checkpoint."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
root=Path(__file__).resolve().parents[3]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
full=root/'Saved/NativeFullHost/Saved/AssetPackPipeline'
e2e=read(full/'E2E/8bcf273ec7914ca38fbada9520fdbbb4/result.json')
delivery=read(full/'Runs/a453c77b7b6446999c5ac81792c4483c/report.json')
soak=read(root/'Docs/Native023/NativeSoak.json')
smoke=read(root/'Saved/NativePackage020/HostProject/Saved/AssetPackPipeline/NativeSmoke.json')
flight=read(root/'Docs/Native023/FlightRegression.json')
assert e2e['passed'] and not e2e.get('error') and soak['passed'] and smoke['passed'] and flight['passed']
assert delivery['fresh_project_verification']=='passed'
checks=delivery['verification_spec']['asset_checks']
assert len(checks)==20 and all(c['passed'] for c in checks)
zip_path=Path(e2e['result']['zip_path'])
with ZipFile(zip_path) as archive:
    assert archive.testzip() is None
    lods=sum(p.endswith('_LODS.uasset') for p in archive.namelist())
    mids=sum(p.endswith('_MID.uasset') for p in archive.namelist())
assert lods==mids==10
result={'version':'0.23.0','date':'2026-10-31','engine':'UE 5.8.4 / Win64',
        'unit_tests':113,'e2e_format':'FBX','unique_models':10,'meshes':20,
        'fresh_project_verification':'passed','project_zip_integrity':'passed',
        'project_zip_sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        'overview_png_count':e2e['result']['renders']['count'],'overview_visually_checked':True,
        'cleanup_deleted':e2e['cleanup']['deleted_count'],'cleanup_retained':e2e['cleanup']['retained_count'],
        'flight':flight,'core_widget_soak':soak,'final_layout_smoke':smoke,
        'limits':['Widget soak used core panel before final compact layout/model-preference restoration; final layout passed a separate short lifecycle test.',
                  'No live OpenAI request: key unavailable in accessible environment/local settings.',
                  'Programmatic text tests do not emulate real IME or OS Alt-Tab.',
                  'No Fab submission or artistic acceptance.'],
        'measurements':[{'id':c['id'],'source_kind':c['source_kind'],'lod_count':c['lod_count'],
                         'triangles':c['triangles'],'nanite_triangles':c['nanite_triangles']} for c in checks]}
(root/'Docs/Native023/Verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('Native023 evidence: passed')
