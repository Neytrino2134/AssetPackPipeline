"""Owned staging cleanup, with conservative dependency guards and disk backups."""
import re
import shutil
from pathlib import Path

ROOT = '/Game/AssetPackPipeline_Staging'
RUN_TAG = 'AssetPackPipeline.StagingRun'


def dependency_options():
    import unreal as u
    return u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True, include_searchable_names=True,
        include_soft_management_references=True, include_hard_management_references=True)


def assert_clean():
    import unreal as u
    from . import runtime
    runtime.assert_editor_idle()
    dirty = list(u.EditorLoadingAndSavingUtils.get_dirty_map_packages()) + list(u.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError('Save or revert all dirty maps/assets before cleanup or delivery: '+', '.join(p.get_name() for p in dirty))


def mark_staging(folder, pack, run_id):
    import unreal as u
    from . import runtime
    if not folder.startswith(ROOT+'/') or not re.fullmatch('[A-Za-z0-9_]{1,128}', run_id):
        raise ValueError('Invalid staging folder/run')
    for path in u.EditorAssetLibrary.list_assets(folder, recursive=True, include_folder=False):
        obj = u.load_asset(path)
        if obj:
            if not runtime.owned(obj, pack):
                runtime.mark(obj, pack)
            if str(u.EditorAssetLibrary.get_metadata_tag(obj, RUN_TAG)) != run_id:
                u.EditorAssetLibrary.set_metadata_tag(obj, RUN_TAG, run_id)
            if not u.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=True):
                raise RuntimeError(f'Cannot save staging asset: {path}')


def retain_referenced(candidates, referencers):
    """Largest removable subset: retain dependencies of any retained referencer."""
    active = set(candidates)
    while True:
        blocked = {p for p in active if set(referencers.get(p, [])) - active - {p}}
        if not blocked:
            return active
        active -= blocked


def backup_packages(packages, destination):
    import unreal as u
    content = Path(u.Paths.project_content_dir()).resolve()
    for package in packages:
        if not package.startswith('/Game/'):
            raise ValueError('Only /Game packages can be backed up')
        for suffix in ('.uasset', '.uexp', '.ubulk', '.umap'):
            original = (content/(package.removeprefix('/Game/')+suffix)).resolve()
            if not original.is_relative_to(content):
                raise ValueError('Package path escapes Content')
            if original.is_file():
                target = Path(destination)/original.relative_to(content)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(original, target)


def plan(manifest, run_id='', imported=False, folder_scope=False):
    import unreal as u
    from . import runtime
    if run_id and not re.fullmatch('[A-Za-z0-9_]{1,128}', run_id):
        raise ValueError('Invalid staging run ID')
    assert_clean()
    root = manifest['profile']['destination_root'].rstrip('/') if imported else ROOT
    if imported and not re.fullmatch(r'/Game/[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)*', root):
        raise ValueError('Cleanup requires a specific pack folder under /Game')
    if folder_scope and (not imported or root.split('/')[2].casefold() in ('presentation', 'assetpackpipeline')):
        raise ValueError('Protected project folder cannot be cleaned')
    registry = u.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(synchronous_search=True)
    # Referencers may have been saved in this same editor tick outside staging.
    # Scan their packages too: scanning only ROOT can leave dependency edges stale.
    registry.scan_paths_synchronous(['/Game'], force_rescan=True)
    rows, refs, candidates = [], {}, set()
    current = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world().get_path_name().split('.')[0] if imported else ''
    for path in u.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False):
        obj = u.load_asset(path)
        package = str(path).split('.')[0]
        tag = str(u.EditorAssetLibrary.get_metadata_tag(obj, RUN_TAG)) if obj else ''
        if run_id and tag != run_id:
            continue
        own = bool(obj and runtime.owned(obj, manifest['profile']['pack_id']) and (imported or tag))
        supported = isinstance(obj, (u.StaticMesh, u.Material, u.MaterialInstanceConstant, u.Texture2D)) or (imported and isinstance(obj, u.World) and package != current)
        if (own or folder_scope) and supported:
            candidates.add(package)
        disk_refs = {str(p) for p in registry.get_referencers(package, dependency_options())}
        confirmed = {str(p) for p in u.EditorAssetLibrary.find_package_referencers_for_asset(str(path), load_assets_to_confirm=True)}
        refs[package] = sorted(disk_refs | confirmed)
        rows.append({'id':package, 'path':str(path), 'owned':own, 'supported':supported,
                     'staging_run':tag, 'referencers':refs[package]})
    active = retain_referenced(candidates, refs)
    for row in rows:
        row['can_delete'] = row['id'] in active
        row['reason'] = (('selected_folder_and_unreferenced' if folder_scope else 'owned_and_unreferenced') if row['can_delete'] else
                         'external_or_retained_referencer' if row['id'] in candidates else 'unowned_or_unsupported')
    return {'assets':rows, 'delete_packages':sorted(active), 'delete_count':len(active),
            'retained_count':len(rows)-len(active), 'publication_ready':False}


def execute(manifest, backup_folder, run_id='', imported=False, expected=None, folder_scope=False):
    import unreal as u
    proposal = plan(manifest, run_id, imported, folder_scope)
    packages = proposal['delete_packages']
    if expected is not None and sorted(expected) != packages:
        raise RuntimeError('Cleanup plan changed; inspect and confirm again')
    backup_packages(packages, backup_folder)
    # Refresh after backups immediately before Unreal's bulk deletion.
    fresh = plan(manifest, run_id, imported, folder_scope)
    if fresh['delete_packages'] != packages:
        raise RuntimeError('Dependencies changed during cleanup; inspect a fresh plan')
    objects = [u.load_asset(p) for p in packages]
    if objects and (any(o is None for o in objects) or not u.EditorAssetLibrary.delete_loaded_assets(objects)):
        raise RuntimeError('Unreal could not delete every staged asset; inspect backup and report')
    remaining = [p for p in packages if u.EditorAssetLibrary.does_asset_exist(p)]
    for row in proposal['assets']:
        row['status'] = 'deleted' if row['can_delete'] and row['id'] not in remaining else 'retained'
    proposal.update(passed=not remaining, deleted_count=len(packages)-len(remaining),
                    backup_folder=str(backup_folder), remaining_requested=remaining)
    return proposal
