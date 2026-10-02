#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "PTSTemplateBuilder.generated.h"

// The generated assets only reference stock Engine nodes, never this builder module.
UCLASS()
class PTSTEMPLATEBUILDER_API UPTSTemplateBuilder : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="PromptToScene")
    static UBlueprint* BuildInteractiveTemplate(const FString& PackagePath);
};
