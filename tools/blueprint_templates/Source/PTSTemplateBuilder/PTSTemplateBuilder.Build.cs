using UnrealBuildTool;
public class PTSTemplateBuilder : ModuleRules
{
    public PTSTemplateBuilder(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {"Core", "CoreUObject", "Engine"});
        PrivateDependencyModuleNames.AddRange(new[] {"UnrealEd", "BlueprintGraph", "KismetCompiler", "Kismet", "InputCore", "Blutility", "UMG", "UMGEditor", "Slate", "SlateCore"});
    }
}
