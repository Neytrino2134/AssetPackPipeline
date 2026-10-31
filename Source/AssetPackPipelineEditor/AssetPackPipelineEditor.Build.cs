using UnrealBuildTool;
public class AssetPackPipelineEditor : ModuleRules
{
    public AssetPackPipelineEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "Slate", "SlateCore", "InputCore", "UnrealEd", "PythonScriptPlugin", "DesktopPlatform", "Json", "Projects" });
    }
}
