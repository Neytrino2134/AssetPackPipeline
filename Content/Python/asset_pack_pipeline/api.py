"""Shared entry points for menus, MCP and unattended editor scripts."""
import json
import re
import time
import traceback
import uuid
from pathlib import Path
from . import __version__, discovery

_jobs = {}
_active = None
_tick = None
_advancing = False
_preview_states = {}
_verification_processes = {}
_flythrough_states = {}


def _ue():
    import unreal
    return unreal


def _runs():
    return Path(_ue().Paths.project_saved_dir()).resolve() / 'AssetPackPipeline' / 'Runs'


def _save(report):
    folder = _runs() / report['run_id']
    folder.mkdir(parents=True, exist_ok=True)
    report['report_path'] = str(folder / 'report.json')
    temp = folder / 'report.tmp'
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(folder / 'report.json')
    (folder / 'report.md').write_text(
        '# Asset Pack Pipeline\n\n' + f"Run: {report['run_id']}\n\nStatus: {report['status']}\n\n"
        + '\n'.join(f"- {a['id']}: {a['status']} {a.get('error', '')}" for a in report.get('assets', [])),
        encoding='utf-8')
    exclusions = report.get('excluded_assets', report.get('excluded_sources', []))
    if exclusions:
        with (folder/'report.md').open('a', encoding='utf-8') as stream:
            stream.write('\n\nExcluded assets (partial pack):\n'+ '\n'.join(
                f"- {row['id']} [{row['stage']}]: {row['reason']}" for row in exclusions))
    warned=[row for row in report.get('assets',[]) if row.get('warnings')]
    if warned:
        with (folder/'report.md').open('a',encoding='utf-8') as stream:
            stream.write('\n\nQuality warnings (models retained):\n'+'\n'.join(
                f"- {row['id']}: {row.get('validation_summary') or str(len(row['warnings']))+' warning(s)'}" for row in warned))
    if report.get('kind')=='flythrough':
        with (folder/'report.md').open('a',encoding='utf-8') as stream:
            stream.write('\n\nContinuous MRQ camera sequence\n\n'+
                f"Models: {len(report['model_ids'])}; frames: {report.get('rendered_frame_count',0)}/{report['flythrough_settings']['frame_count']}\n\n"+
                f"Sequence: {report['sequence_path']}\n\nMap: {report['map_path']}\n\n"+
                f"Playback: {report.get('playback_page','Render pending / partial frames retained')}\n\n"+
                'PNG sequence, not an encoded video. Quality warnings are retained; appearance review is pending.\n')
    if report.get('kind') in ('source_diagnostics', 'import_diagnostics'):
        from . import diagnostics
        (folder / 'report.md').write_text(diagnostics.markdown(report), encoding='utf-8')
    if report.get('kind') in ('preview_export','individual_previews'):
        lines = ['# Preview export', '', f"Status: {report['status']}", '',
                 'Images require visual review; publication readiness is not certified.', '']
        for item in report['assets']:
            lines.append(f"- {item['id']}: {item['status']} — {item['output_path']}")
            if item.get('sha256'):
                lines.append(f"  {item['width']} × {item['height']}, SHA256: {item['sha256']}")
            if item.get('warnings'):
                lines.append(f"  Quality warnings: {len(item['warnings'])}; model retained")
        if report.get('error'):
            lines.extend(['', report['error']])
        (folder / 'report.md').write_text('\n'.join(lines), encoding='utf-8')


def readiness():
    u = _ue()
    return {'plugin_version': __version__, 'engine_version': u.SystemLibrary.get_engine_version(),
            'project': str(Path(u.Paths.project_dir()).resolve()),
            'capabilities': {'scan': True, 'plan': True, 'import': True,
                             'overview': True, 'lod_review': True, 'source_diagnostics': True,
                             'asset_overrides': True, 'material_controls': True, 'settings_update': True,
                             'import_diagnostics': True, 'preview_export': True, 'incremental': True,
                             'resume': True, 'staging_cleanup': True, 'delivery': True, 'delivery_verification': True,
                             'individual_previews':True,'windows_cook':True,'automatic_lod_review':True,
                             'nanite_import':True,'nanite_mid_high_selection':True,
                             'review_candidate':True,'retain_all_models':True,'geometry_warnings':True,'review_bundle':True,
                             'flythrough':hasattr(u,'MoviePipelineQueueSubsystem') and hasattr(u,'MovieSceneSequenceExtensions')},
            'active_run': _active,
            'static_mesh_api': hasattr(u.StaticMeshEditorSubsystem, 'set_lod_from_static_mesh')}


