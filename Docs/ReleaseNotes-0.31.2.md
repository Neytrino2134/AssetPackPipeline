# MESHFLOW Asset Pack Pipeline v0.31.2

## Full pack folder cleanup
- «Удалить всё и папку…» in the cleanup plan (Custom UI and Slate Content cleanup):
  1. backs up every file of the folder on disk (including files Unreal does not track)
     and the outside packages that reference it, to Saved/AssetPackPipeline/ImportedCleanup;
  2. opens L_Presentation outside the folder, or creates /Game/Presentation/L_Presentation
     from the Basic template (Template_Default) when the project has none;
  3. force-deletes every asset in the folder and removes the folder, including the root
     pack folder; untracked leftover files are removed after the backup;
  4. saves the packages whose references were cleared (nothing else was dirty before).
- Previously the open map and externally referenced assets (e.g. meshes used by preview
  studios) were kept, leaving the folder tree behind.
- The plan lists everything with Russian reasons, the number of outside referencing
  packages and whether L_Presentation will be opened or created. Deletion runs in the
  background with a progress note; the journal records the result and backup path.
- Presentation and AssetPackPipeline folders stay protected. Automated smoke/E2E tools
  keep the conservative cleanup. Custom UI waits up to 30 min for this RPC.

Validated: unit tests with a mocked editor (plan, step order, backups, template map
creation, protected folders), cleanup window preview, UE 5.8 API/template presence.
Not yet run on a real pack in Unreal. Same C++ module as v0.30.0. Unreal Engine 5.8.4 Win64.
