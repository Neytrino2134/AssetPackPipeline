"""Source evidence and controlled import experiments. Never edits source exports."""
import copy
import json
from pathlib import Path
from . import discovery, geometry


def source_report(manifest):
    profile = manifest['profile']
    root = Path(profile['source_root']).resolve()
    catalog = discovery.read_json(discovery.contained(root, profile.get('mesh_info', 'MeshInfo.json')))
    entries = {(e['asset'], e['lod_index']): e for e in catalog['meshes'] if e.get('role') == 'LOD'}
    cache, hashes, assets = {}, dict(manifest.get('source_hashes', {})), []
    catalog_path = discovery.contained(root, profile.get('mesh_info', 'MeshInfo.json'))
    hashes[str(catalog_path)] = discovery.digest(catalog_path)
    for asset in manifest['assets']:
        row = {'id': asset['id'], 'formats': {}, 'findings': [], 'diagnostic': True,
               'lod_count': len(asset['lods']), 'triangles': [x['triangles'] for x in asset['lods']]}
        for fmt in ('FBX', 'GLB'):
            rows = []
            for lod in asset['lods']:
                try:
                    if profile.get('nanite_enabled', False):
                        effective = discovery.profiles.effective(profile, asset['id'])
                        entry, _ = discovery.select_detail([e for e in catalog['meshes']
                            if e['asset'] == asset['id'] and e.get('role') in ('MID', 'HIGH')], fmt, effective['nanite_source'])
                    else:
                        entry = entries[(asset['id'], lod['index'])]
                    path = discovery.contained(root, entry['files'][fmt])
                    key = str(path)
                    if key not in cache:
                        hashes[key] = discovery.digest(path)
                        try:
                            cache[key] = geometry.analyze(path)
                        except Exception as error:
                            cache[key] = error
                    if isinstance(cache[key], Exception):
                        raise cache[key]
                    candidates = cache[key] if fmt == 'FBX' else [m for m in cache[key] if m['name'] == entry['name']]
                    if len(candidates) != 1:
                        raise ValueError('Ambiguous source mesh mapping')
                    stats = dict(candidates[0], lod_index=lod['index'], source_file=key,
                                 expected_triangles=lod['triangles'], supported=True)
                    if stats['triangles'] != lod['triangles']:
                        row['findings'].append({'code': 'CATALOG_TRIANGLE_MISMATCH', 'format': fmt, 'lod': lod['index']})
                    for name, code in [('zero_area_triangles', 'SOURCE_ZERO_AREA'),
                                       ('near_zero_area_triangles', 'SOURCE_NEAR_ZERO_AREA'),
                                       ('zero_uv_area_triangles', 'SOURCE_ZERO_UV_AREA')]:
                        if stats[name]:
                            row['findings'].append({'code': code, 'format': fmt, 'lod': lod['index'], 'count': stats[name]})
                except Exception as error:
                    stats = {'lod_index': lod['index'], 'supported': False, 'error': str(error)}
                rows.append(stats)
            row['formats'][fmt] = rows
        row['source_quality_passed'] = not row['findings'] and all(
            x['supported'] for rows in row['formats'].values() for x in rows)
        row['has_source_defects'] = any(f['code'] == 'SOURCE_ZERO_AREA' for f in row['findings'])
        row['status'] = 'passed'  # Analysis completion; source_quality_passed is separate.
        assets.append(row)
    return {'assets': assets, 'source_hashes': hashes, 'publication_ready': False,
            'source_quality_passed': all(a['source_quality_passed'] for a in assets),
            'analysis_limits': ['Measurements are in source-local coordinates, not Unreal world units.',
                                'Near-zero relative area threshold 1e-10 is descriptive, not UE removal tolerance.',
                                'Binary triangulated FBX and uncompressed GLB supported; unsupported files are reported.',
                                'Does not certify manifold topology, normals, self-intersections or the original Blender file.']}