def plan(profile_path, operation='import'):
    manifest = discovery.scan(profile_path)
    from . import runtime
    runtime.assert_editor_idle()
    conflicts = runtime.conflicts(manifest)
    from . import incremental
    enabled = manifest['profile'].get('incremental', True)
    for asset in manifest['assets']:
        if enabled and not conflicts:
            hit, reason, _ = incremental.check(manifest, asset, operation, readiness()['engine_version'])
            asset.update(action='skip' if hit else 'process', action_reason=reason)
        else:
            asset.update(action='process', action_reason='disabled' if not enabled else 'conflict')
    return dict(manifest, conflicts=conflicts, ready=not conflicts,
                incremental_summary={'skip': sum(a['action'] == 'skip' for a in manifest['assets']),
                                     'process': sum(a['action'] == 'process' for a in manifest['assets'])})


def status(run_id):
    if not re.fullmatch('[0-9a-f]{32}', run_id):
        raise ValueError('Invalid run_id')
    if run_id in _jobs:
        return _jobs[run_id]
    report = discovery.read_json(_runs() / run_id / 'report.json')
    if report['status'] == 'running':
        report.update(status='interrupted', interrupted=True,
                      error='Editor restarted before completion; use resume_job after source verification')
        for item in report['assets']:
            if item['status'] == 'running':
                item.update(status='interrupted', error='Interrupted during this asset; recheck before retry')
        _save(report)
    return report


