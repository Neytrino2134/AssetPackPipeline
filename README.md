# Asset Pack Pipeline 0.31.2

Imported pack cleanup removes the whole pack folder: it backs up every file, opens
L_Presentation (creating /Game/Presentation/L_Presentation from the Basic template
when missing), force-deletes all assets including the root folder and saves packages
whose references were cleared.

Custom UI opens centred without a white first frame. Updates, AI settings, Content
scan and cleanup plan share one dark window style with the MESHFLOW title bar,
a loading animation while data loads, and dark confirmations.

Smart Normal conversion (Quick Start → «1. Исходники», on by default): the importer
reads MeshInfo texture entries (`convention`, `preferred`, `unreal.flip_green_channel`)
and `_DirectX/_DX`, `_OpenGL/_GL` file suffixes. DirectX maps are imported as-is;
OpenGL or unlabeled (Blender) maps get Flip Green Channel. Older MeshInfo files,
including FBX/MeshInfo.json with folder-relative paths, are still read.
Existing packs are fixed with «Обновить материалы и настройки без импорта мешей».

Model IDs in MeshInfo may start with a digit (e.g. 52_Ruini_Skali_Pesok_01_01);
Unreal asset names keep their SM_/MI_/T_ prefixes.

The plugin window journal is saved to Saved/AssetPackPipeline/Logs/journal-<date>.log
(errors with full tracebacks). After an error, «Журнал в папке…» opens Explorer with
the file selected, ready to copy from another device.

Custom UI remembers its position, size, mode, tab, wizard step, Quick Start choices
and unsaved form edits between sessions; a Pin button keeps it above other windows.
A MESHFLOW button on the Level Editor toolbar opens it. Quick Start chooses Wireframe
and Player Collision images per target (overview, MID, LOW); see the 0.30.0 notes.

Quick Start now generates fitted Auto Convex simple collisions instead of one box.
Professional mode supports convex / box / none and configurable hull budgets.
Existing meshes can be updated without reimport. See [collision setup](Docs/ConvexCollision0290.md).

Still renders explicitly select Lit, regardless of the editor viewport mode.
Quick Start adds optional Wireframe, Visibility Collision and Player Collision
images in a second options column; suffixes distinguish the outputs.
The original viewport mode is restored after the job. See [render modes](Docs/RenderViews0280.md).

Custom UI uses the transparent cyan/purple MeshFlow logo in its title bar and
window icon. Agent release publication uploads and verifies both update assets.

Window and Slate tab titles display the plugin version. Custom UI pins its
actions, status and progress below scrolling content in all three modes.

Git-free updates: **Tools → Asset Pack Pipeline → Настройки и обновления…**,
or the update button in Custom UI / Slate. Public GitHub Releases, version and
engine BuildId checks, SHA256 validation, post-editor installation and backup.
See [update setup and release publishing](Docs/Updates0260.md).

Overview and individual stills share camera-side key lighting (Pitch 225 degrees,
Yaw 60 degrees in the default front view), rotating with individual view changes.

Overview scenes use a ground backdrop at least 2 km wide, extending beyond the
cameras. Older owned overview maps upgrade their floor on opening through the pipeline.

Final exports use `FinalProject/YYYY-MM-DD_HH-MM-SS/Pack_Project` and
`Pack_Renders`, with separate ZIPs and universal image filenames.
See [final output layout](Docs/FinalOutput0251.md).

Custom UI performance: background status snapshots keep startup and idle interaction
independent of Unreal response time. See [performance verification](Docs/CustomUIPerformance0241.md)
and [dual UI usage](Docs/CustomUI024.md). Restart Unreal after updating Python modules.

## Continuous camera flythrough (0.15)

In **Предметы**, configure duration, FPS, resolution, camera sweep/pitch/FOV, then click **Создать и отрендерить пролёт**. The plugin creates an isolated overview with every selected model, saves a Level Sequence with Camera Cut/linear transform keys and renders every frame through a private Movie Render Queue. Existing MRQ jobs are preserved. Mesh components use automatic LOD (`forced_lod_model=0`); geometry warnings do not remove models. Original SM/MI/master/textures are checked by file hashes before/after.

API/MCP: `start_flythrough(profile_path)` returns Run ID, then status/report/cancel. `open_flythrough(run_id)` opens the saved map and native Sequencer; the window has a Run ID field and open button. Requires the bundled SequencerScripting and MovieRenderPipeline engine plugins (enabled by this plugin), an RHI editor, idle PIE/MRQ, saved maps/targets and global r.ForceLOD=-1. Other engine versions remain unverified.

