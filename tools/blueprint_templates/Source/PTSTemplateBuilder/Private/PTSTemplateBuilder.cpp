#include "PTSTemplateBuilder.h"
#include "Modules/ModuleManager.h"
#include "Engine/Blueprint.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/SimpleConstructionScript.h"
#include "Engine/SCS_Node.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Camera/PlayerCameraManager.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_CallFunction.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_InputKey.h"
#include "K2Node_Self.h"
#include "K2Node_MakeArray.h"
#include "InputCoreTypes.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, PTSTemplateBuilder)

namespace
{
struct FBuilder
{
    UBlueprint* BP;
    UEdGraph* Graph;
    const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();
    int32 Index = 0;
    template<class T> T* Node()
    {
        auto* N = NewObject<T>(Graph);
        Graph->AddNode(N, false, false); N->CreateNewGuid();
        N->NodePosX = (Index % 7) * 360; N->NodePosY = (Index / 7) * 280; ++Index;
        return N;
    }
    void Link(UEdGraphPin* A, UEdGraphPin* B)
    {
        checkf(A && B && Schema->TryCreateConnection(A,B), TEXT("Invalid graph connection"));
    }
    UEdGraphPin* Pin(UEdGraphNode* N, const TCHAR* Name) { return N->FindPinChecked(Name); }
    UEdGraphPin* Out(UEdGraphNode* N) { return Pin(N,TEXT("ReturnValue")); }
    void Default(UEdGraphNode* N, const TCHAR* Name, const FString& Value)
    { Schema->TrySetDefaultValue(*Pin(N,Name),Value); }
    UK2Node_CallFunction* Call(UClass* Class, const TCHAR* Name)
    {
        UFunction* Fn=Class->FindFunctionByName(Name); checkf(Fn,TEXT("Missing %s"),Name);
        auto* N=Node<UK2Node_CallFunction>(); N->SetFromFunction(Fn); N->AllocateDefaultPins(); return N;
    }
    UK2Node_CustomEvent* Event(const TCHAR* Name)
    { auto* N=Node<UK2Node_CustomEvent>(); N->CustomFunctionName=Name; N->AllocateDefaultPins(); return N; }
    UEdGraphPin* Get(const TCHAR* Name)
    {
        auto* N=Node<UK2Node_VariableGet>(); N->VariableReference.SetSelfMember(Name); N->AllocateDefaultPins();
        return Pin(N,Name);
    }
    UK2Node_VariableSet* Set(const TCHAR* Name)
    { auto* N=Node<UK2Node_VariableSet>(); N->VariableReference.SetSelfMember(Name); N->AllocateDefaultPins(); return N; }
    UEdGraphPin* Exec(UEdGraphPin* Prev, UEdGraphNode* Next)
    { Link(Prev,Pin(Next,TEXT("execute"))); return Pin(Next,TEXT("then")); }
    UK2Node_IfThenElse* Branch(UEdGraphPin* Prev, UEdGraphPin* Condition)
    {
        auto* N=Node<UK2Node_IfThenElse>(); N->AllocateDefaultPins();
        Link(Prev,N->GetExecPin()); Link(Condition,N->GetConditionPin()); return N;
    }
    void Var(const TCHAR* Name, FName Category, const FString& Value, UObject* Sub=nullptr)
    {
        FEdGraphPinType Type; Type.PinCategory=Category; Type.PinSubCategoryObject=Sub;
        if(Category==UEdGraphSchema_K2::PC_Real) Type.PinSubCategory=UEdGraphSchema_K2::PC_Double;
        FBlueprintEditorUtils::AddMemberVariable(BP,Name,Type,Value);
        if(auto* Flags=FBlueprintEditorUtils::GetBlueprintVariablePropertyFlags(BP,Name))
            *Flags=(*Flags & ~CPF_DisableEditOnInstance) | CPF_Edit | CPF_BlueprintVisible;
        FBlueprintEditorUtils::SetBlueprintVariableCategory(BP,Name,nullptr,FText::FromString(TEXT("Prompt to Scene")));
    }
    UK2Node_CallFunction* Rotation(UEdGraphPin* Prev, bool Open)
    {
        auto* SetOpen=Set(TEXT("Open")); Default(SetOpen,TEXT("Open"),Open?TEXT("true"):TEXT("false"));
        Prev=Exec(Prev,SetOpen);
        auto* Rotate=Call(USceneComponent::StaticClass(),TEXT("K2_SetRelativeRotation"));
        Link(Get(TEXT("MovingPivot")),Pin(Rotate,TEXT("self")));
        if(Open) Link(Get(TEXT("OpenRotation")),Pin(Rotate,TEXT("NewRotation")));
        Exec(Prev,Rotate); return Rotate;
    }
};
}

