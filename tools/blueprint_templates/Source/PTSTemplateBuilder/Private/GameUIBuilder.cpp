#include "PTSTemplateBuilder.h"
#include "WidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetBlueprintLibrary.h"
#include "Engine/DataAsset.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "Blueprint/WidgetBlueprintGeneratedClass.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "GameFramework/PlayerController.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Border.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/UniformGridPanel.h"
#include "Components/SizeBox.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Components/Image.h"
#include "Components/ProgressBar.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/GameplayStatics.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_Event.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_CallFunction.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_InputKey.h"
#include "K2Node_Self.h"
#include "InputCoreTypes.h"
#include "Misc/PackageName.h"

namespace {
struct G
{
 UBlueprint* BP; UEdGraph* Graph; const UEdGraphSchema_K2* S=GetDefault<UEdGraphSchema_K2>(); int I=0;
 G(UBlueprint* In):BP(In){Graph=BP->UbergraphPages.Num()?BP->UbergraphPages[0].Get():FBlueprintEditorUtils::CreateNewGraph(BP,TEXT("EventGraph"),UEdGraph::StaticClass(),UEdGraphSchema_K2::StaticClass());if(!BP->UbergraphPages.Contains(Graph))FBlueprintEditorUtils::AddUbergraphPage(BP,Graph);}
 template<class T>T* Node(){auto* N=NewObject<T>(Graph);Graph->AddNode(N,false,false);N->CreateNewGuid();N->NodePosX=(I%6)*380;N->NodePosY=(I/6)*260;I++;return N;}
 UEdGraphPin* P(UEdGraphNode* N,const TCHAR* Name){return N->FindPinChecked(Name);}
 void L(UEdGraphPin* A,UEdGraphPin* B){checkf(A && B && S->TryCreateConnection(A,B),TEXT("Game UI graph connection failed"));}
 void D(UEdGraphNode* N,const TCHAR* Name,FString Value){S->TrySetDefaultValue(*P(N,Name),Value);}
 void Compile(){FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);FKismetEditorUtilities::CompileBlueprint(BP);check(BP->Status!=BS_Error);}
 void Var(FString Name,FName Cat,UObject* Type=nullptr,FString Default=TEXT("")){
  FEdGraphPinType T;T.PinCategory=Cat;T.PinSubCategoryObject=Type;if(Cat==UEdGraphSchema_K2::PC_Real)T.PinSubCategory=UEdGraphSchema_K2::PC_Float;
  FBlueprintEditorUtils::AddMemberVariable(BP,*Name,T,Default);
  if(auto* F=FBlueprintEditorUtils::GetBlueprintVariablePropertyFlags(BP,*Name))*F=(*F & ~CPF_DisableEditOnInstance)|CPF_Edit|CPF_BlueprintVisible;
 }
 UEdGraphPin* Get(FString Name){auto* N=Node<UK2Node_VariableGet>();N->VariableReference.SetSelfMember(*Name);N->AllocateDefaultPins();return P(N,*Name);}
 UEdGraphPin* Field(FString Name,UClass* C,UEdGraphPin* Obj){auto* N=Node<UK2Node_VariableGet>();N->VariableReference.SetExternalMember(*Name,C);N->AllocateDefaultPins();L(Obj,P(N,TEXT("self")));return P(N,*Name);}
 UK2Node_VariableSet* Set(FString Name){auto* N=Node<UK2Node_VariableSet>();N->VariableReference.SetSelfMember(*Name);N->AllocateDefaultPins();return N;}
 UK2Node_CallFunction* Call(UClass* C,const TCHAR* Name){auto* F=C->FindFunctionByName(Name);checkf(F,TEXT("Missing UI function %s"),Name);auto* N=Node<UK2Node_CallFunction>();N->SetFromFunction(F);N->AllocateDefaultPins();return N;}
 UEdGraphPin* Exec(UEdGraphPin* Prev,UEdGraphNode* N){L(Prev,P(N,TEXT("execute")));return P(N,TEXT("then"));}
 UK2Node_CustomEvent* Event(const TCHAR* Name){auto* N=Node<UK2Node_CustomEvent>();N->CustomFunctionName=Name;N->AllocateDefaultPins();return N;}
 UEdGraphPin* Param(UK2Node_CustomEvent* E,const TCHAR* Name,FName Category,UObject* Object=nullptr){FEdGraphPinType T;T.PinCategory=Category;T.PinSubCategoryObject=Object;if(Category==UEdGraphSchema_K2::PC_Real)T.PinSubCategory=UEdGraphSchema_K2::PC_Float;return E->CreateUserDefinedPin(Name,T,EGPD_Output);}
 UK2Node_IfThenElse* If(UEdGraphPin* Prev,UEdGraphPin* Condition){auto* N=Node<UK2Node_IfThenElse>();N->AllocateDefaultPins();L(Prev,N->GetExecPin());L(Condition,N->GetConditionPin());return N;}
 UEdGraphPin* Valid(UEdGraphPin* Object){auto* N=Call(UKismetSystemLibrary::StaticClass(),TEXT("IsValid"));L(Object,P(N,TEXT("Object")));return P(N,TEXT("ReturnValue"));}
 UEdGraphPin* Text(UEdGraphPin* Prev,FString Widget,UEdGraphPin* Value){auto* N=Call(UTextBlock::StaticClass(),TEXT("SetText"));L(Get(Widget),P(N,TEXT("self")));L(Value,P(N,TEXT("InText")));return Exec(Prev,N);}
 UEdGraphPin* Image(UEdGraphPin* Prev,FString Widget,UEdGraphPin* Value){auto* N=Call(UImage::StaticClass(),TEXT("SetBrushFromTexture"));L(Get(Widget),P(N,TEXT("self")));L(Value,P(N,TEXT("Texture")));auto* Show=Call(UWidget::StaticClass(),TEXT("SetVisibility"));L(Get(Widget),P(Show,TEXT("self")));D(Show,TEXT("InVisibility"),TEXT("Visible"));return Exec(Exec(Prev,N),Show);}
 void Click(FString Widget,const TCHAR* Function,int Index=-1){auto* Property=FindFProperty<FObjectProperty>(BP->SkeletonGeneratedClass,*Widget);check(Property);auto* Delegate=FindFProperty<FMulticastDelegateProperty>(UButton::StaticClass(),TEXT("OnClicked"));auto* E=Node<UK2Node_ComponentBoundEvent>();E->InitializeComponentBoundEventParams(Property,Delegate);E->AllocateDefaultPins();auto* N=Call(BP->SkeletonGeneratedClass,Function);if(Index>=0)D(N,TEXT("Index"),FString::FromInt(Index));Exec(P(E,TEXT("then")),N);}
};
UBlueprint* Plain(const FString& Path,UClass* Parent){return FKismetEditorUtilities::CreateBlueprint(Parent,CreatePackage(*Path),*FPackageName::GetLongPackageAssetName(Path),BPTYPE_Normal,UBlueprint::StaticClass(),UBlueprintGeneratedClass::StaticClass());}
FLinearColor Hex(const TCHAR* S){return FLinearColor(FColor::FromHex(S));}
}

