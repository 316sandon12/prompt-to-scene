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

UBlueprint* UPTSTemplateBuilder::BuildGameUITemplate(const FString& Path,const FString& Kind)
{
 auto* ItemClass=LoadObject<UClass>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameItem.BP_PTSGameItem_C"));check(ItemClass);
 auto* BP=CastChecked<UWidgetBlueprint>(FKismetEditorUtilities::CreateBlueprint(UUserWidget::StaticClass(),CreatePackage(*Path),*FPackageName::GetLongPackageAssetName(Path),BPTYPE_Normal,UWidgetBlueprint::StaticClass(),UWidgetBlueprintGeneratedClass::StaticClass()));
 BP->WidgetTree=NewObject<UWidgetTree>(BP,TEXT("WidgetTree"),RF_Transactional);auto* T=BP->WidgetTree.Get();
 auto* Canvas=T->ConstructWidget<UCanvasPanel>();T->RootWidget=Canvas;
 auto* Border=T->ConstructWidget<UBorder>(UBorder::StaticClass(),TEXT("Panel"));Border->bIsVariable=true;Border->SetBrushColor(Hex(TEXT("182521")));Border->SetPadding(FMargin(Kind==TEXT("hud")?16:32));
 auto* PanelSlot=Canvas->AddChildToCanvas(Border);PanelSlot->SetAnchors(Kind==TEXT("hud")?FAnchors(.03f,.74f,.44f,.96f):FAnchors(.12f,.12f,.88f,.88f));PanelSlot->SetOffsets(FMargin(0));
 auto* Main=T->ConstructWidget<UVerticalBox>();Border->AddChild(Main);
 auto Text=[&](FString Name,FString Value,int Size=22,FLinearColor Color=FLinearColor(.9,.87,.75)){
  auto* W=T->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(),*Name);W->bIsVariable=true;W->SetText(FText::FromString(Value));W->SetAutoWrapText(true);auto Font=W->GetFont();Font.Size=Size;W->SetFont(Font);W->SetColorAndOpacity(FSlateColor(Color));return W;};
 auto Button=[&](FString Name,FString Title){auto* W=T->ConstructWidget<UButton>(UButton::StaticClass(),*Name);W->bIsVariable=true;W->SetBackgroundColor(Hex(TEXT("283D32")));if(!Title.IsEmpty())W->AddChild(Text(Name+TEXT("Label"),Title));return W;};
 auto Image=[&](FString Name){auto* W=T->ConstructWidget<UImage>(UImage::StaticClass(),*Name);W->bIsVariable=true;W->SetDesiredSizeOverride(FVector2D(86,86));W->SetVisibility(ESlateVisibility::Hidden);return W;};
 auto* Header=T->ConstructWidget<UHorizontalBox>();Main->AddChildToVerticalBox(Header)->SetPadding(FMargin(0,0,0,Kind==TEXT("hud")?8:24));
 auto* Title=Text(TEXT("Title"),Kind==TEXT("inventory")?TEXT("SATCHEL"):Kind==TEXT("pause")?TEXT("PAUSED"):TEXT("ADVENTURER"),Kind==TEXT("hud")?18:30);
 Header->AddChildToHorizontalBox(Title)->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
 if(Kind!=TEXT("hud"))Header->AddChildToHorizontalBox(Button(TEXT("Close"),TEXT("×")));
 auto* Body=T->ConstructWidget<UHorizontalBox>();Main->AddChildToVerticalBox(Body)->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
 int Count=Kind==TEXT("inventory")?16:Kind==TEXT("hud")?4:0;
 if(Kind==TEXT("inventory"))
 {
  auto* Grid=T->ConstructWidget<UUniformGridPanel>();Grid->SetSlotPadding(FMargin(6));Body->AddChildToHorizontalBox(Grid)->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
  for(int i=0;i<16;i++){auto* W=Button(FString::Printf(TEXT("Slot%d"),i),TEXT(""));auto* Size=T->ConstructWidget<USizeBox>();Size->SetMinDesiredWidth(100);Size->SetMinDesiredHeight(100);W->AddChild(Size);Size->AddChild(Image(FString::Printf(TEXT("Icon%d"),i)));Grid->AddChildToUniformGrid(W,i/4,i%4);}
  auto* Details=T->ConstructWidget<UVerticalBox>();auto* S=Body->AddChildToHorizontalBox(Details);S->SetSize(FSlateChildSize(ESlateSizeRule::Fill));S->SetPadding(FMargin(32,0,0,0));
  // DesiredSizeOverride on UImage is transient. Serialize the square layout in a SizeBox.
  auto* DetailSize=T->ConstructWidget<USizeBox>();DetailSize->SetWidthOverride(200);DetailSize->SetHeightOverride(200);
  DetailSize->AddChild(Image(TEXT("DetailIcon")));Details->AddChildToVerticalBox(DetailSize)->SetHorizontalAlignment(HAlign_Center);
  Details->AddChildToVerticalBox(Text(TEXT("DetailName"),TEXT("Select an item"),26))->SetPadding(FMargin(0,20));
  Details->AddChildToVerticalBox(Text(TEXT("DetailDescription"),TEXT("A place for every discovery.")));
 }
 else if(Kind==TEXT("hud"))
 {
  auto* Health=T->ConstructWidget<UProgressBar>(UProgressBar::StaticClass(),TEXT("Health"));Health->bIsVariable=true;Health->SetPercent(1);Health->SetFillColorAndOpacity(Hex(TEXT("D4BB7B")));
  auto* HealthSize=T->ConstructWidget<USizeBox>();HealthSize->SetHeightOverride(10);HealthSize->AddChild(Health);Main->InsertChildAt(1,HealthSize);
  for(int i=0;i<4;i++){auto* Size=T->ConstructWidget<USizeBox>();Size->SetWidthOverride(48);Size->SetHeightOverride(48);Size->AddChild(Image(FString::Printf(TEXT("Icon%d"),i)));auto* Slot=Body->AddChildToHorizontalBox(Size);Slot->SetPadding(FMargin(6,8,6,0));Slot->SetVerticalAlignment(VAlign_Center);}
 }
 else
 {
  auto* Menu=T->ConstructWidget<UVerticalBox>();Body->AddChildToHorizontalBox(Menu)->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
  Menu->AddChildToVerticalBox(Text(TEXT("PauseHint"),TEXT("Take a breath. Your journey will wait.")))->SetPadding(FMargin(20));
  Menu->AddChildToVerticalBox(Button(TEXT("ResumeButton"),TEXT("Resume")))->SetPadding(FMargin(20));
  Menu->AddChildToVerticalBox(Button(TEXT("SettingsButton"),TEXT("Settings")))->SetPadding(FMargin(20));
 }
 G B(BP);for(int i=0;i<Count;i++)B.Var(FString::Printf(TEXT("Item%d"),i),UEdGraphSchema_K2::PC_Object,ItemClass);
 auto* Refresh=B.Event(TEXT("RefreshItems"));auto* Select=B.Event(TEXT("SelectItem"));auto* Index=B.Param(Select,TEXT("Index"),UEdGraphSchema_K2::PC_Int);
 auto* Selected=B.Event(TEXT("OnItemSelected"));B.Param(Selected,TEXT("ItemId"),UEdGraphSchema_K2::PC_String);
 auto* Resume=B.Event(TEXT("Resume"));B.Event(TEXT("OnResume"));B.Event(TEXT("OnSettings"));
 auto* Skill=B.Event(TEXT("SetSkillIcon"));auto* SkillIndex=B.Param(Skill,TEXT("Index"),UEdGraphSchema_K2::PC_Int);auto* SkillTexture=B.Param(Skill,TEXT("Texture"),UEdGraphSchema_K2::PC_Object,UTexture2D::StaticClass());
 auto* Health=B.Event(TEXT("SetHealth"));auto* Percent=B.Param(Health,TEXT("Percent"),UEdGraphSchema_K2::PC_Real);
 B.Compile();
 if(Count){auto* Sequence=B.Node<UK2Node_ExecutionSequence>();Sequence->AllocateDefaultPins();for(int i=2;i<Count;i++)Sequence->AddInputPin();B.L(B.P(Refresh,TEXT("then")),B.P(Sequence,TEXT("execute")));
  for(int i=0;i<Count;i++){auto* Item=B.Get(FString::Printf(TEXT("Item%d"),i));auto* Guard=B.If(B.P(Sequence,*FString::Printf(TEXT("Then_%d"),i)),B.Valid(Item));B.Image(Guard->GetThenPin(),FString::Printf(TEXT("Icon%d"),i),B.Field(TEXT("Icon"),ItemClass,Item));}
 }
 if(Kind==TEXT("inventory")){auto* Sequence=B.Node<UK2Node_ExecutionSequence>();Sequence->AllocateDefaultPins();for(int i=2;i<Count;i++)Sequence->AddInputPin();B.L(B.P(Select,TEXT("then")),B.P(Sequence,TEXT("execute")));
  for(int i=0;i<Count;i++){auto* Equal=B.Call(UKismetMathLibrary::StaticClass(),TEXT("EqualEqual_IntInt"));B.L(Index,B.P(Equal,TEXT("A")));B.D(Equal,TEXT("B"),FString::FromInt(i));auto* Guard=B.If(B.P(Sequence,*FString::Printf(TEXT("Then_%d"),i)),B.P(Equal,TEXT("ReturnValue")));auto* Item=B.Get(FString::Printf(TEXT("Item%d"),i));auto* Valid=B.If(Guard->GetThenPin(),B.Valid(Item));auto* Prev=B.Text(Valid->GetThenPin(),TEXT("DetailName"),B.Field(TEXT("DisplayName"),ItemClass,Item));Prev=B.Text(Prev,TEXT("DetailDescription"),B.Field(TEXT("Description"),ItemClass,Item));Prev=B.Image(Prev,TEXT("DetailIcon"),B.Field(TEXT("Icon"),ItemClass,Item));auto* Hook=B.Call(BP->SkeletonGeneratedClass,TEXT("OnItemSelected"));B.L(B.Field(TEXT("ItemId"),ItemClass,Item),B.P(Hook,TEXT("ItemId")));B.Exec(Prev,Hook);B.Click(FString::Printf(TEXT("Slot%d"),i),TEXT("SelectItem"),i);}
 }
 auto* Construct=B.Node<UK2Node_Event>();Construct->EventReference.SetExternalMember(TEXT("Construct"),UUserWidget::StaticClass());Construct->bOverrideFunction=true;Construct->AllocateDefaultPins();B.Exec(B.P(Construct,TEXT("then")),B.Call(BP->SkeletonGeneratedClass,TEXT("RefreshItems")));
 auto* Remove=B.Call(UUserWidget::StaticClass(),TEXT("RemoveFromParent"));auto* Prev=B.Exec(B.P(Resume,TEXT("then")),Remove);
 if(Kind==TEXT("pause")){auto* Pause=B.Call(UGameplayStatics::StaticClass(),TEXT("SetGamePaused"));B.D(Pause,TEXT("bPaused"),TEXT("false"));Prev=B.Exec(Prev,Pause);B.Click(TEXT("ResumeButton"),TEXT("Resume"));B.Click(TEXT("SettingsButton"),TEXT("OnSettings"));}
 if(Kind!=TEXT("hud")){
  auto* Owner=B.Call(UUserWidget::StaticClass(),TEXT("GetOwningPlayer"));auto* PC=B.P(Owner,TEXT("ReturnValue"));
  auto* Mode=B.Call(UWidgetBlueprintLibrary::StaticClass(),TEXT("SetInputMode_GameOnly"));B.L(PC,B.P(Mode,TEXT("PlayerController")));Prev=B.Exec(Prev,Mode);
  auto* Cursor=B.Node<UK2Node_VariableSet>();Cursor->VariableReference.SetExternalMember(TEXT("bShowMouseCursor"),APlayerController::StaticClass());Cursor->AllocateDefaultPins();B.L(PC,B.P(Cursor,TEXT("self")));B.D(Cursor,TEXT("bShowMouseCursor"),TEXT("false"));Prev=B.Exec(Prev,Cursor);
 }
 B.Exec(Prev,B.Call(BP->SkeletonGeneratedClass,TEXT("OnResume")));if(Kind!=TEXT("hud"))B.Click(TEXT("Close"),TEXT("Resume"));
 if(Kind==TEXT("hud")){
  auto* Sequence=B.Node<UK2Node_ExecutionSequence>();Sequence->AllocateDefaultPins();Sequence->AddInputPin();Sequence->AddInputPin();B.L(B.P(Skill,TEXT("then")),B.P(Sequence,TEXT("execute")));
  for(int i=0;i<4;i++){auto* Eq=B.Call(UKismetMathLibrary::StaticClass(),TEXT("EqualEqual_IntInt"));B.L(SkillIndex,B.P(Eq,TEXT("A")));B.D(Eq,TEXT("B"),FString::FromInt(i));auto* Guard=B.If(B.P(Sequence,*FString::Printf(TEXT("Then_%d"),i)),B.P(Eq,TEXT("ReturnValue")));B.Image(Guard->GetThenPin(),FString::Printf(TEXT("Icon%d"),i),SkillTexture);}
 }
 if(Kind==TEXT("hud")){auto* Set=B.Call(UProgressBar::StaticClass(),TEXT("SetPercent"));B.L(B.Get(TEXT("Health")),B.P(Set,TEXT("self")));B.L(Percent,B.P(Set,TEXT("InPercent")));B.Exec(B.P(Health,TEXT("then")),Set);}
 B.Compile();BP->MarkPackageDirty();return BP;
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
  auto* Key=B.Node<UK2Node_InputKey>();Key->InputKey=Kind==TEXT("pause")?EKeys::Escape:EKeys::I;Key->bConsumeInput=false;Key->bExecuteWhenPaused=true;Key->AllocateDefaultPins();auto* Enabled=B.If(B.P(Key,TEXT("Pressed")),B.Get(TEXT("DemoInput")));B.Exec(Enabled->GetThenPin(),B.Call(BP->SkeletonGeneratedClass,TEXT("Toggle")));
 }
 B.Compile();CastChecked<AActor>(BP->GeneratedClass->GetDefaultObject())->AutoReceiveInput=EAutoReceiveInput::Player0;BP->MarkPackageDirty();return BP;
}