UBlueprint* UPTSTemplateBuilder::BuildInteractiveTemplate(const FString& PackagePath)
{
    UPackage* Package=CreatePackage(*PackagePath);
    const FName Name(*FPackageName::GetLongPackageAssetName(PackagePath));
    UBlueprint* BP=FKismetEditorUtilities::CreateBlueprint(AStaticMeshActor::StaticClass(),Package,Name,
        BPTYPE_Normal,UBlueprint::StaticClass(),UBlueprintGeneratedClass::StaticClass());
    check(BP);
    auto* Pivot=BP->SimpleConstructionScript->CreateNode(USceneComponent::StaticClass(),TEXT("MovingPivot"));
    Pivot->SetParent(GetDefault<AStaticMeshActor>()->GetStaticMeshComponent());
    BP->SimpleConstructionScript->AddNode(Pivot);
    auto* Moving=BP->SimpleConstructionScript->CreateNode(UStaticMeshComponent::StaticClass(),TEXT("MovingMesh"));
    Pivot->AddChildNode(Moving);
    Cast<USceneComponent>(Pivot->ComponentTemplate)->SetMobility(EComponentMobility::Movable);
    Cast<USceneComponent>(Moving->ComponentTemplate)->SetMobility(EComponentMobility::Movable);
    UEdGraph* Graph=BP->UbergraphPages.Num()?BP->UbergraphPages[0].Get():FBlueprintEditorUtils::CreateNewGraph(BP,TEXT("EventGraph"),UEdGraph::StaticClass(),UEdGraphSchema_K2::StaticClass());
    if(!BP->UbergraphPages.Contains(Graph)) FBlueprintEditorUtils::AddUbergraphPage(BP,Graph);
    FBuilder B{BP,Graph};
    B.Var(TEXT("Open"),UEdGraphSchema_K2::PC_Boolean,TEXT("false"));
    B.Var(TEXT("Collected"),UEdGraphSchema_K2::PC_Boolean,TEXT("false"));
    B.Var(TEXT("InteractionCount"),UEdGraphSchema_K2::PC_Int,TEXT("0"));
    B.Var(TEXT("TemplateKind"),UEdGraphSchema_K2::PC_Int,TEXT("0"));
    B.Var(TEXT("InteractionRange"),UEdGraphSchema_K2::PC_Real,TEXT("250"));
    B.Var(TEXT("OpenRotation"),UEdGraphSchema_K2::PC_Struct,TEXT("(Pitch=0,Yaw=90,Roll=0)"),TBaseStructure<FRotator>::Get());
    auto* Hook=B.Event(TEXT("OnInteracted"));
    auto* Interact=B.Event(TEXT("Interact"));
    auto* Try=B.Event(TEXT("TryInteract"));
    FEdGraphPinType VectorType; VectorType.PinCategory=UEdGraphSchema_K2::PC_Struct; VectorType.PinSubCategoryObject=TBaseStructure<FVector>::Get();
    Try->CreateUserDefinedPin(TEXT("WorldPosition"),VectorType,EGPD_Output);
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
    FKismetEditorUtilities::CompileBlueprint(BP);
    auto* NotCollected=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Not_PreBool"));
    B.Link(B.Get(TEXT("Collected")),B.Pin(NotCollected,TEXT("A")));
    auto* Guard=B.Branch(B.Pin(Interact,TEXT("then")),B.Out(NotCollected));
    auto* Add=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Add_IntInt"));
    B.Link(B.Get(TEXT("InteractionCount")),B.Pin(Add,TEXT("A"))); B.Default(Add,TEXT("B"),TEXT("1"));
    auto* Count=B.Set(TEXT("InteractionCount")); B.Link(B.Out(Add),B.Pin(Count,TEXT("InteractionCount")));
    auto* Next=B.Exec(Guard->GetThenPin(),Count);
    auto* Eq=B.Call(UKismetMathLibrary::StaticClass(),TEXT("EqualEqual_IntInt"));
    B.Link(B.Get(TEXT("TemplateKind")),B.Pin(Eq,TEXT("A"))); B.Default(Eq,TEXT("B"),TEXT("2"));
    auto* Pickup=B.Branch(Next,B.Out(Eq));
    auto* Collected=B.Set(TEXT("Collected")); B.Default(Collected,TEXT("Collected"),TEXT("true"));
    Next=B.Exec(Pickup->GetThenPin(),Collected);
    auto* Hide=B.Call(AActor::StaticClass(),TEXT("SetActorHiddenInGame")); B.Default(Hide,TEXT("bNewHidden"),TEXT("true"));
    Next=B.Exec(Next,Hide);
    auto* Collision=B.Call(AActor::StaticClass(),TEXT("SetActorEnableCollision")); B.Default(Collision,TEXT("bNewActorEnableCollision"),TEXT("false"));
    Next=B.Exec(Next,Collision);
    B.Exec(Next,B.Call(BP->SkeletonGeneratedClass,TEXT("OnInteracted")));
    auto* OpenBranch=B.Branch(Pickup->GetElsePin(),B.Get(TEXT("Open")));
    auto* Close=B.Rotation(OpenBranch->GetThenPin(),false);
    auto* Open=B.Rotation(OpenBranch->GetElsePin(),true);
    B.Exec(B.Pin(Close,TEXT("then")),B.Call(BP->SkeletonGeneratedClass,TEXT("OnInteracted")));
    B.Exec(B.Pin(Open,TEXT("then")),B.Call(BP->SkeletonGeneratedClass,TEXT("OnInteracted")));
    auto* Location=B.Call(AActor::StaticClass(),TEXT("K2_GetActorLocation"));
    auto* Distance=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Vector_Distance"));
    B.Link(B.Out(Location),B.Pin(Distance,TEXT("V1"))); B.Link(B.Pin(Try,TEXT("WorldPosition")),B.Pin(Distance,TEXT("V2")));
    auto* Within=B.Call(UKismetMathLibrary::StaticClass(),TEXT("LessEqual_DoubleDouble"));
    B.Link(B.Out(Distance),B.Pin(Within,TEXT("A"))); B.Link(B.Get(TEXT("InteractionRange")),B.Pin(Within,TEXT("B")));
    auto* Range=B.Branch(B.Pin(Try,TEXT("then")),B.Out(Within));
    B.Exec(Range->GetThenPin(),B.Call(BP->SkeletonGeneratedClass,TEXT("Interact")));
    // Optional demo E input: a camera trace selects a single visible object.
    auto* Key=B.Node<UK2Node_InputKey>(); Key->InputKey=EKeys::E; Key->bConsumeInput=false; Key->AllocateDefaultPins();
    auto* Camera=B.Call(UGameplayStatics::StaticClass(),TEXT("GetPlayerCameraManager"));
    auto* CameraPos=B.Call(APlayerCameraManager::StaticClass(),TEXT("GetCameraLocation"));
    auto* CameraRot=B.Call(APlayerCameraManager::StaticClass(),TEXT("GetCameraRotation"));
    B.Link(B.Out(Camera),B.Pin(CameraPos,TEXT("self"))); B.Link(B.Out(Camera),B.Pin(CameraRot,TEXT("self")));
    auto* Forward=B.Call(UKismetMathLibrary::StaticClass(),TEXT("GetForwardVector")); B.Link(B.Out(CameraRot),B.Pin(Forward,TEXT("InRot")));
    auto* Scale=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Multiply_VectorFloat")); B.Link(B.Out(Forward),B.Pin(Scale,TEXT("A"))); B.Link(B.Get(TEXT("InteractionRange")),B.Pin(Scale,TEXT("B")));
    auto* End=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Add_VectorVector")); B.Link(B.Out(CameraPos),B.Pin(End,TEXT("A"))); B.Link(B.Out(Scale),B.Pin(End,TEXT("B")));
    auto* Trace=B.Call(UKismetSystemLibrary::StaticClass(),TEXT("LineTraceSingle"));
    B.Link(B.Out(CameraPos),B.Pin(Trace,TEXT("Start"))); B.Link(B.Out(End),B.Pin(Trace,TEXT("End")));
    B.Default(Trace,TEXT("bIgnoreSelf"),TEXT("false")); B.Default(Trace,TEXT("bTraceComplex"),TEXT("true"));
    auto* Empty=B.Node<UK2Node_MakeArray>(); Empty->NumInputs=0; Empty->AllocateDefaultPins(); B.Link(B.Pin(Empty,TEXT("Array")),B.Pin(Trace,TEXT("ActorsToIgnore")));
    B.Exec(B.Pin(Key,TEXT("Pressed")),Trace);
    auto* Hit=B.Call(UGameplayStatics::StaticClass(),TEXT("BreakHitResult")); B.Link(B.Pin(Trace,TEXT("OutHit")),B.Pin(Hit,TEXT("Hit")));
    auto* Self=B.Node<UK2Node_Self>(); Self->AllocateDefaultPins();
    auto* Equal=B.Call(UKismetMathLibrary::StaticClass(),TEXT("EqualEqual_ObjectObject")); B.Link(B.Pin(Hit,TEXT("HitActor")),B.Pin(Equal,TEXT("A"))); B.Link(B.Pin(Self,TEXT("self")),B.Pin(Equal,TEXT("B")));
    auto* Aimed=B.Branch(B.Pin(Trace,TEXT("then")),B.Out(Equal));
    auto* TryCall=B.Call(BP->SkeletonGeneratedClass,TEXT("TryInteract")); B.Link(B.Out(CameraPos),B.Pin(TryCall,TEXT("WorldPosition"))); B.Exec(Aimed->GetThenPin(),TryCall);
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP); FKismetEditorUtilities::CompileBlueprint(BP);
    auto* Defaults=Cast<AStaticMeshActor>(BP->GeneratedClass->GetDefaultObject());
    Defaults->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
    Defaults->AutoReceiveInput=EAutoReceiveInput::Player0;
    checkf(BP->Status != BS_Error,TEXT("Template Blueprint failed compilation"));
    BP->MarkPackageDirty(); return BP;
}