Output: PNG frame sequence, camera/frame manifests and local playback.html. This is not an encoded movie. Cancellation retains partial frames and does not create a complete-playback result. No existing frames or user queues are overwritten. profile.flythrough.example.json supplies defaults: 8 seconds, 24 FPS, 1280×720. The maximum is 1800 frames.

UE 5.8.3 acceptance: UI launch/cancel preserved 15 partial frames; complete LOD and Nanite runs each contain all 12 models and every frame 0…191. The original files/packages and a sentinel editor MRQ queue were preserved. Saved Sequence reopened through the window after editor restart; 73 unit tests passed. Native frames were inspected; HTML JavaScript syntax passed, browser interaction was not tested. Evidence: host Docs/Flythrough. This is a technical overview sweep; artistic approval and per-frame observed LOD telemetry are separate.

## All models with quality warnings (0.14)

The default `validation_policy: "warn"` imports every selected catalog model. Catalog/file triangle differences and losses during Unreal/Nanite building are recorded as quality warnings. They do not remove the mesh from preparation, overview, media or clean delivery. `preparation_passed` and `strict_passed` are separate: successful preparation never certifies geometry quality. Explicit `validation_policy: "strict"` blocks quality discrepancies. The legacy skip_invalid_sources field no longer excludes models.

After import, click **Подготовить все модели к просмотру**. MCP/Python: `create_review_candidate(import_run_id)`. It retains every manifest ID, checks source revisions and current asset settings, and writes a complete review profile with per-model issues. An unreadable/missing file stays in the queue and candidate as an explicit blocking row; no fake mesh or silent omission is created. Invalid global settings, missing output meshes and failed material/LOD/Nanite setup remain operational errors. Changed source revisions require reimport.

Next stage: **Общий просмотр LOD / Nanite** on the delivery tab, with completed media Run IDs separated by commas. MCP/Python: `create_review_bundle(media_run_ids)`. The offline board copies checked PNGs and covers every model in every representation, compares LOD/Nanite images, shows warnings and exports appearance-review decisions. Missing models or changed PNG hashes block the board; quality warnings do not. Technical manifests retain catalog/observed counters and warnings. Artistic approval and publication remain pending.

Version 0.13 subset selection was an incorrect interpretation of the workflow and is superseded. Its old reports/archives remain historical evidence. Current full-catalog acceptance is in Tools/pipeline_all_models_acceptance.py and Docs/AllModelsReview. Historical milestones below refer to earlier exports and policies.

## Automatic LOD boundaries (0.11)

In **Предметы**, **Проверить автоматические LOD** starts a diagnostic camera-distance sweep on selected valid meshes. It uses the first yaw angle, canonical FOV 90° and 1280×720. Each saved LOD threshold after LOD0 is sampled at screen size +10% (near) and -10% (far). Distances use the original mesh bounding-sphere radius and Unreal's projection formula. The existing profile and final mesh screen sizes are preserved. These technical images are separate from the 1920×1080 product media.

The first selected model supplies five forced-LOD calibration frames. Every subsequent frame uses component `forced_lod_model=0` for automatic selection. Forced LOD changes use `set_forced_lod_model`, which marks render state dirty, and are independently read back. Every frame requests `r.MeshDrawCommands.DumpStats`; the report filters actual visible original-mesh BasePass draws, verifies `LODIndex` and total section `PrimitiveCount`, and saves the native CSV next to its PNG. Duplicate/ambiguous draws, missing GPU readback or LOD/triangle mismatches fail the job. Idle editor viewports are invalidated while waiting for GPU readback. Global `r.ForceLOD` must be -1 and `r.StaticMeshLODDistanceScale` must be 1; the tool does not change these cvars.

Open `review.html` next to the frames for expected/observed LOD, triangles, distance and PNG/CSV evidence. The report also records input-file hashes and all original mesh/material/texture package hashes before/after. Original assets are saved in advance; dirty targets block the start. The active viewport view mode is restored at completion/cancellation, and partial evidence remains available. The tool uses the original geometry and materials throughout; no diagnostic mesh copy or material replacement is used.

MCP: `start_automatic_lod_review(profile_path)` on `asset_pack_pipeline.mcp_tools.AssetPackTools`, then `get_job_status` / `get_report` / `cancel_job`. Python in Unreal: `api.start_media(profile_path, automatic_lod=True)`. Both use the same job as the UI. A dedicated example profile is included as `profile.auto-lod.example.json`.