def cases(source):
    return [{'id': f'{asset["id"]} [{fmt} remove={remove}]', 'asset_id': asset['id'],
             'format': fmt, 'remove_degenerates': remove, 'status': 'pending', 'diagnostic': True}
            for asset in source['assets'] for fmt, rows in asset['formats'].items()
            if all(row['supported'] for row in rows) for remove in (True, False)]


def run_case(manifest, case, run_id, folder):
    import unreal as u
    from . import runtime
    runtime.assert_editor_idle()
    config = copy.deepcopy(manifest['profile'])
    fmt, remove = case['format'], case['remove_degenerates']
    config.update(source_format=fmt, asset_ids=[case['asset_id']], remove_degenerates=remove,
                  destination_root=f'/Game/AssetPackPipeline_Diagnostics/{run_id}/{case["asset_id"]}/{fmt}_{int(remove)}')
    path = Path(folder) / f'{case["asset_id"]}_{fmt}_{int(remove)}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    probe = discovery.scan(path)
    asset = probe['assets'][0]
    stage_id = f'{run_id}_{fmt}_{int(remove)}'
    mesh = runtime._fbx(probe, asset, None, stage_id) if fmt == 'FBX' else runtime._glb(probe, asset, None, stage_id)
    # Interchange may enable Nanite by default; its fallback count is not the
    # source geometry. Disable it and finish the rebuild before measurements.
    nanite = mesh.get_editor_property('nanite_settings')
    nanite.enabled = False
    mesh.set_editor_property('nanite_settings', nanite)
    runtime.save(mesh)
    subsystem = runtime.smes()
    count = subsystem.get_lod_count(mesh)
    before = [mesh.get_num_triangles(i) for i in range(count)]
    before_flags = []
    for index in range(count):
        options = subsystem.get_lod_build_settings(mesh, index)
        before_flags.append(options.remove_degenerates)
        if fmt == 'GLB':
            options.remove_degenerates = remove
            subsystem.set_lod_build_settings(mesh, index, options)
    runtime.save(mesh)
    actual = [mesh.get_num_triangles(i) for i in range(count)]
    flags = [subsystem.get_lod_build_settings(mesh, i).remove_degenerates for i in range(count)]
    if any(flag != remove for flag in flags):
        raise RuntimeError(f'Effective build flags disagree with the requested variant: {flags}')
    return {'id': case['id'], 'asset_id': case['asset_id'], 'format': fmt, 'diagnostic': True,
            'remove_degenerates': remove, 'nanite_enabled': False, 'lod_count': count,
            'expected_triangles': [x['triangles'] for x in asset['lods']], 'triangles': actual,
            'before_build_change': before, 'effective_remove_before': before_flags, 'effective_remove_after': flags,
            'mesh_path': mesh.get_path_name(), 'passed': True}


def finish_report(report):
    source = report['source_analysis']
    changed = [path for path, sha in source['source_hashes'].items()
               if not Path(path).is_file() or discovery.digest(path) != sha]
    report['source_files_unchanged'] = not changed
    report['changed_sources'] = changed
    conclusions = []
    for asset in source['assets']:
        entries = [x for x in report['assets'] if x.get('asset_id') == asset['id'] and x.get('status') == 'passed']
        variants = {(x['format'], x['remove_degenerates']): x for x in entries}
        evidence = []
        if asset['has_source_defects']:
            evidence.append('Нулевые треугольники обнаружены в файлах экспорта до Unreal: подтверждён дефект геометрии экспорта.')
        for fmt in ('FBX', 'GLB'):
            on, off = variants.get((fmt, True)), variants.get((fmt, False))
            if on and off and on['triangles'] != off['triangles']:
                evidence.append(f'{fmt}: изменение Remove Degenerates меняет число треугольников; подтверждено влияние обработки импорта/сборки.')
            if off and off['triangles'] != off['expected_triangles']:
                evidence.append(f'{fmt}: даже при Remove Degenerates=False число отличается от каталога; отключение флажка не исправляет исходник.')
        conclusions.append({'id': asset['id'], 'evidence': evidence,
                            'recommended_action': 'Проверить перечисленные полигоны и UV в исходном DCC, исправить и повторно экспортировать. Автоматическое исправление не выполнялось.'
                            if asset['has_source_defects'] else 'Проверить предупреждения и результаты вариантов; качество исходника не сертифицировано.'})
    report.update(conclusions=conclusions, publication_ready=False)
    if changed:
        report['status'] = 'failed'
        report['error'] = 'Sources changed during diagnostics; repeat on a stable export set'


