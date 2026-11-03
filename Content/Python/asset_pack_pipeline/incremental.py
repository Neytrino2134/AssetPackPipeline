"""Conservative per-asset import receipts. Hashes never substitute for UE read-back."""
import hashlib
import json
from pathlib import Path
from . import __version__, discovery, profiles

RECEIPT_SCHEMA = 1


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def fingerprint(manifest, asset, operation, engine_version):
    profile = profiles.effective(manifest['profile'], asset['id'])
    files = {lod['file'] for lod in asset['lods']} | set(asset['textures'].values())
    settings = {key: profile[key] for key in sorted(profiles.OVERRIDE_KEYS)}
    if profile['collision']=='convex':settings['convex_collision']=profiles.convex_settings(profile)
    # UI profiles serialize 1.0 where a hand-authored profile may use 1.
    # Numeric equivalents must identify the same effective Unreal settings.
    for key in ('roughness', 'metallic', 'normal_strength', 'uv_scale'):
        settings[key] = float(settings[key])
    settings['lod_screen_sizes'] = [float(x) for x in settings['lod_screen_sizes']]
    spec = {'schema': RECEIPT_SCHEMA, 'plugin_version': __version__, 'engine_version': engine_version,
            'operation': operation, 'nanite_enabled':profile.get('nanite_enabled',False),
            'validation_policy':profile.get('validation_policy','warn'),
            'normal_map_convention':profile.get('normal_map_convention','OpenGL'),
            'pack_id': profile['pack_id'], 'destination_root': profile['destination_root'],
            'source_format': profile['source_format'], 'asset_id': asset['id'], 'mesh_path': asset['mesh_path'],
            'lods': asset['lods'], 'textures': asset['textures'],
            'settings': settings,
            'source_hashes': {path: manifest['source_hashes'][path] for path in sorted(files)}}
    return hashlib.sha256(_canonical(spec)).hexdigest()


def sources_unchanged(manifest, asset):
    files = {lod['file'] for lod in asset['lods']} | set(asset['textures'].values())
    changed = [p for p in files if not Path(p).is_file() or discovery.digest(p) != manifest['source_hashes'][p]]
    if changed:
        raise RuntimeError(f"Source changed after plan: {', '.join(sorted(changed))}")


def receipt_path(saved, manifest, asset, operation):
    key = {'root': manifest['profile']['destination_root'], 'asset': asset['id'], 'operation': operation}
    return Path(saved)/'AssetPackPipeline'/'Cache'/(hashlib.sha256(_canonical(key)).hexdigest()+'.json')


def package_files(content, package_paths):
    content = Path(content).resolve()
    result = []
    for path in sorted(set(package_paths)):
        if not path.startswith('/Game/'):
            raise ValueError(f'Invalid package path: {path}')
        stem = content/path.removeprefix('/Game/')
        main = stem.with_suffix('.uasset')
        if not main.is_file():
            raise FileNotFoundError(f'Expected saved package missing: {main}')
        result.extend([p for suffix in ('.uasset', '.uexp', '.ubulk')
                       if (p := stem.with_suffix(suffix)).is_file()])
    return result


def output_hashes(content, package_paths):
    return {str(path): discovery.digest(path) for path in package_files(content, package_paths)}


def _paths(manifest, asset):
    from . import runtime
    return runtime._paths(manifest, asset)


def build_receipt(manifest, asset, operation, engine_version):
    import unreal as u
    sources_unchanged(manifest, asset)
    hashes = output_hashes(u.Paths.project_content_dir(), _paths(manifest, asset))
    return {'schema_version': RECEIPT_SCHEMA, 'input_fingerprint': fingerprint(manifest, asset, operation, engine_version),
            'output_hashes': hashes, 'asset_id': asset['id'], 'operation': operation,
            'project_dir': str(Path(u.Paths.project_dir()).resolve())}


def publish(manifest, asset, operation, engine_version):
    import unreal as u
    from . import runtime
    check = runtime.inspect(manifest, asset)
    if not check['passed']:
        raise RuntimeError(f"Cannot cache failed asset {asset['id']}: {check.get('validation_summary', '')}")
    receipt = build_receipt(manifest, asset, operation, engine_version)
    path = receipt_path(u.Paths.project_saved_dir(), manifest, asset, operation)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    temp.replace(path)
    return receipt


def check(manifest, asset, operation, engine_version):
    """Return (hit, reason, independent inspection). Any uncertainty is a miss."""
    import unreal as u
    from . import runtime
    path = receipt_path(u.Paths.project_saved_dir(), manifest, asset, operation)
    if not path.is_file():
        return False, 'no_receipt', None
    try:
        receipt = discovery.read_json(path)
        if receipt.get('schema_version') != RECEIPT_SCHEMA:
            return False, 'receipt_schema_changed', None
        if receipt.get('project_dir') != str(Path(u.Paths.project_dir()).resolve()):
            return False, 'project_changed', None
        if receipt.get('input_fingerprint') != fingerprint(manifest, asset, operation, engine_version):
            return False, 'inputs_changed', None
        sources_unchanged(manifest, asset)
        current = output_hashes(u.Paths.project_content_dir(), _paths(manifest, asset))
        if current != receipt.get('output_hashes'):
            return False, 'saved_assets_changed', None
        inspection = runtime.inspect(manifest, asset)
        if not inspection['passed']:
            return False, 'readback_failed', inspection
        return True, 'verified_receipt', inspection
    except Exception as error:
        return False, f'could_not_verify: {error}', None