UE 5.8.3 acceptance: UI sample 13 frames (5 calibration + 8 automatic), public MCP cancellation and full 85-frame sweep (5 calibration + 80 automatic across 10 models). All 80 automatic renderer observations matched saved thresholds, including triangle counts. Distances ranged from 1.817 to 19.947 metres; source files and original Unreal packages were unchanged. All collision traces passed. 47 unit tests passed, and the final parser independently reread all 85 native CSVs. Evidence: `Docs/AutomaticLODReview` in the authoring workspace.

This verifies discrete positions around the thresholds; a continuous camera animation and final artistic approval remain separate. The supplied 02/06 geometry is still deferred; only the other 10 models are covered. Other engine versions/platforms remain unverified. Restart Unreal to load updated Python/MCP registrations.

## LOD visual review (0.10)

In **Предметы**, enter `0,1,2,3,4` in **Серия LOD** to render every selected model and angle at each LOD. Leave it blank to use the existing single **Принудительный LOD** field. The JSON equivalent is `media.lod_indices: [0,1,2,3,4]`; it overrides `lod_index` for the series. Each frame reads back `forced_lod_model`, and camera/lighting stay identical across LODs of one model/view. Multi-LOD filenames include `_LOD0`…`_LOD4`; single-LOD names remain compatible. `profile.media-review.example.json` demonstrates the settings.

Every individual media job writes `review.html` and `review.json` next to its completed PNGs, including partial/cancelled results. Open the HTML locally: select model, angle, reference/comparison LOD, and use the wipe slider. The image fits the viewport; links open full-resolution PNGs. Notes and pending/accept/revise decisions are saved per model/view in the browser; **Export review decisions JSON** downloads a local record. These decisions do not change Unreal reports or publication readiness. Keep the HTML, JSON and PNGs together when sharing locally. No network libraries or server are required for the page; browser storage on file URLs can vary, so export notes before closing it.

The media studio now uses a large floor and a two-sided unlit background sphere, eliminating the previous black strip at the horizon. The sphere and its material stay under the isolated studio root and are excluded from content delivery; collision and shadow casting are explicitly disabled. Collision audit failures now fail the media job. For the supplied sample, `sky_intensity=1.1` and `exposure_bias=0` improve readability; existing profile defaults are preserved rather than silently changing their exposure.

Verified in UE 5.8.3: UI-driven four-frame series, MCP-driven 50 LOD frames and 20 hero views for 10 valid models, camera equality across LODs, forced-LOD read-back, collision traces and unchanged source hashes. Browser QA covered model/view/LOD switching, slider clipping, notes persistence and actual JSON download. Separate scene checks found zero Map Check errors/warnings and zero unbuilt light/primitive interactions in overview, LOD review and saved studio, with movable scene lights. Diagnostic console commands must receive the actual editor world, never a null world context. 40 unit tests passed.

This is preliminary visual review. LOD4 visibly changes silhouette/shading up close; check automatic transitions at intended distances in Unreal before approving LOD settings. Geometry 02/06, final artist approval and other UE versions remain open. The source geometry and main working Content were not edited. Evidence and portable pages: `Docs/VisualReview` in the authoring workspace.

## Individual media and Windows cooking (0.9)

The **Предметы** tab generates one PNG per selected asset and yaw angle, using the resolution/warmup/output settings from **Превью**. Set yaw angles, camera pitch/FOV/framing margin, exposure, key/sky intensity and forced LOD. Camera distance fits the mesh bounds automatically. The isolated `/Game/AssetPackPipeline_Previews/<run_id>/Studio` uses the existing final mesh/materials; it is outside the pack and excluded from delivery. Each screenshot records dimensions, size, SHA256, source validity and real X/Y/Z collision traces against the mesh while ignoring the floor. Traces confirm collision presence, not silhouette accuracy.

Invalid models are rejected by default. **Include invalid** is an explicit diagnostic option; resulting filenames/reports are marked diagnostic and never certify publication readiness. Cancellation happens after the current frame. Source hashes are checked after completion. Reports are persisted after each completed frame; warmup ticks do not rewrite them.

In **Поставка**, **Windows cooking** launches a hidden UnrealEditor-Cmd against an already verified clean delivery. It cooks the delivered maps with `-TargetPlatform=Windows -SkipZenStore`, checks exit status/log errors and the actual cooked `.umap` files, and records warnings. This is a content cook, not packaging a game executable. Timeout is 900 seconds. ZIP creation still includes only the original delivery allowlist, excluding cook outputs.

Clean export names the project after the first folder in `destination_root`, preserving Unreal package paths and matching Fab's single Content root convention. Empty editor-created Collections/Developers directories are harmless; foreign files outside the pack root block verification. Default animation compression settings use Engine fallback assets without adding an unused ACL plugin dependency. Child Python script paths use forward slashes to avoid Unreal's Windows backslash escape parsing.

