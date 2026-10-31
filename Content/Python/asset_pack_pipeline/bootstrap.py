"""Idempotent menu and optional MCP registration."""
import unreal

_registration = None


def register():
    global _registration
    if '-run=' not in unreal.SystemLibrary.get_command_line().lower():
        from . import ui
        ui.register()
    if _registration is None and hasattr(unreal, 'ToolsetDefinition'):
        try:
            from toolset_registry.registration import Registration
            from .mcp_tools import AssetPackTools
            _registration = Registration([AssetPackTools])
            if not _registration.register():
                _registration = None
                unreal.log_warning('AssetPackPipeline: MCP registry unavailable; manual mode remains available')
        except ImportError:
            unreal.log_warning('AssetPackPipeline: MCP adapter unavailable; manual mode remains available')
    from . import __version__
    unreal.log(f'AssetPackPipeline {__version__} initialized')