def start(profile_path, settings_only=False, resumed_from=None):
    global _active, _tick
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    operation = 'settings_update' if settings_only else 'import'
    manifest = plan(profile_path, operation)
    if manifest['conflicts']:
        raise ValueError('Conflicting assets: ' + ', '.join(manifest['conflicts']))
    from . import runtime
    runtime.assert_targets_clean(manifest)
    if resumed_from is not None:
        old = resumed_from['manifest']
        if manifest['profile_hash'] != old['profile_hash'] or manifest['source_hashes'] != old['source_hashes']:
            raise RuntimeError('Frozen profile or source files changed; start a new job instead of resuming')
        def selected_contract(assets):
            return [{key: asset[key] for key in ('id', 'mesh_path', 'lods', 'textures', 'effective_settings')}
                    for asset in assets]
        if selected_contract(manifest['assets']) != selected_contract(old['assets']):
            raise RuntimeError('Selected asset mapping or MeshInfo changed since interrupted run')
    if settings_only:
        for asset in manifest['assets']:
            mesh = _ue().load_asset(asset['mesh_path'])
            if not isinstance(mesh, _ue().StaticMesh) or not runtime.owned(mesh, manifest['profile']['pack_id']):
                raise RuntimeError(f"Import the owned mesh before updating settings: {asset['mesh_path']}")
    run_id = uuid.uuid4().hex
    folder = _runs() / run_id
    folder.mkdir(parents=True, exist_ok=False)
    snapshot = folder / 'profile.json'
    snapshot.write_text(json.dumps(manifest['profile'], ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'schema_version': 1, 'run_id': run_id, 'status': 'running',
              'kind': operation, 'resume_schema': 1,
              'plugin_version': __version__, 'engine_version': readiness()['engine_version'],
              'project_dir': str(Path(_ue().Paths.project_dir()).resolve()),
              'profile_snapshot': str(snapshot), 'resumed_from': resumed_from['run_id'] if resumed_from else None,
              'manifest': manifest, 'started_at': time.time(), 'cancel_requested': False,
              'assets': [{'id': a['id'], 'status': 'pending'} for a in manifest['assets']],
              'excluded_sources': manifest.get('excluded_sources', []),
              'visual_review': 'pending', 'overview': 'not_requested', 'delivery': 'not_implemented'}
    _jobs[run_id] = report
    _active = run_id
    _save(report)
    if '-run=' not in _ue().SystemLibrary.get_command_line().lower():
        _tick = _ue().register_slate_post_tick_callback(_advance)
    return run_id


def list_runs(limit=20):
    """Recent persisted import/settings jobs for the queue tab and MCP."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    rows = []
    for path in sorted(_runs().glob('*/report.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            report = discovery.read_json(path)
            if report.get('kind') not in ('import', 'settings_update'):
                continue
            if report['status'] == 'running' and report['run_id'] != _active:
                report = status(report['run_id'])
            rows.append({key: report.get(key) for key in ('run_id', 'kind', 'status', 'started_at', 'finished_at',
                                                         'resumed_from', 'report_path')})
            if len(rows) >= limit:
                break
        except (OSError, ValueError, KeyError):
            continue
    return rows


def resume(run_id):
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    old = status(run_id)
    if old.get('kind') not in ('import', 'settings_update') or old.get('resume_schema') != 1:
        raise ValueError('Run has no compatible resume snapshot')
    if old['status'] not in ('failed', 'cancelled', 'interrupted'):
        raise ValueError(f"Run is not resumable: {old['status']}")
    if old.get('project_dir') != str(Path(_ue().Paths.project_dir()).resolve()):
        raise ValueError('Run belongs to another project')
    if old.get('plugin_version') != __version__ or old.get('engine_version') != readiness()['engine_version']:
        raise ValueError('Plugin or engine version changed; start a new job')
    snapshot = (_runs() / run_id / 'profile.json').resolve()
    if not snapshot.is_file() or str(snapshot) != old.get('profile_snapshot'):
        raise ValueError('Frozen profile snapshot missing or misplaced')
    return start(str(snapshot), old['kind'] == 'settings_update', resumed_from=old)


def cancel(run_id):
    report = status(run_id)
    if report['status'] == 'running':
        if report.get('kind') in ('overview', 'lod_review', 'staging_cleanup', 'delivery'):
            raise RuntimeError('Overview generation is atomic and cannot be cancelled mid-map')
        report['cancel_requested'] = True
        _save(report)
    return report


def _advance(delta=0):
    global _advancing
    if _advancing:
        return
    _advancing = True
    try:
        _advance_impl(delta)
    finally:
        _advancing = False


def _advance_impl(delta=0):
    global _active, _tick
    if not _active:
        return
    report = _jobs[_active]
    if report.get('kind')=='flythrough':
        from . import flythrough
        state=_flythrough_states[report['run_id']]
        try:
            done=flythrough.advance(report,state)
        except Exception as error:
            state['executor'].cancel_all_jobs()
            report.update(error=str(error),traceback=traceback.format_exc(),status='failed');done=True
        if done:
            if report['status']=='running':report['status']='cancelled' if report['cancel_requested'] else 'passed'
            report['assets'][0]['status']=report['status'];report['finished_at']=time.time()
            flythrough.release(state)
            _flythrough_states.pop(report['run_id'],None);_active=None
            if _tick is not None:_ue().unregister_slate_post_tick_callback(_tick);_tick=None
        report['rendered_frame_count']=len(list(Path(report['output_directory']).glob('frame_*.png')))
        if done or report['rendered_frame_count']!=state.get('last_count'):
            state['last_count']=report['rendered_frame_count'];_save(report)
        return
    if report.get('kind') in ('delivery_verification','delivery_cook'):
        from . import delivery
        state = _verification_processes[report['run_id']]
        process = state['process']
        if report['cancel_requested'] or time.monotonic()-state['started'] > (900 if report['kind']=='delivery_cook' else 240):
            if process.poll() is None:
                process.terminate()
            state['terminated'] = True
        if process.poll() is None:
            return
        try:
            source = status(report['delivery_run_id'])
            result = (delivery.inspect_cook(source,_runs()/report['run_id'],process.returncode) if report['kind']=='delivery_cook'
                      else discovery.read_json(_runs()/report['run_id']/'verification.json'))
            delivery.verify_files(source)
            passed = process.returncode==0 and result['passed'] and not state.get('terminated')
            report.update(verification=result, status='passed' if passed else 'cancelled' if report['cancel_requested'] else 'failed')
            if passed:
                if report['kind']=='delivery_cook':source.update(windows_cook='passed',cook_run_id=report['run_id'])
                else:source.update(fresh_project_verification='passed', verification_run_id=report['run_id'])
                _save(source)
        except Exception as error:
            report.update(status='cancelled' if report['cancel_requested'] else 'failed', error=str(error))
        report['assets'][0]['status'] = report['status']
        report['finished_at'] = time.time()
        _save(report)
        _verification_processes.pop(report['run_id'], None)
        _active = None
        if _tick is not None:
            _ue().unregister_slate_post_tick_callback(_tick)
            _tick = None
        return
    if report.get('kind') in ('preview_export','individual_previews'):
        from . import previews,media
        before=json.dumps(report['assets'],sort_keys=True)
        try:
            runner=media.advance if report['kind']=='individual_previews' else previews.advance
            done = runner(report, _preview_states[report['run_id']])
        except Exception as error:
            from . import render_quality
            render_quality.restore()
            report.update(error=str(error), traceback=traceback.format_exc())
            for row in report['assets']:
                if row['status'] in ('pending', 'running'):
                    row.update(status='failed', error=str(error))
            done = True
            _ue().log_error(report['traceback'])
        if done:
            report['status'] = ('failed' if any(a['status'] == 'failed' for a in report['assets']) else
                                'cancelled' if report['cancel_requested'] else 'passed')
            report['finished_at'] = time.time()
            if report['kind']=='individual_previews':
                changed=[p for p,sha in report['manifest']['source_hashes'].items()
                         if not Path(p).is_file() or discovery.digest(p)!=sha]
                report['source_files_unchanged']=not changed
                if changed:report.update(status='failed',error='Sources changed during media export')
                if report.get('original_package_hashes'):
                    report['original_packages_unchanged']=all(Path(p).is_file() and discovery.digest(p)==sha for p,sha in report['original_package_hashes'].items())
                    if not report['original_packages_unchanged']:report.update(status='failed',error='Original Unreal packages changed during LOD review')
                from . import review,auto_lod
                try:
                    auto_lod.restore(_preview_states[report['run_id']])
                    report['review_page']=(auto_lod.write_review(report) if report.get('automatic_lod_review') else review.write(report))
                except Exception as error:report.update(status='failed',error='Review export failed: '+str(error))
            _preview_states.pop(report['run_id'], None)
            _active = None
            if _tick is not None:
                _ue().unregister_slate_post_tick_callback(_tick)
                _tick = None
        if done or before!=json.dumps(report['assets'],sort_keys=True):
            _save(report)
        return
    pending = next((i for i, a in enumerate(report['assets']) if a['status'] == 'pending'), None)
    if report['cancel_requested'] or pending is None:
        if report['cancel_requested']:
            for asset in report['assets']:
                if asset['status'] == 'pending':
                    asset['status'] = 'cancelled'
            report['status'] = 'cancelled'
        else:
            report['status'] = 'failed' if any(a['status'] == 'failed' for a in report['assets']) else 'passed'
        if report.get('kind') in ('import', 'settings_update') and not report['cancel_requested']:
            # Shared master/helper packages can change later in a batch. Refresh
            # receipts at completion and reread every completed asset.
            from . import incremental
            for index, row in enumerate(report['assets']):
                if row['status'] in ('passed', 'skipped'):
                    try:
                        incremental.publish(report['manifest'], report['manifest']['assets'][index],
                                            report['kind'], report['engine_version'])
                    except Exception as error:
                        row.update(status='failed', error=f'Final receipt/read-back failed: {error}')
            if any(row['status'] == 'failed' for row in report['assets']):
                report['status'] = 'failed'
            if report.get('excluded_sources'):
                report['status'] = 'failed'
            report['partial'] = report['status'] != 'passed'
            report['quality_passed'] = all(row.get('strict_passed', row.get('passed',False)) for row in report['assets'])
            report['warning_count'] = sum(len(row.get('warnings',[])) for row in report['assets'])
        report['finished_at'] = time.time()
        if report.get('kind') == 'import_diagnostics':
            from . import diagnostics
            diagnostics.finish_report(report)
        _save(report)
        _active = None
        if _tick is not None:
            _ue().unregister_slate_post_tick_callback(_tick)
            _tick = None
        return
    item = report['assets'][pending]
    item['status'] = 'running'
    _save(report)
    try:
        if report.get('kind') == 'import_diagnostics':
            from . import diagnostics
            item.update(diagnostics.run_case(report['manifest'], item, report['run_id'],
                                              _runs() / report['run_id'] / 'profiles'))
        else:
            from . import runtime, incremental
            asset = report['manifest']['assets'][pending]
            submanifest = dict(report['manifest'], assets=[asset])
            runtime.assert_targets_clean(submanifest)
            incremental.sources_unchanged(report['manifest'], asset)
            hit, reason, inspected = incremental.check(report['manifest'], asset, report['kind'], report['engine_version']) \
                if report['manifest']['profile'].get('incremental', True) or report.get('resumed_from') else (False, 'disabled', None)
            if hit:
                item.update(inspected, status='skipped', action_reason=reason)
                _save(report)
                return
            runtime.backup(submanifest, _runs() / report['run_id'] / 'backup')
            item.update(runtime.process_asset(report['manifest'], pending, report['run_id'],
                                              settings_only=report.get('kind') == 'settings_update'))
            item['action_reason'] = reason
        item['status'] = 'passed' if item['passed'] else 'failed'
        if item['status'] == 'passed' and report.get('kind') in ('import', 'settings_update'):
            from . import incremental
            receipt = incremental.publish(report['manifest'], report['manifest']['assets'][pending],
                                          report['kind'], report['engine_version'])
            item['input_fingerprint'] = receipt['input_fingerprint']
        if not item['passed']:
            item['error'] = item.get('validation_summary', 'Read-back values disagree with the profile or MeshInfo; inspect checks')
    except Exception as error:
        item.update(status='failed', error=str(error), traceback=traceback.format_exc())
        _ue().log_error(item['traceback'])
    _save(report)


def run_blocking(profile_path):
    """Commandlet-only runner; the interactive UI/MCP use start and status."""
    if '-run=pythonscript' not in _ue().SystemLibrary.get_command_line().lower():
        raise RuntimeError('Use start() in an interactive editor')
    run_id = start(profile_path)
    while _active:
        _advance()
    return status(run_id)


def start_settings(profile_path):
    """Update materials, textures and mesh settings without reimporting geometry."""
    return start(profile_path, settings_only=True)


def create_review_candidate(import_run_id):
    """Persist a complete-catalog review profile and per-model issues; never edits Content."""
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import candidate, incremental, runtime
    source = status(import_run_id)
    if source.get('kind') not in ('import', 'settings_update') or source['status'] not in ('passed', 'failed'):
        raise ValueError('A completed import/settings run is required')
    if source.get('project_dir') != str(Path(_ue().Paths.project_dir()).resolve()):
        raise ValueError('Import belongs to another project')
    if source.get('plugin_version') != __version__ or source.get('engine_version') != readiness()['engine_version']:
        raise ValueError('Plugin/engine changed; rerun the import before selecting a candidate')
    manifest = source['manifest']
    runtime.assert_editor_idle()
    runtime.assert_targets_clean(manifest)
    accepted, issues, checks = candidate.select(source,
        lambda asset: incremental.sources_unchanged(manifest, asset),
        lambda asset: runtime.inspect(manifest, asset))
    config = candidate.profile(manifest['profile'], accepted)
    run_id = uuid.uuid4().hex
    folder = _runs()/run_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder/'candidate.profile.json'
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        current = discovery.scan(path)
        keys = ('id','mesh_path','lods','textures','effective_settings','source_kind')
        previous = [{k:a.get(k) for k in keys} for a in manifest['assets'] if a['id'] in accepted]
        if previous != [{k:a.get(k) for k in keys} for a in current['assets']]:
            raise RuntimeError('MeshInfo source mapping changed; reimport before selecting a candidate')
        if any(manifest['source_hashes'].get(path) != sha for path,sha in current['source_hashes'].items()):
            raise RuntimeError('Source files changed during candidate selection; reimport before proceeding')
    except Exception:
        path.unlink(missing_ok=True)
        raise
    blocked = [a['id'] for a in checks if not a.get('passed')]
    report = {'schema_version':1, 'run_id':run_id, 'kind':'review_candidate', 'status':'failed' if blocked else 'passed',
              'plugin_version':__version__, 'engine_version':readiness()['engine_version'],
              'started_at':time.time(), 'finished_at':time.time(), 'import_run_id':import_run_id,
              'profile_path':str(path), 'accepted_ids':accepted, 'excluded_assets':[], 'issues':issues,
              'blocking_ids':blocked, 'partial':bool(blocked), 'assets':checks,
              'quality_passed':all(a.get('strict_passed', a['passed']) for a in checks),
              'publication_ready':False, 'visual_review':'pending'}
    for row in report['assets']: row['status'] = 'passed' if row['passed'] else 'failed'
    _jobs[run_id] = report
    _save(report)
    return report


def validate(profile_path):
    from . import runtime
    manifest = discovery.scan(profile_path)
    results = []
    for asset in manifest['assets']:
        try:
            results.append(runtime.inspect(manifest, asset))
        except Exception as error:
            results.append({'id': asset['id'], 'passed': False, 'error': str(error)})
    return {'passed': all(a['passed'] for a in results) and not manifest.get('excluded_sources'),
            'assets': results, 'excluded_sources': manifest.get('excluded_sources', []), 'visual_review': 'pending'}


def create_review_bundle(media_run_ids):
    """Copy complete-model media into one offline LOD/Nanite comparison board."""
    if _active: raise RuntimeError(f'Job already running: {_active}')
    from . import review_bundle
    ids=[x.strip() for x in media_run_ids.split(',') if x.strip()]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate media Run IDs')
    run_id=uuid.uuid4().hex
    folder=_runs()/run_id
    result=review_bundle.build([status(run) for run in ids],folder/'Review')
    report=dict(result,schema_version=1,run_id=run_id,kind='review_bundle',status='passed',
                plugin_version=__version__,started_at=time.time(),finished_at=time.time(),assets=[],media_run_ids=ids)
    _jobs[run_id]=report;_save(report)
    return report


def analyze_sources(profile_path):
    """Read FBX/GLB evidence and save a report without importing any asset."""
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import diagnostics
    manifest = discovery.scan(profile_path)
    source = diagnostics.source_report(manifest)
    report = {'schema_version': 1, 'run_id': uuid.uuid4().hex, 'kind': 'source_diagnostics',
              'status': 'passed', 'plugin_version': __version__, 'manifest': manifest,
              'source_analysis': source, 'assets': source['assets'], 'finished_at': time.time()}
    diagnostics.finish_report(report)
    _jobs[report['run_id']] = report
    _save(report)
    return report


def start_diagnostics(profile_path):
    """Queue per-model FBX/GLB on/off probes only under an isolated diagnostic root."""
    global _active, _tick
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import diagnostics, runtime
    runtime.assert_editor_idle()
    manifest = discovery.scan(profile_path)
    if manifest['profile'].get('nanite_enabled',False):
        raise ValueError('Remove Degenerates LOD comparison requires Nanite OFF; source analysis supports Nanite sources')
    source = diagnostics.source_report(manifest)
    cases = diagnostics.cases(source)
    if not cases:
        raise ValueError('No source formats supported for import diagnostics; run source analysis for details')
    run_id = uuid.uuid4().hex
    report = {'schema_version': 1, 'run_id': run_id, 'kind': 'import_diagnostics', 'status': 'running',
              'plugin_version': __version__, 'engine_version': readiness()['engine_version'],
              'manifest': manifest, 'source_analysis': source, 'assets': cases,
              'cancel_requested': False, 'started_at': time.time(), 'publication_ready': False}
    _jobs[run_id] = report
    _active = run_id
    _save(report)
    if '-run=' not in _ue().SystemLibrary.get_command_line().lower():
        _tick = _ue().register_slate_post_tick_callback(_advance)
    return run_id


def create_overview(profile_path, lod_review=False):
    """Create/update the owned map only. Does not reimport meshes or publish files."""
    global _active
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import overview
    manifest = discovery.scan(profile_path)
    # Fail before recording a mutation job if inputs/settings cannot be used.
    overview.prepare(manifest, lod_review)
    overview._safe_to_switch()
    run_id = uuid.uuid4().hex
    report = {'schema_version': 1, 'run_id': run_id, 'kind': 'lod_review' if lod_review else 'overview',
              'status': 'running', 'plugin_version': __version__, 'engine_version': readiness()['engine_version'],
              'manifest': manifest, 'started_at': time.time(), 'assets': [], 'visual_review': 'pending'}
    _jobs[run_id] = report
    _active = run_id
    _save(report)
    try:
        result = overview.build(manifest, _runs() / run_id / 'backup', lod_review)
        report.update(result)
        report['status'] = 'passed' if result['passed'] else 'failed'
    except Exception as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
        _ue().log_error(report['traceback'])
    finally:
        report['finished_at'] = time.time()
        _save(report)
        _active = None
    return report


def open_overview(profile_path, lod_review=False):
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import overview
    return overview.open_map(discovery.scan(profile_path), lod_review)


def validate_overview(profile_path, lod_review=False):
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import overview
    return overview.validate_current(discovery.scan(profile_path), lod_review)


def start_previews(profile_path):
    """Export saved overview/LOD maps asynchronously, into a unique run folder."""
    global _active, _tick
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import previews, overview, runtime
    runtime.assert_editor_idle()
    command = _ue().SystemLibrary.get_command_line().lower()
    if '-run=' in command or '-nullrhi' in command:
        raise RuntimeError('Preview export needs an interactive editor with RHI, not a commandlet/NullRHI')
    manifest = discovery.scan(profile_path)
    config = previews.settings(manifest['profile'])
    overview._safe_to_switch()
    modes = [False, True] if config['mode'] == 'both' else [config['mode'] == 'lod_review']
    for lod in modes:
        overview.prepare(manifest, lod)
        path = overview.settings(manifest['profile'], lod)['map_path']
        world = _ue().load_asset(path)
        if not world or not runtime.owned(world, manifest['profile']['pack_id']):
            raise RuntimeError(f'Create the owned scene before exporting previews: {path}')
        del world
    run_id = uuid.uuid4().hex
    folder = (Path(config['output_directory']) if config['output_directory'] else
              _runs().parent / 'Previews') / run_id
    folder.mkdir(parents=True, exist_ok=False)
    rows = [{'id': 'lod_review' if lod else 'overview', 'lod_review': lod, 'status': 'pending',
             'map_path': overview.settings(manifest['profile'], lod)['map_path'],
             'output_path': str(folder / (('lod_review' if lod else 'overview')+'.png'))} for lod in modes]
    from . import render_views
    rows=render_views.expand(rows,config['view_modes'])
    report = {'schema_version': 1, 'run_id': run_id, 'kind': 'preview_export', 'status': 'running',
              'plugin_version': __version__, 'engine_version': readiness()['engine_version'],
              'manifest': manifest, 'preview_settings': config, 'assets': rows,
              'started_at': time.time(), 'cancel_requested': False, 'output_directory': str(folder),
              'publication_ready': False, 'visual_review': 'pending'}
    _jobs[run_id] = report
    _preview_states[run_id] = {}
    _active = run_id
    _save(report)
    _tick = _ue().register_slate_post_tick_callback(_advance)
    return run_id


def start_media(profile_path, automatic_lod=False):
    """Generate per-model bounds-framed stills in a new isolated studio."""
    global _active,_tick
    if _active:raise RuntimeError(f'Job already running: {_active}')
    from . import media,previews,runtime,overview
    runtime.assert_editor_idle();overview._safe_to_switch()
    command=_ue().SystemLibrary.get_command_line().lower()
    if '-run=' in command or '-nullrhi' in command:raise RuntimeError('Individual media requires an interactive RHI editor')
    manifest=discovery.scan(profile_path)
    config=media.settings(manifest['profile']);capture=previews.settings(manifest['profile'])
    checks=[runtime.inspect(manifest,asset) for asset in manifest['assets']]
    if automatic_lod:
        if capture['view_modes']!=['lit']:
            raise ValueError('Automatic LOD telemetry requires only Lit; use ordinary renders for wireframe/collision')
        if manifest['profile'].get('nanite_enabled', False):
            raise ValueError('Automatic conventional LOD review requires Nanite OFF')
        from . import auto_lod
        runtime.assert_targets_clean(manifest)
        if not all(a['passed'] for a in checks):
            raise RuntimeError('Automatic LOD review requires valid source assets: '+', '.join(a['id'] for a in checks if not a['passed']))
        if _ue().SystemLibrary.get_console_variable_int_value('r.ForceLOD')!=-1:
            raise RuntimeError('Disable global r.ForceLOD before automatic LOD review')
        scale=_ue().SystemLibrary.get_console_variable_float_value('r.StaticMeshLODDistanceScale')
        if abs(scale-1)>1e-5:raise RuntimeError('Automatic LOD review requires r.StaticMeshLODDistanceScale=1')
        config['fov']=90;capture.update(width=1280,height=720)
        for asset,check in zip(manifest['assets'],checks):
            check['sphere_radius']=float(_ue().load_asset(asset['mesh_path']).get_bounds().sphere_radius)
    if not config['include_invalid'] and not all(a['passed'] for a in checks):
        raise RuntimeError('Invalid meshes require media.include_invalid=true for diagnostic images')
    run_id=uuid.uuid4().hex
    folder=(Path(capture['output_directory']) if capture['output_directory'] else _runs().parent/'Media')/run_id
    folder.mkdir(parents=True,exist_ok=False)
    studio='/Game/AssetPackPipeline_Previews/'+run_id+'/Studio'
    rows=(auto_lod.rows if automatic_lod else media.frame_rows)(manifest['assets'],checks,config,folder,studio)
    report={'schema_version':1,'run_id':run_id,'kind':'individual_previews','status':'running',
            'plugin_version':__version__,'manifest':manifest,'media_settings':config,'preview_settings':capture,
            'source_asset_checks':checks,'assets':rows,'cancel_requested':False,'started_at':time.time(),
            'source_assets_valid':all(a.get('strict_passed',a['passed']) for a in checks),
            'diagnostic':not all(a.get('strict_passed',a['passed']) for a in checks),
            'publication_ready':False,'visual_review':'pending','output_directory':str(folder),
            'studio_backup':str(_runs()/run_id/'studio_backup')}
    report['automatic_lod_review']=automatic_lod
    if automatic_lod:
        from . import incremental
        report['evidence_method']='original_mesh_draw_command_csv'
        report['original_package_hashes']=incremental.output_hashes(_ue().Paths.project_content_dir(),[p for a in manifest['assets'] for p in runtime._paths(manifest,a)])
    _jobs[run_id]=report;_active=run_id;_preview_states[run_id]={};_save(report)
    _tick=_ue().register_slate_post_tick_callback(_advance)
    return run_id


def start_flythrough(profile_path):
    """Create an isolated saved sequence and render every frame with a private MRQ queue."""
    global _active,_tick
    if _active:raise RuntimeError(f'Job already running: {_active}')
    from . import flythrough,runtime,overview,incremental
    u=_ue();runtime.assert_editor_idle();overview._safe_to_switch()
    if not hasattr(u,'MoviePipelineQueueSubsystem') or not hasattr(u,'MovieSceneSequenceExtensions'):
        raise RuntimeError('Enable MovieRenderPipeline and SequencerScripting, then restart Unreal')
    if '-nullrhi' in u.SystemLibrary.get_command_line().lower():raise RuntimeError('Flythrough requires an RHI editor')
    if u.get_editor_subsystem(u.MoviePipelineQueueSubsystem).is_rendering():raise RuntimeError('Movie Render Queue is busy')
    if u.SystemLibrary.get_console_variable_int_value('r.ForceLOD')!=-1:raise RuntimeError('Disable global r.ForceLOD before flythrough')
    manifest=discovery.scan(profile_path);runtime.assert_targets_clean(manifest)
    checks=[runtime.inspect(manifest,a) for a in manifest['assets']]
    if not all(c['passed'] for c in checks):raise RuntimeError('Resolve operational preparation errors before flythrough')
    config=flythrough.settings(manifest['profile']);run_id=uuid.uuid4().hex
    folder=_runs().parent/'Flythrough'/run_id;folder.mkdir(parents=True,exist_ok=False)
    hashes=incremental.output_hashes(u.Paths.project_content_dir(),[p for a in manifest['assets'] for p in runtime._paths(manifest,a)])
    built=flythrough.build(manifest,run_id,config,_runs()/run_id/'scene_backup')
    report=dict(built,schema_version=1,run_id=run_id,kind='flythrough',status='running',plugin_version=__version__,
                manifest=manifest,flythrough_settings=config,started_at=time.time(),cancel_requested=False,
                assets=[{'id':'Continuous flythrough','status':'running'}],output_directory=str(folder),
                original_package_hashes=hashes,publication_ready=False,visual_review='pending')
    _jobs[run_id]=report;state={};_flythrough_states[run_id]=state;_active=run_id;_save(report)
    try:
        flythrough.launch(report,state)
        _tick=u.register_slate_post_tick_callback(_advance)
    except Exception as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc(),finished_at=time.time())
        report['assets'][0]['status']='failed';_active=None;_flythrough_states.pop(run_id,None);_save(report)
    return run_id


def open_flythrough(run_id):
    """Open the saved flythrough map and Level Sequence in this editor."""
    if _active:raise RuntimeError(f'Job already running: {_active}')
    from . import overview,runtime
    runtime.assert_editor_idle();overview._safe_to_switch()
    report=status(run_id)
    if report.get('kind')!='flythrough':raise ValueError('Select a flythrough Run ID')
    u=_ue()
    if not u.EditorAssetLibrary.does_asset_exist(report['map_path']) or not u.EditorAssetLibrary.does_asset_exist(report['sequence_path']):
        raise ValueError('Flythrough assets are not present in this project')
    if not u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(report['map_path']):raise RuntimeError('Cannot open flythrough map')
    sequence=u.load_asset(report['sequence_path'])
    if not u.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence):raise RuntimeError('Cannot open saved Level Sequence')
    return {'map_path':report['map_path'],'sequence_path':report['sequence_path'],'opened':True}


def plan_cleanup(profile_path, staging_run_id=''):
    from . import cleanup
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    return cleanup.plan(discovery.scan(profile_path), staging_run_id)


def plan_delivery(profile_path):
    from . import delivery
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    return delivery.plan(discovery.scan(profile_path))


def _content_operation(profile_path, kind, staging_run_id='', prepared_manifest=None):
    global _active
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import cleanup, delivery
    manifest = prepared_manifest if prepared_manifest is not None else discovery.scan(profile_path)
    cleanup.assert_clean()
    run_id = uuid.uuid4().hex
    report = {'schema_version':1, 'run_id':run_id, 'kind':kind, 'status':'running',
              'plugin_version':__version__, 'engine_version':readiness()['engine_version'], 'manifest':manifest,
              'assets':[], 'started_at':time.time(), 'publication_ready':False, 'visual_review':'pending'}
    _jobs[run_id] = report
    _active = run_id
    _save(report)
    try:
        if kind=='staging_cleanup':
            result = cleanup.execute(manifest, _runs()/run_id/'backup', staging_run_id)
        else:
            result = delivery.create(manifest, run_id)
        report.update(result)
        report['status'] = 'passed' if result['passed'] else 'failed'
        if kind=='staging_cleanup' and result['passed'] and result['retained_count']:
            report['status'] = 'partial'
    except Exception as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
        _ue().log_error(report['traceback'])
    finally:
        report['finished_at'] = time.time()
        _save(report)
        _active = None
    return report


def cleanup_staging(profile_path, staging_run_id=''):
    return _content_operation(profile_path, 'staging_cleanup', staging_run_id)


def create_delivery(profile_path):
    return _content_operation(profile_path, 'delivery')


def create_combined_delivery(profile_paths):
    """One clean project with both mesh representations and shared resources."""
    from . import delivery
    manifest = delivery.combine([discovery.scan(p) for p in profile_paths])
    return _content_operation(profile_paths[0], 'delivery', prepared_manifest=manifest)


def start_delivery_verification(delivery_run_id):
    global _active, _tick
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import delivery
    source = status(delivery_run_id)
    if source.get('kind')!='delivery' or source['status']!='passed':
        raise ValueError('A completed clean delivery project is required')
    run_id = uuid.uuid4().hex
    folder = _runs()/run_id
    process = delivery.launch_verifier(source, folder)
    report = {'schema_version':1, 'run_id':run_id, 'kind':'delivery_verification', 'status':'running',
              'delivery_run_id':delivery_run_id, 'plugin_version':__version__,
              'started_at':time.time(), 'cancel_requested':False, 'publication_ready':False,
              'assets':[{'id':'Clean project', 'status':'running'}]}
    _jobs[run_id] = report
    _verification_processes[run_id] = {'process':process, 'started':time.monotonic()}
    _active = run_id
    _save(report)
    _tick = _ue().register_slate_post_tick_callback(_advance)
    return run_id


def package_delivery(delivery_run_id):
    if _active:
        raise RuntimeError(f'Job already running: {_active}')
    from . import delivery
    report = status(delivery_run_id)
    if report.get('kind')!='delivery' or report['status']!='passed':
        raise ValueError('Completed delivery required')
    result = delivery.package(report)
    report.update(result)
    _save(report)
    return result


def start_cook(delivery_run_id):
    global _active,_tick
    if _active:raise RuntimeError(f'Job already running: {_active}')
    from . import delivery
    source=status(delivery_run_id)
    if source.get('kind')!='delivery' or source.get('fresh_project_verification')!='passed':
        raise ValueError('A verified clean delivery is required before cooking')
    run_id=uuid.uuid4().hex
    process=delivery.launch_cook(source,_runs()/run_id)
    report={'schema_version':1,'run_id':run_id,'kind':'delivery_cook','status':'running',
            'delivery_run_id':delivery_run_id,'plugin_version':__version__,'started_at':time.time(),
            'cancel_requested':False,'publication_ready':False,'assets':[{'id':'Windows cook','status':'running'}]}
    _jobs[run_id]=report;_active=run_id
    _verification_processes[run_id]={'process':process,'started':time.monotonic()};_save(report)
    _tick=_ue().register_slate_post_tick_callback(_advance)
    return run_id