MCP toolset `asset_pack_pipeline.mcp_tools.AssetPackTools` adds `start_individual_previews(profile_path)` and `start_windows_cook(delivery_run_id)`; both return a run ID, polled through `get_job_status` / `get_report`. Manual UI and MCP invoke the same API.

Verified on UE 5.8.3 with all 12 original meshes in both formats: 10/12 strict passes per format, only known geometry failures 02/06 remain deferred. Generated 24 individual 1920×1080 images (four diagnostic), verified collision traces/source hashes, independently opened a clean 10-model project and cooked both maps with zero errors/warnings. Public HTTP MCP media/cook/ZIP operations passed. 37 unit tests passed. Working Content and original exports were not changed by acceptance tests. Other UE versions and final human visual acceptance remain open. Evidence: `Docs/Acceptance` in the authoring workspace.

Development editor plugin for Unreal Engine 5.8.3. Python editor plugin: no native compilation required. This is an internal authoring tool, not a Fab Code Plugin submission.

## Install and use

1. Copy `AssetPackPipeline` into the project's `Plugins` directory.
2. Enable the plugin and restart Unreal. PythonScriptPlugin and Interchange dependencies are enabled by the descriptor. The optional ToolsetRegistry integration registers the MCP adapter when available.
3. Open **Tools → Asset Pack Pipeline → Открыть окно Asset Pack Pipeline…**. The modeless window is owned by Unreal, can be moved/resized, and opens only once. Its event loop is driven by Slate; no separate Python process or pip install is needed. This is a separate window, not a dockable Slate tab.
4. In **Импорт и LOD**, choose the export folder, FBX/GLB, model IDs, destination and LOD screen sizes. A blank model selection means all models. In **Материалы и меши**, set texture folder, roughness, collision and FBX degenerate removal. Keep model 01 selected for the first run.
5. Load/save JSON profiles directly from the window. The initial profile comes from `<Project>/Saved/AssetPackPipeline/active_profile.json` if present. Supported fields are editable; unexposed/unknown keys are preserved. Unsaved settings are used through a session snapshot, so running a job does not overwrite the loaded profile.
6. Click **Проверить исходники**, then **Запустить импорт**. The results tab shows progress, per-model status and triangle counts. Select a model to see details/errors. **Остановить** requests cancellation at the next asset boundary. Closing the window leaves the job running; reopening attaches to the active job. Individual imports may occupy the editor while assets compile.
7. Click **Проверить ассеты** for independent read-back, or **Открыть отчёты** for JSON/Markdown files. Failed triangle checks must be investigated, not silently accepted. Legacy quick menu commands remain available for diagnostics.
8. In **Обзорная сцена**, set grid columns, spacing and label size. **Создать / обновить обзор** creates `/Game/<Destination>/Maps/Overview_<Pack>`. **Сравнение LOD** creates a separate `LOD_Review_<Pack>` map, one row per model with forced LOD0…N. The map contains labelled meshes, floor, movable key/skylight, manual exposure and overview/detail cameras. **Открыть обзор** pilots the saved overview camera; **Проверить сцену** reads back the selected scene mode.

Save/revert all dirty maps before creating or opening a scene. Existing maps must be owned by the plugin; previous `.umap` and built data are backed up under the run. Tagged actors are updated by stable IDs, obsolete generated actors are removed, untagged actors are retained. Detach user actors from generated actors before regenerating. Generation is a short atomic map operation; it cannot be cancelled mid-map. It leaves the generated map open and does not change project startup maps.

By default, every mesh must pass asset validation. Unchecking **Требовать успешную проверку всех мешей** explicitly permits a diagnostic overview. Such a map can be structurally correct while source meshes remain invalid: the report records `diagnostic=true`, `source_assets_valid=false`, and `publication_ready=false`. Scene validation never certifies a Fab-ready package.

Existing target assets must be owned by this plugin (metadata); foreign conflicts fail preflight. Save or revert dirty target packages first. Previous on-disk target packages are backed up under the run's `backup/` before replacement. This is a recovery copy, not an automatic rollback system.

## Staging cleanup and clean delivery (0.8)

**Поставка** provides six actions: cleanup plan, staging cleanup, delivery plan, clean project creation, separate Unreal verification and ZIP packaging. Save/revert all maps and assets first. Choose a staging Run ID to restrict cleanup to one import, or leave it empty for the current pack. New successful FBX staging imports and GLB imports stamp every staged asset with pack/run ownership and save it. Legacy unmarked content remains retained; the plugin never adopts it for automatic deletion.