UBlueprint* UPTSTemplateBuilder::BuildItemTemplate(const FString& Path)
{
 auto* BP=Plain(Path,UPrimaryDataAsset::StaticClass());G B(BP);
 B.Var(TEXT("ItemId"),UEdGraphSchema_K2::PC_String);B.Var(TEXT("DisplayName"),UEdGraphSchema_K2::PC_Text);B.Var(TEXT("Description"),UEdGraphSchema_K2::PC_Text);
 B.Var(TEXT("Icon"),UEdGraphSchema_K2::PC_Object,UTexture2D::StaticClass());B.Var(TEXT("Model"),UEdGraphSchema_K2::PC_Object,UStaticMesh::StaticClass());
 B.Var(TEXT("PickupClass"),UEdGraphSchema_K2::PC_Class,AActor::StaticClass());B.Var(TEXT("MaxStack"),UEdGraphSchema_K2::PC_Int,nullptr,TEXT("99"));B.Compile();BP->MarkPackageDirty();return BP;
}

UBlueprint* UPTSTemplateBuilder::BuildItemPickupTemplate(const FString& Path)
{
 auto* Parent=LoadClass<AActor>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSInteraction.BP_PTSInteraction_C"));check(Parent);
 auto* Item=LoadClass<UObject>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameItem.BP_PTSGameItem_C"));check(Item);
 auto* BP=Plain(Path,Parent);G B(BP);B.Var(TEXT("ItemData"),UEdGraphSchema_K2::PC_Object,Item);B.Compile();BP->MarkPackageDirty();return BP;
}

