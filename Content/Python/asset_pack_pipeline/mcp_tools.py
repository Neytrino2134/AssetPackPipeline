import json
import unreal
import toolset_registry
from . import api


@unreal.uclass()
class AssetPackTools(unreal.ToolsetDefinition):
    """Run repeatable asset-pack jobs and independently inspect their results."""

    @toolset_registry.tool_call
    @staticmethod
    def open_custom_window() -> str:
        """Launch or focus the isolated Custom UI; Unreal retains ownership of jobs."""
        from . import ui
        return json.dumps(ui.open_custom_window())

    @toolset_registry.tool_call
    @staticmethod
    def create_combined_delivery(profile_paths: str) -> str:
        """Create one content project from a JSON array of LOD/Nanite profile paths with a shared pack root."""
        return json.dumps(api.create_combined_delivery(json.loads(profile_paths)))

    @toolset_registry.tool_call
    @staticmethod
    def open_window() -> str:
        """Show or focus the modeless Asset Pack Pipeline settings window."""
        from . import ui
        ui.open_window()
        return json.dumps({'open':True,'ui':'native'})

    @toolset_registry.tool_call
    @staticmethod
    def readiness() -> str:
        """Get project identity, supported capabilities and active job."""
        return json.dumps(api.readiness())

    @toolset_registry.tool_call
    @staticmethod
    def plan(profile_path: str) -> str:
        """Validate files, LOD mapping and destination conflicts without import."""
        return json.dumps(api.plan(profile_path))

    @toolset_registry.tool_call
    @staticmethod
    def start_job(profile_path: str) -> str:
        """Start a sequential import/material/LOD batch. Returns run_id quickly."""
        return api.start(profile_path)

    @toolset_registry.tool_call
    @staticmethod
    def start_settings(profile_path: str) -> str:
        """Update per-model settings, textures and versioned materials without mesh reimport; returns run_id."""
        return api.start_settings(profile_path)

    @toolset_registry.tool_call
    @staticmethod
    def create_review_candidate(import_run_id: str) -> str:
        """Prepare every catalog model for review, retain quality warnings, and explicitly report unreadable inputs."""
        return json.dumps(api.create_review_candidate(import_run_id))

    @toolset_registry.tool_call
    @staticmethod
    def create_review_bundle(media_run_ids: str) -> str:
        """Build a complete-model LOD/Nanite comparison board from comma-separated completed media Run IDs."""
        return json.dumps(api.create_review_bundle(media_run_ids))

    @toolset_registry.tool_call
    @staticmethod
    def start_flythrough(profile_path: str) -> str:
        """Create an isolated Level Sequence and render all continuous camera frames using a private MRQ queue."""
        return api.start_flythrough(profile_path)

    @toolset_registry.tool_call
    @staticmethod
    def open_flythrough(run_id: str) -> str:
        """Open the saved flythrough map and Level Sequence for native editor playback."""
        return json.dumps(api.open_flythrough(run_id))

    @toolset_registry.tool_call
    @staticmethod
    def list_runs(limit: int = 20) -> str:
        """List recent persisted import/settings runs and their statuses."""
        return json.dumps(api.list_runs(limit))

    @toolset_registry.tool_call
    @staticmethod
    def resume_job(run_id: str) -> str:
        """Resume a failed/cancelled/interrupted run from its frozen profile in a new run."""
        return api.resume(run_id)

    @toolset_registry.tool_call
    @staticmethod
    def plan_cleanup(profile_path: str, staging_run_id: str = '') -> str:
        """List owned staging candidates and retained external dependencies without deletion."""
        return json.dumps(api.plan_cleanup(profile_path, staging_run_id))

    @toolset_registry.tool_call
    @staticmethod
    def cleanup_staging(profile_path: str, staging_run_id: str = '') -> str:
        """Back up and delete only unreferenced owned staging assets; retain foreign/referenced content."""
        return json.dumps(api.cleanup_staging(profile_path, staging_run_id))

    @toolset_registry.tool_call
    @staticmethod
    def plan_delivery(profile_path: str) -> str:
        """Validate selected assets/maps and inspect the clean project's dependency closure."""
        return json.dumps(api.plan_delivery(profile_path))

    @toolset_registry.tool_call
    @staticmethod
    def create_delivery(profile_path: str) -> str:
        """Create a separate clean content project, keeping Unreal package paths."""
        return json.dumps(api.create_delivery(profile_path))

    @toolset_registry.tool_call
    @staticmethod
    def start_delivery_verification(delivery_run_id: str) -> str:
        """Launch a separate Unreal editor without authoring plugins and read back the copied project."""
        return api.start_delivery_verification(delivery_run_id)

    @toolset_registry.tool_call
    @staticmethod
    def package_delivery(delivery_run_id: str) -> str:
        """ZIP a successfully verified clean project, excluding generated Saved/Intermediate files."""
        return json.dumps(api.package_delivery(delivery_run_id))

    @toolset_registry.tool_call
    @staticmethod
    def start_windows_cook(delivery_run_id: str) -> str:
        """Cook verified clean-project maps for Windows in a separate commandlet; returns run_id."""
        return api.start_cook(delivery_run_id)

    @toolset_registry.tool_call
    @staticmethod
    def get_job_status(run_id: str) -> str:
        """Read persisted per-asset checks, failures and current progress."""
        report = api.status(run_id)
        return json.dumps({key: report.get(key) for key in
                           ('run_id', 'status', 'assets', 'report_path', 'visual_review')})

    @toolset_registry.tool_call
    @staticmethod
    def get_report(run_id: str) -> str:
        """Read the full report including manifest and source hashes."""
        return json.dumps(api.status(run_id))

    @toolset_registry.tool_call
    @staticmethod
    def cancel_job(run_id: str) -> str:
        """Cancel at the next safe asset boundary. Completed imports are retained."""
        return json.dumps(api.cancel(run_id))

    @toolset_registry.tool_call
    @staticmethod
    def validate_pack(profile_path: str) -> str:
        """Independently read back current saved mesh/material/LOD parameters."""
        return json.dumps(api.validate(profile_path))

    @toolset_registry.tool_call
    @staticmethod
    def analyze_sources(profile_path: str) -> str:
        """Analyze raw FBX/GLB triangles/UV and save evidence without importing."""
        return json.dumps(api.analyze_sources(profile_path))

    @toolset_registry.tool_call
    @staticmethod
    def start_diagnostics(profile_path: str) -> str:
        """Queue isolated FBX/GLB Remove Degenerates on/off probes; returns run_id."""
        return api.start_diagnostics(profile_path)

    @toolset_registry.tool_call
    @staticmethod
    def start_previews(profile_path: str) -> str:
        """Export saved overview/LOD map PNGs with profile camera/resolution settings; returns run_id."""
        return api.start_previews(profile_path)

    @toolset_registry.tool_call
    @staticmethod
    def start_individual_previews(profile_path: str) -> str:
        """Render selected models individually using bounds framing, profile angles/lighting and explicit diagnostic policy."""
        return api.start_media(profile_path)

    @toolset_registry.tool_call
    @staticmethod
    def start_automatic_lod_review(profile_path: str) -> str:
        """Probe automatic LOD boundaries with original-mesh draw-command LOD/triangle CSVs and lit images."""
        return api.start_media(profile_path,automatic_lod=True)

    @toolset_registry.tool_call
    @staticmethod
    def create_overview(profile_path: str, lod_review: bool = False) -> str:
        """Create/update the owned overview or forced-LOD map. Dirty maps block changes."""
        return json.dumps(api.create_overview(profile_path, lod_review))

    @toolset_registry.tool_call
    @staticmethod
    def open_overview(profile_path: str, lod_review: bool = False) -> str:
        """Open the saved owned overview map and pilot its overview camera."""
        return json.dumps(api.open_overview(profile_path, lod_review))

    @toolset_registry.tool_call
    @staticmethod
    def validate_overview(profile_path: str, lod_review: bool = False) -> str:
        """Independently read back the current overview placement, LODs and actors."""
        return json.dumps(api.validate_overview(profile_path, lod_review))