Cleanup refreshes the complete project registry, checks package referencers and loaded confirmations, and retains dependencies of retained assets. Foreign content, unsupported asset classes and externally referenced staged assets are preserved. Before bulk deletion, dependencies are checked again and every requested package is copied into the report backup. A `partial` result means retained content remains; inspect each row's reason/referencers. The operation uses Unreal's deletion API and is atomic from the UI; backups are recovery copies, not automatic rollback. Source mesh files are not edited.

For delivery, choose `none`, `overview` or `both` maps and an optional absolute destination. A fresh uniquely named folder is created, by default `<Project>/Saved/AssetPackPipeline/Deliveries/<run_id>/<Pack>`. The selected assets must pass strict validation; requested maps must be owned, saved and match the selected meshes. Dependencies are collected recursively inside the pack's Content root. Staging, other project folders, unsupported script modules and plugin content outside `/Engine` block export. Engine content is referenced without copying it. Original `/Game` package paths are retained.

The new project contains Content, minimal Config, a .uproject and a sanitized TechnicalManifest.json. It has no AdditionalPluginDirectories or AssetPackPipeline/MCP references. Default engine plugins are disabled; standard Interchange/InterchangeEditor are explicitly enabled for import metadata. Startup/default map points at the copied overview (or Engine Entry when no maps were selected). Authoring config, automation plugins, source files, caches and logs are not copied.

After creation, the Delivery Run ID field is filled automatically. **Проверить отдельным Unreal** starts a hidden child editor against that project and asynchronously checks meshes, material parents/maps/scalars, LODs, collision and copied maps. PythonScriptPlugin/EditorScriptingUtilities are enabled only for that verification command line. The delivered descriptor does not require them; the child confirms AssetPackPipeline is not importable and MCP/ToolsetRegistry modules are absent. Verification reads the copied assets and does not save them. Keep the authoring editor open until completion; cancellation terminates its own child process.

**Собрать ZIP** requires successful fresh-project verification and unchanged file hashes. It packages only the export manifest's allowlisted files; the child's Saved/Intermediate output is excluded. The archive is integrity-checked and receives a SHA256. Project verification is a structural loading check using NullRHI. Visual/artistic review, cooking, testing all promised engine versions and final Fab acceptance remain separate requirements. Models 02/06 still block a complete GraveStones02 delivery until their source geometry is repaired.

## Incremental batches and resume (0.7)

**Импорт и LOD** now has **Пропускать неизменённые модели после проверки ассетов** (on by default). `plan` reports how many models can be skipped. A run checks each source file hash, the effective per-model settings, the engine/plugin version, the saved Unreal package files (including sidecars) and independent mesh/material/LOD read-back before skipping. A missing receipt, changed source, modified package, failed read-back or unsupported receipt version causes a rebuild. Turning the checkbox off rebuilds every selected model. Cached receipts live under `<Project>/Saved/AssetPackPipeline/Cache`; older plugin runs need one new import/settings run to create them.

Each completed model gets a persistent receipt. At job completion, receipts and read-back are refreshed because the master material and helper texture are shared. Skipped models create no backup; before each rebuilt model, the plugin backs up its existing packages under that run. The earliest backup of a shared package is retained. Unchanged shared materials/helper are no longer resaved on each model. Dirty target assets block a job and are rechecked before an individual model changes.

**Очередь** lists recent import/settings runs. Select a failed, cancelled or interrupted run and click **Продолжить выбранный запуск**. Resume creates a new run ID from the frozen profile saved with the original run. It requires the same project, engine/plugin version, source hashes and selected MeshInfo mapping. Completed models are independently checked; any invalid or unfinished model is processed again. A run interrupted during an asset is never assumed complete. A changed source blocks resume: start a new job with the updated exports instead. A completed run cannot be resumed. The original report remains available and records the interruption.

MCP entry points are `list_runs(limit)` and `resume_job(run_id)`; subsequent progress is read with the existing status/report tools. Import and settings-update jobs participate in this workflow. Diagnostic probes, scene generation and screenshots have separate semantics and cannot be resumed. Receipts are an optimization, not an automated rollback. Backups remain recovery copies.

## Per-model settings and materials (0.6)

**Материалы и меши** now exposes Metallic (0..1), Normal Strength (0..4), UV Scale (0.01..100), and an optional ORM source path. ORM is relative to the export folder; `{asset_id}` expands to the model ID. Packing is fixed: R=AO, G=Roughness, B=Metallic. ORM is imported with sRGB off and Masks compression. Without ORM, Roughness/Metallic are uniform scalars; with ORM, Roughness multiplies G and Metallic comes from B. UV Scale multiplies UV0 for all three maps. Normal Strength scales decoded normal XY and normalizes the resulting vector; zero flattens the normal.

