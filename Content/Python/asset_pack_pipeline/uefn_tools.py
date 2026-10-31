"""Small UEFN-only MCP surface, intentionally excludes ordinary UE delivery/import commands."""
import json
import unreal
import toolset_registry
from . import uefn


@unreal.uclass()
class UEFNAssetPackTools(unreal.ToolsetDefinition):
    """Inspect UEFN compatibility and verify migrated asset packs."""

    @toolset_registry.tool_call
    @staticmethod
    def environment(project_file: str) -> str:
        """Read UEFN project identity and available editing/validation APIs."""
        return json.dumps(uefn.environment(project_file))

    @toolset_registry.tool_call
    @staticmethod
    def inspect_transfer(plan_path: str) -> str:
        """Read both migrated representations and verify geometry, materials and collisions."""
        from .discovery import read_json
        return json.dumps(uefn.inspect(read_json(plan_path)))