UBlueprint* UPTSTemplateBuilder::BuildUIHostTemplate(const FString& Path,const FString& Kind)
{
 auto* BP=Plain(Path,AActor::StaticClass());G B(BP);
 B.Var(TEXT("FlowId"),UEdGraphSchema_K2::PC_String);
 B.Var(TEXT("WidgetClass"),UEdGraphSchema_K2::PC_Class,UUserWidget::StaticClass());
 B.Var(TEXT("WidgetRef"),UEdGraphSchema_K2::PC_Object,UUserWidget::StaticClass());
 B.Var(TEXT("DemoInput"),UEdGraphSchema_K2::PC_Boolean,nullptr,TEXT("true"));
 auto* Toggle=B.Event(TEXT("Toggle"));auto* Show=B.Event(TEXT("Show"));auto* Hide=B.Event(TEXT("Hide"));B.Compile();
 auto* Player=B.Call(UGameplayStatics::StaticClass(),TEXT("GetPlayerController"));auto* PC=B.P(Player,TEXT("ReturnValue"));
 auto* Create=B.Call(UWidgetBlueprintLibrary::StaticClass(),TEXT("Create"));B.L(B.Get(TEXT("WidgetClass")),B.P(Create,TEXT("WidgetType")));B.L(PC,B.P(Create,TEXT("OwningPlayer")));
 auto* Guard=B.If(B.P(Show,TEXT("then")),B.Valid(B.Get(TEXT("WidgetRef"))));
 auto* InViewport=B.Call(UUserWidget::StaticClass(),TEXT("IsInViewport"));B.L(B.Get(TEXT("WidgetRef")),B.P(InViewport,TEXT("self")));
 auto* Visible=B.If(Guard->GetThenPin(),B.P(InViewport,TEXT("ReturnValue")));
 auto* Add=B.Call(UUserWidget::StaticClass(),TEXT("AddToViewport"));B.L(B.Get(TEXT("WidgetRef")),B.P(Add,TEXT("self")));B.Exec(Visible->GetElsePin(),Add);
 auto* Set=B.Set(TEXT("WidgetRef"));B.L(B.P(Create,TEXT("ReturnValue")),B.P(Set,TEXT("WidgetRef")));B.Exec(Guard->GetElsePin(),Create);B.Exec(B.P(Create,TEXT("then")),Set);B.Exec(B.P(Set,TEXT("then")),Add);
 auto* Prev=B.P(Add,TEXT("then"));
 if(Kind!=TEXT("hud")){
  auto* Mode=B.Call(UWidgetBlueprintLibrary::StaticClass(),TEXT("SetInputMode_GameAndUIEx"));B.L(PC,B.P(Mode,TEXT("PlayerController")));B.L(B.Get(TEXT("WidgetRef")),B.P(Mode,TEXT("InWidgetToFocus")));Prev=B.Exec(Prev,Mode);
  auto* Cursor=B.Node<UK2Node_VariableSet>();Cursor->VariableReference.SetExternalMember(TEXT("bShowMouseCursor"),APlayerController::StaticClass());Cursor->AllocateDefaultPins();B.L(PC,B.P(Cursor,TEXT("self")));B.D(Cursor,TEXT("bShowMouseCursor"),TEXT("true"));Prev=B.Exec(Prev,Cursor);
 }
 if(Kind==TEXT("pause")){auto* Pause=B.Call(UGameplayStatics::StaticClass(),TEXT("SetGamePaused"));B.D(Pause,TEXT("bPaused"),TEXT("true"));B.Exec(Prev,Pause);}
 auto* Has=B.If(B.P(Toggle,TEXT("then")),B.Valid(B.Get(TEXT("WidgetRef"))));
 auto* TVisible=B.If(Has->GetThenPin(),B.P(InViewport,TEXT("ReturnValue")));B.Exec(TVisible->GetThenPin(),B.Call(BP->SkeletonGeneratedClass,TEXT("Hide")));auto* ShowCall=B.Call(BP->SkeletonGeneratedClass,TEXT("Show"));B.Exec(TVisible->GetElsePin(),ShowCall);B.Exec(Has->GetElsePin(),ShowCall);
 auto* H=B.If(B.P(Hide,TEXT("then")),B.Valid(B.Get(TEXT("WidgetRef"))));auto* Remove=B.Call(UWidget::StaticClass(),TEXT("RemoveFromParent"));B.L(B.Get(TEXT("WidgetRef")),B.P(Remove,TEXT("self")));Prev=B.Exec(H->GetThenPin(),Remove);
 if(Kind==TEXT("pause")){auto* Pause=B.Call(UGameplayStatics::StaticClass(),TEXT("SetGamePaused"));B.D(Pause,TEXT("bPaused"),TEXT("false"));Prev=B.Exec(Prev,Pause);}
 if(Kind!=TEXT("hud")){
  auto* Mode=B.Call(UWidgetBlueprintLibrary::StaticClass(),TEXT("SetInputMode_GameOnly"));B.L(PC,B.P(Mode,TEXT("PlayerController")));Prev=B.Exec(Prev,Mode);
  auto* Cursor=B.Node<UK2Node_VariableSet>();Cursor->VariableReference.SetExternalMember(TEXT("bShowMouseCursor"),APlayerController::StaticClass());Cursor->AllocateDefaultPins();B.L(PC,B.P(Cursor,TEXT("self")));B.D(Cursor,TEXT("bShowMouseCursor"),TEXT("false"));B.Exec(Prev,Cursor);
 }
 if(Kind==TEXT("hud")){
  auto* Begin=B.Node<UK2Node_Event>();Begin->EventReference.SetExternalMember(TEXT("ReceiveBeginPlay"),AActor::StaticClass());Begin->bOverrideFunction=true;Begin->AllocateDefaultPins();B.Exec(B.P(Begin,TEXT("then")),B.Call(BP->SkeletonGeneratedClass,TEXT("Show")));
 }else{
  auto* Key=B.Node<UK2Node_InputKey>();Key->InputKey=Kind==TEXT("pause")?EKeys::Escape:EKeys::I;Key->bConsumeInput=false;Key->bExecuteWhenPaused=true;Key->AllocateDefaultPins();auto* Pad=B.Node<UK2Node_InputKey>();Pad->InputKey=Kind==TEXT("pause")?EKeys::Gamepad_Special_Right:EKeys::Gamepad_Special_Left;Pad->bConsumeInput=false;Pad->bExecuteWhenPaused=true;Pad->AllocateDefaultPins();auto* Enabled=B.If(B.P(Key,TEXT("Pressed")),B.Get(TEXT("DemoInput")));B.L(B.P(Pad,TEXT("Pressed")),Enabled->GetExecPin());B.Exec(Enabled->GetThenPin(),B.Call(BP->SkeletonGeneratedClass,TEXT("Toggle")));
 }
 B.Compile();CastChecked<AActor>(BP->GeneratedClass->GetDefaultObject())->AutoReceiveInput=EAutoReceiveInput::Player0;BP->MarkPackageDirty();return BP;
}