In **По моделям**, enter an exact model ID, load its values, edit fields and click **Записать в профиль**. Empty fields inherit common settings; `inherit` selects inheritance for collision/removal; `-` disables an inherited ORM path. Save the profile after storing edits. Remove overrides with the dedicated button. Only models selected on the import tab are processed. Override fields: `lod_screen_sizes`, `collision`, `remove_degenerates`, `roughness`, `metallic`, `normal_strength`, `uv_scale`, `orm_texture`. Unknown IDs/keys, invalid numeric ranges and changes to LOD count fail preflight. Each manifest/report records effective settings.

**Обновить материалы и настройки без импорта мешей** / MCP `start_settings` requires existing owned meshes and updates selected textures, material instances, the owned master graph, collision, build flags and LOD thresholds. Geometry files are not reimported. Changing a build flag may rebuild existing render data; it does not restore geometry already lost during import. Use a full import when needed. Texture files are reimported; this is not incremental skipping. A source scan is still required.

Legacy owned master graphs are rebuilt in place to graph version 2, retaining asset paths and instance parents. Backups include the previous master, selected instances, textures and meshes. Higher unknown graph versions are rejected. Artist edits to the owned graph are replaced during migration; keep artist-managed materials separate. A failure may leave partial changes; backups are recovery copies, not automatic rollback. Old graphs fail current validation until migrated by import/settings update. Repeated runs at version 2 do not duplicate graph nodes.

One shared `T_<Pack>_ORM_Default` texture provides a valid neutral sampler input for instances without ORM. It is generated under the project Saved folder, then imported into Content with Masks compression. For the current pack without optional maps, expected source textures remain 24; final content includes this helper (25 textures), plus any explicitly enabled per-model ORM textures. Do not remove a referenced helper from delivery. Disabling ORM resets its instance binding to the helper; unused old ORM assets are retained until dependency-safe cleanup is implemented.

## Source and import diagnostics

The **Диагностика** tab uses the model selection from the import tab. **Анализ экспортов** reads binary FBX/GLB geometry and UVs without importing Content. **Сравнить импорт FBX / GLB** queues four isolated cases per model: each format with Remove Degenerates on/off. Reports include source hashes, per-LOD statistics, effective build flags, actual triangle counts and readable explanations. Diagnostic assets are written under `/Game/AssetPackPipeline_Diagnostics/<run_id>` and are excluded from delivery.

A diagnostic job that passes has completed its checks; it does not mean the source geometry passed quality checks. Inspect `source_quality_passed`, findings and `publication_ready=false`. Exact zero-area triangles and descriptive near-zero/zero-UV statistics do not constitute a full topology, tangent or visual audit. Unsupported geometry encodings fail explicitly. Original Blender files are not inspected or repaired.

FBX Remove Degenerates=false uses fresh staged imports for every LOD, then copies them to the stable final mesh. This avoids import_lod resetting import options and reimport preserving an old LOD0 build flag. Effective flags are checked on every FBX LOD. Default removal remains enabled; disabling it is not a geometry repair.

## Preview export

In **Превью**, choose width/height (256..8192, maximum 32 megapixels), scene (`overview`, `lod_review`, `both`), existing camera (`overview`, `detail`), scene warmup and optional absolute output directory. Create and save the matching scenes first. The export validates their saved layout; it never generates or repairs a scene implicitly. Save/revert dirty maps before starting. Camera transform, FOV and aspect ratio come from the saved map; edit them in Unreal for a different composition. The default camera aspect is 16:9.

**Экспортировать PNG** starts an asynchronous RHI capture job. Each run gets its own subfolder, by default `Saved/AssetPackPipeline/Previews/<run_id>`. PNG dimensions, byte size and SHA256 are read back into the JSON/Markdown report. Stop waits for the in-flight screenshot and skips subsequent scenes; completed images remain. Closing the window leaves the job running. The last exported map remains open. An interactive editor viewport is required; commandlet/NullRHI runs are rejected. Existing files are not overwritten.

These are scene previews, not an automatic Fab media acceptance check. Review framing, lighting and materials visually. Per-model turntables, automatic individual camera framing, transparent backgrounds, video and automatic image embedding into listings are not implemented.

## Agent entry points

MCP toolset: `asset_pack_pipeline.mcp_tools.AssetPackTools`.

