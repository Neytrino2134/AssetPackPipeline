#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AssetPackPipelineNative.generated.h"

UCLASS()
class ASSETPACKPIPELINEEDITOR_API UAssetPackPipelineNative : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Asset Pack Pipeline")
    static void OpenWindow();
    UFUNCTION(BlueprintCallable, Category="Asset Pack Pipeline")
    static bool IsWindowOpen();
    UFUNCTION(BlueprintCallable, Category="Asset Pack Pipeline")
    static void CloseWindow();
    UFUNCTION(BlueprintCallable, Category="Asset Pack Pipeline|Tests")
    static bool RunUIRegressionStep(int32 Iteration);
};
