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


def dirty_user_maps(u):
    saving = u.EditorLoadingAndSavingUtils
    dirty = list(saving.get_dirty_map_packages())
    studios = [package for package in dirty if re.fullmatch(
        r'/Game/AssetPackPipeline_Previews/[0-9a-f]{32}/Studio', package.get_name())]
    if studios:
        saving.save_packages(studios, True)
    return list(saving.get_dirty_map_packages())


def assert_clean():
    import unreal as u
    from . import runtime
    runtime.assert_editor_idle()
    dirty = dirty_user_maps(u) + list(u.EditorLoadingAndSavingUtils.get_dirty_content_packages())
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


PROTECTED_FOLDERS = ('presentation', 'assetpackpipeline')
PRESENTATION_MAP = '/Game/Presentation/L_Presentation'
PRESENTATION_TEMPLATE = '/Engine/Maps/Templates/Template_Default'


def presentation_map(root):
    """Existing L_Presentation outside the cleaned folder, or None."""
    import unreal as u
    found = []
    for path in u.EditorAssetLibrary.list_assets('/Game', recursive=True, include_folder=False):
        package = str(path).split('.')[0]
        if package.rsplit('/', 1)[-1] == 'L_Presentation' and not package.startswith(root+'/'):
            found.append(package)
    return PRESENTATION_MAP if PRESENTATION_MAP in found else (sorted(found)[0] if found else None)


def open_presentation(root):
    """Leave the cleaned folder: open L_Presentation, creating it from the Basic
    template (or empty) when the project has none. Returns (path, created)."""
    import unreal as u
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    path = presentation_map(root)
    if path:
        current = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world().get_path_name().split('.')[0]
        if current != path and not levels.load_level(path):
            raise RuntimeError(f'Не удалось открыть {path}')
        return path, False
    created = False
    if u.EditorAssetLibrary.does_asset_exist(PRESENTATION_TEMPLATE):
        created = bool(levels.new_level_from_template(PRESENTATION_MAP, PRESENTATION_TEMPLATE))
    if not created and not levels.new_level(PRESENTATION_MAP):
        raise RuntimeError(f'Не удалось создать {PRESENTATION_MAP}')
    if not levels.save_current_level():
        raise RuntimeError(f'Не удалось сохранить {PRESENTATION_MAP}')
    return PRESENTATION_MAP, True


def backup_folder_files(root, destination):
    """Copy every file under a /Game folder on disk, including files Unreal does not track."""
    import unreal as u
    content = Path(u.Paths.project_content_dir()).resolve()
    source = (content/root.removeprefix('/Game/')).resolve()
    if not source.is_relative_to(content) or source == content:
        raise ValueError('Folder path escapes Content')
    copied = 0
    if source.is_dir():
        for file in source.rglob('*'):
            if file.is_file():
                target = Path(destination)/file.relative_to(content)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(file, target)
                    copied += 1
    return source, copied


def plan(manifest, run_id='', imported=False, folder_scope=False, force=False):
    import unreal as u
    from . import runtime
    if run_id and not re.fullmatch('[A-Za-z0-9_]{1,128}', run_id):
        raise ValueError('Invalid staging run ID')
    assert_clean()
    root = manifest['profile']['destination_root'].rstrip('/') if imported else ROOT
    if imported and not re.fullmatch(r'/Game/[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)*', root):
        raise ValueError('Cleanup requires a specific pack folder under /Game')
    if (folder_scope or force) and (not imported or root.split('/')[2].casefold() in PROTECTED_FOLDERS):
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
    external = {}
    if force and imported:
        # Forced folder removal: everything under the root goes, including the current
        # map (L_Presentation is opened first) and assets other packages reference.
        packages = {row['id'] for row in rows}
        for row in rows:
            outside = [p for p in row['referencers'] if p not in packages and not p.startswith(root+'/')]
            if outside:
                external[row['id']] = outside
            if not row['can_delete']:
                row['reason'] = ('forced_current_map' if row['id'] == current else
                                 'forced_external_references' if outside else 'forced_folder_removal')
                row['can_delete'] = True
        active = packages
    existing = presentation_map(root) if force and imported else None
    return {'assets':rows, 'delete_packages':sorted(active), 'delete_count':len(active),
            'retained_count':len(rows)-len(active), 'publication_ready':False,
            'force':bool(force and imported), 'root':root, 'external_referencers':external,
            'presentation_map':(existing or PRESENTATION_MAP) if force and imported else None,
            'presentation_exists':bool(existing) if force and imported else None}


def execute_forced(manifest, backup_folder, expected=None, folder_scope=False):
    """Back up the whole folder on disk (and outside packages that reference it), open
    L_Presentation, force-delete every asset and remove the folder itself."""
    import unreal as u
    proposal = plan(manifest, imported=True, folder_scope=folder_scope, force=True)
    root = proposal['root']
    if expected is not None and sorted(expected) != proposal['delete_packages']:
        raise RuntimeError('Cleanup plan changed; inspect and confirm again')
    source, copied = backup_folder_files(root, backup_folder)
    outside = sorted({p for refs in proposal['external_referencers'].values() for p in refs if p.startswith('/Game/')})
    backup_packages(outside, Path(backup_folder)/'_external_referencers')
    map_path, created = open_presentation(root)
    u.EditorAssetLibrary.delete_directory(root)
    leftovers = [str(p) for p in source.rglob('*') if p.is_file()] if source.is_dir() else []
    if source.is_dir():
        # Files Unreal does not track (already in the backup) keep the folder alive.
        shutil.rmtree(source)
        u.EditorAssetLibrary.delete_directory(root)
    # Force delete nulls references in outside packages; save exactly what it dirtied
    # (assert_clean guaranteed nothing else was dirty before).
    saving = u.EditorLoadingAndSavingUtils
    dirtied = [p.get_name() for p in list(saving.get_dirty_map_packages())+list(saving.get_dirty_content_packages())]
    if dirtied:
        saving.save_dirty_packages(True, True)
    remaining = [p for p in proposal['delete_packages'] if u.EditorAssetLibrary.does_asset_exist(p)]
    folder_removed = not source.exists() and not u.EditorAssetLibrary.does_directory_exist(root)
    for row in proposal['assets']:
        row['status'] = 'retained' if row['id'] in remaining else 'deleted'
    proposal.update(passed=not remaining and folder_removed, deleted_count=len(proposal['delete_packages'])-len(remaining),
                    remaining_requested=remaining, folder_removed=folder_removed, backup_folder=str(backup_folder),
                    backup_files=copied, untracked_files_removed=leftovers, saved_after_delete=dirtied,
                    presentation_map=map_path, presentation_created=created)
    return proposal


def execute(manifest, backup_folder, run_id='', imported=False, expected=None, folder_scope=False, force=False):
    import unreal as u
    if force and imported:
        return execute_forced(manifest, backup_folder, expected, folder_scope)
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