def explain_mismatches(manifest, asset, actual):
    """Attach source evidence to ordinary validation failures, without importing."""
    rows = []
    cache = {}
    for lod in asset['lods']:
        index = lod['index']
        imported = actual[index] if index < len(actual) else None
        if imported == lod['triangles']:
            continue
        row = {'lod_index': index, 'expected_triangles': lod['triangles'], 'imported_triangles': imported,
               'removed_triangles': lod['triangles']-imported if imported is not None else None}
        try:
            if lod['file'] not in cache:
                cache[lod['file']] = geometry.analyze(lod['file'])
            meshes = cache[lod['file']]
            matches = meshes if manifest['profile']['source_format'].upper() == 'FBX' else [x for x in meshes if x['name'] == lod['node']]
            if len(matches) != 1:
                raise ValueError('Ambiguous source mapping')
            source = matches[0]
            row['source_evidence'] = source
            row['reason'] = 'SOURCE_ZERO_AREA_CONFIRMED' if source['zero_area_triangles'] else 'IMPORT_DIFFERENCE_REQUIRES_PROBE'
            row['message'] = ('В исходном экспорте есть треугольники нулевой площади. Дополнительные потери нужно проверить матрицей импорта.'
                              if source['zero_area_triangles'] else 'Счётчик после импорта отличается; запустите сравнение вариантов импорта.')
        except Exception as error:
            row.update(reason='SOURCE_ANALYSIS_UNAVAILABLE', error=str(error))
        rows.append(row)
    return rows


def markdown(report):
    source = report.get('source_analysis', {})
    lines = ['# Диагностика геометрии', '', f"Run: {report['run_id']}", '', f"Задача: {report['status']}",
             '', 'Статус задачи означает завершение диагностики, а не пригодность мешей к публикации.', '',
             '| Модель | Формат | LOD | Треугольники | Нулевая площадь | Почти нулевые | Нулевая UV-площадь |',
             '|---|---|---:|---:|---:|---:|---:|']
    for asset in source.get('assets', []):
        for fmt, rows in asset['formats'].items():
            for row in rows:
                if row['supported']:
                    lines.append(f"| {asset['id']} | {fmt} | {row['lod_index']} | {row['triangles']} | {row['zero_area_triangles']} | {row['near_zero_area_triangles']} | {row['zero_uv_area_triangles']} |")
                else:
                    lines.append(f"| {asset['id']} | {fmt} | {row['lod_index']} | unsupported: {row['error']} | — | — | — |")
    lines += ['', '## Варианты Unreal', '', '| Модель | Формат | Remove Degenerates | LOD0…N | Статус |', '|---|---|---|---|---|']
    for row in report.get('assets', []):
        if 'format' in row:
            lines.append(f"| {row.get('asset_id')} | {row['format']} | {row['remove_degenerates']} | {' / '.join(map(str,row.get('triangles', [])))} | {row['status']} |")
    for item in report.get('conclusions', []):
        lines += ['', '## ' + item['id'], ''] + ['- '+s for s in item['evidence']] + ['', item['recommended_action']]
    lines += ['', '## Ограничения', ''] + ['- '+s for s in source.get('analysis_limits', [])]
    lines += ['', 'Source files unchanged: ' + str(report.get('source_files_unchanged', 'not checked yet')), '']
    return '\n'.join(lines)