- `readiness()`
- `open_window()` — show/focus the same settings window manually available from Tools
- `plan(profile_path)` — no Content mutation
- `start_job(profile_path)` — returns run_id
- `start_settings(profile_path)` — queued material/texture/mesh settings update without geometry reimport
- `list_runs(limit=20)` / `resume_job(run_id)` — inspect and continue compatible interrupted queues
- `plan_cleanup(profile_path, staging_run_id="")` / `cleanup_staging(...)`
- `plan_delivery(profile_path)` / `create_delivery(profile_path)`
- `start_delivery_verification(delivery_run_id)` — asynchronous child-editor check; use status/report
- `package_delivery(delivery_run_id)` — create a verified project ZIP
- `get_job_status(run_id)` / `get_report(run_id)`
- `cancel_job(run_id)`
- `validate_pack(profile_path)` — current read-back
- `analyze_sources(profile_path)` — read-only exported geometry/UV analysis and saved report
- `start_diagnostics(profile_path)` — queued FBX/GLB on/off matrix; use the same status/report/cancel methods
- `start_previews(profile_path)` — asynchronous saved-map PNG export; use the same status/report/cancel methods
- `create_overview(profile_path, lod_review=False)` — create/update map, returns persisted run report
- `open_overview(profile_path, lod_review=False)`
- `validate_overview(profile_path, lod_review=False)` — inspect the currently loaded target map

Do not embed package imports in the standard sandboxed ProgrammaticToolset. Call the registered tools. The same underlying Python API is available through `from asset_pack_pipeline import api` in Unreal's Python console. `api.run_blocking(profile_path)` is reserved for PythonScript commandlets.

## Current implementation

- MeshInfo schema 2 adapter, ordered LOD discovery, GLB JSON validation, source hashes and path containment.
- FBX LOD0 import and explicit LOD1..4 import, original normals, external textures.
- GLB per-node import into staging and copy to one Static Mesh with five LODs.
- One versioned master (BaseColor, Normal, ORM, Roughness, Metallic, NormalStrength, UVScale, UseORM), MI per model, texture settings, assignments.
- Conventional LOD screen sizes or Nanite MID/HIGH import, collision none/box, saved-asset read-back, sequential jobs, cancellation at asset boundaries, persisted reports and package backups.
- Generated content has no runtime dependency on this plugin.
- Overview/forced-LOD scenes, bounds-aware layout, lights/cameras/labels, safe repeat generation and saved-map checks.

## Limitations of this milestone

- The window uses Tk bundled with Epic's Windows Python runtime. Docking into the Unreal layout is not implemented. File/folder pickers are modal while choosing a path.
- Clean project/ZIP delivery and owned staging cleanup are implemented. Artistic acceptance and final Fab audit remain pending. Preview export now uses the same AutomationLibrary backend in the product UI and MCP. The API advertises unavailable capabilities explicitly.
- Staging is retained until explicit cleanup. Marked unreferenced content can be backed up/deleted; legacy unmarked content requires manual review. Delivery dependency checks reject staging references.
- Structural validation currently checks LOD triangles/count/thresholds, material slots, MI parent/maps/scalars, graph version, sRGB/compression, bounds, collision count and Nanite. It does not certify UV quality, each section mapping, collision suitability, visual quality or final Fab readiness.
- Roughness/screen sizes and box collision are provisional presets, not validated artistic settings. Source sizes and normal orientation still require visual review.
- Historical exports failed for models 02/06. New 2026-10-22 LOD exports: 06 passes FBX/GLB; 02 retains thin geometry/zero-area UVs and GLB catalog mismatches. New MID sources are separate: Nanite FBX 02/06/12 lose triangles and fail strict validation. Inspect development status for actual counts.

## Nanite sources (0.12)

Use the window's Nanite ON checkbox and AUTO/MID/HIGH selector, or `nanite_enabled: true` and `nanite_source: "AUTO"` in the profile. See Content/Profiles/profile.nanite.example.json. AUTO chooses one catalogued _MID, otherwise one _HIGH. The suffix takes precedence over the legacy HIGH role on new MID exports. Explicit selection never falls back to LOD0 or another kind; missing, conflicting or ambiguous sources fail. Source overrides use asset_overrides[id].nanite_source. Uncatalogued stale files are ignored.

Nanite imports one source LOD, builds actual Nanite resources through the editor subsystem and compares get_num_nanite_triangles with the catalog. The report's triangles field is the fallback mesh count; source_triangles/nanite_triangles describe the compiled Nanite input. A fallback reduction is expected; a source count mismatch is a warning by default and fails only in strict mode. Conventional LOD chains remain available with Nanite OFF. Mode changes require full reimport when source LOD count changes and invalidate incremental receipts.

Overview and single-representation item previews support Nanite. Forced/automatic conventional LOD review and the LOD import comparison require Nanite OFF. Nanite rendering still requires compatible project/RHI settings and visual review. Machine validation does not approve appearance or Fab publication.
- Incremental runs skip unchanged, independently validated assets. Turn off incremental mode for a forced rebuild. User edits to owned assets are not merged. Backup first; keep artist-managed assets at separate paths.

## Development checks

Run `python -m unittest discover -s Tests -v` outside Unreal. Real editor smoke scripts and reports live in the host project's Tools and Saved/AssetPackPipeline directories. Tests import original meshes; they do not modify exports.

Native module prototype is kept in the host project's Docs/NativeModulePrototype. Its build was blocked by missing NetFxSDK in UnrealBuildTool; it is intentionally absent from the installable Python plugin descriptor. The window implementation does not require this SDK.
# 0.15.1 — front camera convention

Overview/detail cameras are on +Y, looking toward the objects with yaw −90°. Text faces +Y (yaw +90°); per-model labels move to the +Y side and the raised title to the back of the layout. Saved overview maps and LOD maps must be regenerated to apply this change. Preview export uses these generated cameras.

Still/automatic-LOD default position azimuths are 90° and 120° (front then front three-quarter). These angles describe the camera position around the object, not the camera rotation. The flythrough sweeps 65°–115° on the +Y side. The old shipped presets [-60,120], [-60] and flythrough -115…-65 are upgraded in UI/runtime; other explicit custom angles are retained. Old rendered media and release candidates remain historical and require regeneration for corrected views. 0.15.1 also includes the dark UI border corrections.

# Current workflow — preparation first (2026-10-28)

By user request, defer artistic acceptance and skip per-model/per-LOD renders, automatic LOD screenshot sweeps, comparison boards and flythrough/video. Prepare all meshes, authored LODs or MID/HIGH Nanite sources, master/instances, textures, collision, overview map and clean verified project ZIPs. Keep technical read-back and clean-project/cook checks. Produce exactly **one overview PNG for the whole pack**, even when preparing both LOD and Nanite project variants. Camera is on +Y looking toward −Y, labels face the camera. Preserve quality warnings and every model; do not label deferred acceptance as passed or publication-ready. Historical acceptance runners are not the current default workflow. Reusable host runner: Tools/pipeline_preparation_only.py, configured by Saved/AssetPackPipeline/PreparationOnly/request.json.

# 0.16.0 — single-project LOD/Nanite delivery

The current output is **one .uproject and one ZIP**, with StaticMeshes/LOD and StaticMeshes/Nanite under the same Content pack root. Materials/instances/textures are shared. Use profiles with the same pack_id/source_root/destination_root, distinct mesh_subdirectory values and Overview_LOD/Overview_Nanite maps. `api.create_combined_delivery([lod_profile_path, nanite_profile_path])` creates the union of both dependency closures; MCP accepts profile_paths as a JSON array string. Separate-editor verification checks both sets, shared instances and a single master. The preparation-only runner now follows this scheme. Keep one PNG per pack; artistic acceptance remains deferred. Older instructions describing separate variant projects are superseded for the current workflow.

Manual UI: load `profile.combined.lod.example.json` and `profile.combined.nanite.example.json`, set the same source directory/pack root and run the two imports in sequence. The import tab exposes the mesh subdirectory. On the delivery tab enter the companion JSON profile and click **Один проект LOD + Nanite**, then verify/cook/package using its delivery Run ID. Both imports and saved overview maps must exist before delivery. Host automation publishes the combined result with `Tools/publish_combined_preparation.py <result.json>`; the older two-project publisher is only for historical reports.

# 0.16.1 — clean project Content Browser fix

Clean delivery descriptors explicitly enable Epic's ContentBrowserAssetDataSource and ContentBrowserClassDataSource while keeping authoring plugins excluded. Disabling all default engine plugins without these sources leaves the Content Browser tree empty even when meshes load. Standalone delivery verification now requires an active asset data source in ContentBrowserDataSubsystem. Existing extracted projects can enable these two built-in plugins and restart; new deliveries include them automatically.

# 0.16.2 — Nanite project defaults and explicit mesh names

Combined deliveries explicitly select Windows DX12 + SM6 and Nanite project support. Clean verification records native import filenames, Nanite resource triangles and fallback triangles separately, and requires the imported filename to match the selected MID/HIGH source. Editor fallback/wireframe representations can be much coarser than the original Nanite data; use Nanite visualization to inspect the actual rendered representation.

In combined profiles, mesh_subdirectory=LOD produces SM_<ID>_LODS; mesh_subdirectory=Nanite produces SM_<ID>_MID. Legacy profiles with no subdirectory keep their names. Shared material/texture names remain based on the unique model ID. Rebuild rather than renaming binary packages in the filesystem.

