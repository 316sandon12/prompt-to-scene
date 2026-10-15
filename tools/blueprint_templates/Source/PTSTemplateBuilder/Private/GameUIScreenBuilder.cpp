#include "PTSTemplateBuilder.h"
#include "GameFlowGraph.h"
#include "WidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetBlueprintGeneratedClass.h"
#include "Blueprint/WidgetBlueprintLibrary.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/SafeZone.h"
#include "Components/ScrollBox.h"
#include "Components/WrapBox.h"
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
#include "Engine/Texture2D.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetTextLibrary.h"
#include "Kismet/KismetStringLibrary.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_ExecutionSequence.h"

using namespace PTSGraph;
namespace {
struct FlowUI : G {
 FlowUI(UBlueprint* BP,UEdGraph* Graph):G(BP,Graph){}
 UEdGraphPin* Text(UEdGraphPin* Prev,const TCHAR* Widget,UEdGraphPin* Value){auto* N=Call(UTextBlock::StaticClass(),TEXT("SetText"));L(Get(Widget),P(N,TEXT("self")));L(Value,P(N,TEXT("InText")));return Exec(Prev,N);}
 UEdGraphPin* ToText(UEdGraphPin* Value,bool Integer=false){auto* N=Call(UKismetTextLibrary::StaticClass(),Integer?TEXT("Conv_IntToText"):TEXT("Conv_StringToText"));L(Value,P(N,Integer?TEXT("Value"):TEXT("InString")));return Out(N);}
 UEdGraphPin* Enabled(UEdGraphPin* Prev,const TCHAR* Widget,UEdGraphPin* Value){auto* N=Call(UWidget::StaticClass(),TEXT("SetIsEnabled"));L(Get(Widget),P(N,TEXT("self")));L(Value,P(N,TEXT("bInIsEnabled")));return Exec(Prev,N);}
 UEdGraphPin* Image(UEdGraphPin* Prev,const TCHAR* Widget,UEdGraphPin* Value){auto* N=Call(UImage::StaticClass(),TEXT("SetBrushFromTexture"));L(Get(Widget),P(N,TEXT("self")));L(Value,P(N,TEXT("Texture")));return Exec(Prev,N);}
 UEdGraphPin* Visible(UEdGraphPin* Prev,const TCHAR* Widget,bool Show){auto* N=Call(UWidget::StaticClass(),TEXT("SetVisibility"));L(Get(Widget),P(N,TEXT("self")));D(N,TEXT("InVisibility"),Show?TEXT("Visible"):TEXT("Hidden"));return Exec(Prev,N);}
 UEdGraphPin* Collapse(UEdGraphPin* Prev,const TCHAR* Widget){auto* N=Call(UWidget::StaticClass(),TEXT("SetVisibility"));L(Get(Widget),P(N,TEXT("self")));D(N,TEXT("InVisibility"),TEXT("Collapsed"));return Exec(Prev,N);}
 UEdGraphPin* PageText(const TCHAR* Name,UEdGraphPin* Count,int Size){auto* First=Call(UKismetStringLibrary::StaticClass(),TEXT("BuildString_Int"));L(Math(TEXT("Add_IntInt"),Get(Name),Num(1)),P(First,TEXT("InInt")));D(First,TEXT("Suffix"),TEXT(" / "));auto* Last=Call(UKismetStringLibrary::StaticClass(),TEXT("BuildString_Int"));L(Out(First),P(Last,TEXT("AppendTo")));L(Math(TEXT("Max"),Num(1),Math(TEXT("Divide_IntInt"),Math(TEXT("Add_IntInt"),Count,Num(Size-1)),Num(Size))),P(Last,TEXT("InInt")));return ToText(Out(Last));}
 UEdGraphPin* Tip(UEdGraphPin* Prev,const TCHAR* Widget,UEdGraphPin* Value){auto* N=Call(UWidget::StaticClass(),TEXT("SetToolTipText"));L(Get(Widget),P(N,TEXT("self")));L(Value,P(N,TEXT("InToolTipText")));return Exec(Prev,N);}
 UEdGraphPin* Session(const TCHAR* Function){auto* C=LoadClass<AActor>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameSession.BP_PTSGameSession_C"));return Field(C,Get(TEXT("FlowSession")),Function);}
 UEdGraphPin* RuleCall(UEdGraphPin* Prev,const TCHAR* Function,UEdGraphPin* Id,UK2Node_CallFunction*& N){auto* C=LoadClass<AActor>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameSession.BP_PTSGameSession_C"));N=Call(C,Function);L(Get(TEXT("FlowSession")),P(N,TEXT("self")));L(Id,P(N,TEXT("RuleId")));return Exec(Prev,N);}
 void Click(const TCHAR* Widget,const TCHAR* Function,int Index=-1,const TCHAR* DelegateName=TEXT("OnClicked")){auto* Prop=FindFProperty<FObjectProperty>(BP->SkeletonGeneratedClass,Widget);check(Prop);auto* Delegate=FindFProperty<FMulticastDelegateProperty>(UButton::StaticClass(),DelegateName);auto* E=Node<UK2Node_ComponentBoundEvent>();E->InitializeComponentBoundEventParams(Prop,Delegate);E->AllocateDefaultPins();auto* N=Call(BP->SkeletonGeneratedClass,Function);if(Index>=0)D(N,TEXT("Index"),FString::FromInt(Index));Exec(P(E,TEXT("then")),N);}
};
}

UBlueprint* UPTSTemplateBuilder::BuildGameUITemplate(const FString& Path,const FString& Kind)
{
 auto* ItemClass=LoadClass<UObject>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameItem.BP_PTSGameItem_C"));check(ItemClass);
 auto* SessionClass=LoadClass<AActor>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameSession.BP_PTSGameSession_C"));check(SessionClass);
 auto* RuleClass=LoadClass<UObject>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameRule.BP_PTSGameRule_C"));check(RuleClass);
 auto* BP=CastChecked<UWidgetBlueprint>(FKismetEditorUtilities::CreateBlueprint(UUserWidget::StaticClass(),CreatePackage(*Path),*FPackageName::GetLongPackageAssetName(Path),BPTYPE_Normal,UWidgetBlueprint::StaticClass(),UWidgetBlueprintGeneratedClass::StaticClass()));
 BP->WidgetTree=NewObject<UWidgetTree>(BP,TEXT("WidgetTree"),RF_Transactional);auto* T=BP->WidgetTree.Get();
 auto* Canvas=T->ConstructWidget<UCanvasPanel>();T->RootWidget=Canvas;
 auto* Safe=T->ConstructWidget<USafeZone>();auto* SafeSlot=Canvas->AddChildToCanvas(Safe);SafeSlot->SetAnchors(FAnchors(0,0,1,1));SafeSlot->SetOffsets(FMargin(0));
 auto* Inner=T->ConstructWidget<UCanvasPanel>();Safe->AddChild(Inner);
 auto* Panel=T->ConstructWidget<UBorder>(UBorder::StaticClass(),TEXT("Panel"));Panel->bIsVariable=true;Panel->SetBrushColor(FLinearColor(.009,.019,.014, .98));Panel->SetPadding(FMargin(20));
 auto* Slot=Inner->AddChildToCanvas(Panel);Slot->SetAnchors(Kind==TEXT("hud")?FAnchors(.03,.74,.48,.97):FAnchors(.06,.06,.94,.94));Slot->SetOffsets(FMargin(0));
 auto* Main=T->ConstructWidget<UVerticalBox>();Panel->AddChild(Main);
 auto Text=[&](FString Name,FString Value,int Size=18){auto* W=T->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(),*Name);W->bIsVariable=true;W->SetText(FText::FromString(Value));W->SetAutoWrapText(true);auto Font=W->GetFont();Font.Size=Size;W->SetFont(Font);W->SetColorAndOpacity(FSlateColor(FLinearColor(.82,.76,.59)));return W;};
 auto Button=[&](FString Name,FString Label){auto* W=T->ConstructWidget<UButton>(UButton::StaticClass(),*Name);W->bIsVariable=true;W->SetBackgroundColor(FLinearColor(.025,.07,.045));if(!Label.IsEmpty())W->AddChild(Text(Name+TEXT("Label"),Label));return W;};
 auto Image=[&](FString Name,int Size){auto* Box=T->ConstructWidget<USizeBox>();Box->SetWidthOverride(Size);Box->SetHeightOverride(Size);auto* W=T->ConstructWidget<UImage>(UImage::StaticClass(),*Name);W->bIsVariable=true;Box->AddChild(W);return Box;};
 auto* Header=T->ConstructWidget<UHorizontalBox>();Main->AddChildToVerticalBox(Header)->SetPadding(FMargin(0,0,0,16));
 Header->AddChildToHorizontalBox(Text(TEXT("Title"),Kind==TEXT("inventory")?TEXT("SATCHEL"):Kind==TEXT("hud")?TEXT("ADVENTURER"):TEXT("PAUSED"),26))->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
 if(Kind!=TEXT("hud"))Header->AddChildToHorizontalBox(Button(TEXT("Close"),TEXT("×")));
 int Count=Kind==TEXT("inventory")?16:Kind==TEXT("hud")?4:0;
 if(Kind==TEXT("inventory")){
  // Wrap into a vertical, scrollable layout on narrow displays; retain readable controls.
  auto* Scroll=T->ConstructWidget<UScrollBox>();Main->AddChildToVerticalBox(Scroll)->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
  auto* Wrap=T->ConstructWidget<UWrapBox>();Wrap->SetInnerSlotPadding(FVector2D(22,16));Wrap->SetHorizontalAlignment(HAlign_Center);Scroll->AddChild(Wrap);
  auto* Grid=T->ConstructWidget<UUniformGridPanel>();Grid->SetSlotPadding(FMargin(4));Wrap->AddChildToWrapBox(Grid);
  for(int i=0;i<Count;i++){auto* W=Button(FString::Printf(TEXT("Slot%d"),i),TEXT(""));auto* Cell=T->ConstructWidget<UVerticalBox>();W->AddChild(Cell);Cell->AddChildToVerticalBox(Image(FString::Printf(TEXT("Icon%d"),i),72));Cell->AddChildToVerticalBox(Text(FString::Printf(TEXT("Quantity%d"),i),TEXT(""),14));Grid->AddChildToUniformGrid(W,i/4,i%4);}
  auto* DetailBox=T->ConstructWidget<USizeBox>();DetailBox->SetWidthOverride(270);auto* Details=T->ConstructWidget<UVerticalBox>();DetailBox->AddChild(Details);Wrap->AddChildToWrapBox(DetailBox);
  Details->AddChildToVerticalBox(Image(TEXT("DetailIcon"),160))->SetHorizontalAlignment(HAlign_Center);
  Details->AddChildToVerticalBox(Text(TEXT("DetailName"),TEXT("Select an item"),23))->SetPadding(FMargin(0,16));
  Details->AddChildToVerticalBox(Text(TEXT("DetailDescription"),TEXT("Your discoveries and supplies.")));
  Details->AddChildToVerticalBox(Text(TEXT("DetailQuantity"),TEXT("")))->SetPadding(FMargin(0,8));
  Details->AddChildToVerticalBox(Button(TEXT("UseButton"),TEXT("Use item")));
  auto* CraftBox=T->ConstructWidget<USizeBox>(USizeBox::StaticClass(),TEXT("CraftingPanel"));CraftBox->bIsVariable=true;CraftBox->SetVisibility(ESlateVisibility::Collapsed);CraftBox->SetWidthOverride(250);auto* Recipes=T->ConstructWidget<UVerticalBox>();CraftBox->AddChild(Recipes);Wrap->AddChildToWrapBox(CraftBox);
  Recipes->AddChildToVerticalBox(Text(TEXT("CraftTitle"),TEXT("CRAFTING"),22));
  for(int i=0;i<8;i++)Recipes->AddChildToVerticalBox(Button(FString::Printf(TEXT("Craft%d"),i),TEXT("Recipe")))->SetPadding(FMargin(0,4));
  auto* RecipePager=T->ConstructWidget<UHorizontalBox>();Recipes->AddChildToVerticalBox(RecipePager);RecipePager->AddChildToHorizontalBox(Button(TEXT("CraftPrevious"),TEXT("‹")));RecipePager->AddChildToHorizontalBox(Text(TEXT("CraftPageLabel"),TEXT("1")))->SetSize(FSlateChildSize(ESlateSizeRule::Fill));RecipePager->AddChildToHorizontalBox(Button(TEXT("CraftNext"),TEXT("›")));
  Main->AddChildToVerticalBox(Text(TEXT("EmptyLabel"),TEXT("No items yet — collect supplies to begin.")));
  auto* Pager=T->ConstructWidget<UHorizontalBox>();Main->AddChildToVerticalBox(Pager);Pager->AddChildToHorizontalBox(Button(TEXT("Previous"),TEXT("‹ Previous")));Pager->AddChildToHorizontalBox(Text(TEXT("PageLabel"),TEXT("1")))->SetSize(FSlateChildSize(ESlateSizeRule::Fill));Pager->AddChildToHorizontalBox(Button(TEXT("Next"),TEXT("Next ›")));
 }else if(Kind==TEXT("hud")){
  auto* Bar=T->ConstructWidget<UProgressBar>(UProgressBar::StaticClass(),TEXT("Health"));Bar->bIsVariable=true;Bar->SetPercent(1);Bar->SetFillColorAndOpacity(FLinearColor(.65,.49,.2));auto* Box=T->ConstructWidget<USizeBox>();Box->SetHeightOverride(12);Box->AddChild(Bar);Main->AddChildToVerticalBox(Box);
  auto* Row=T->ConstructWidget<UHorizontalBox>();Main->AddChildToVerticalBox(Row);for(int i=0;i<Count;i++)Row->AddChildToHorizontalBox(Image(FString::Printf(TEXT("Icon%d"),i),48))->SetPadding(FMargin(6));
 }else{
  Main->AddChildToVerticalBox(Text(TEXT("PauseHint"),TEXT("Take a breath. Your journey will wait.")))->SetPadding(FMargin(12));
  Main->AddChildToVerticalBox(Button(TEXT("ResumeButton"),TEXT("Resume")))->SetPadding(FMargin(12));Main->AddChildToVerticalBox(Button(TEXT("SettingsButton"),TEXT("Settings")))->SetPadding(FMargin(12));
 }
 Main->AddChildToVerticalBox(Text(TEXT("Feedback"),TEXT(""),16))->SetPadding(FMargin(0,8,0,0));
 Var(BP,TEXT("FlowId"),String());Var(BP,TEXT("FlowSession"),Object(SessionClass));Var(BP,TEXT("Items"),Array(Object(ItemClass)));Var(BP,TEXT("VisibleItems"),Array(Object(ItemClass)));
 Var(BP,TEXT("SelectedItem"),Object(ItemClass));Var(BP,TEXT("Page"),Int(),TEXT("0"));Var(BP,TEXT("CraftPage"),Int(),TEXT("0"));Var(BP,TEXT("RefreshClock"),Float(),TEXT("0"));
 for(int i=0;i<Count;i++)Var(BP,*FString::Printf(TEXT("Item%d"),i),Object(ItemClass));
 auto Refresh=Declare(BP,TEXT("RefreshItems"));auto Paint=Declare(BP,TEXT("PaintItems"));auto Detail=Declare(BP,TEXT("PaintDetails"));
 auto Select=Declare(BP,TEXT("SelectItem"),{{TEXT("Index"),Int()}});auto Use=Declare(BP,TEXT("UseSelected"));auto Craft=Declare(BP,TEXT("CraftItem"),{{TEXT("Index"),Int()}});
 auto Resume=Declare(BP,TEXT("Resume"));Declare(BP,TEXT("OnResume"));Declare(BP,TEXT("OnSettings"));auto Selected=Declare(BP,TEXT("OnItemSelected"),{{TEXT("ItemId"),String()}});
 auto Health=Declare(BP,TEXT("SetHealth"),{{TEXT("Percent"),Float()}});auto Skill=Declare(BP,TEXT("SetSkillIcon"),{{TEXT("Index"),Int()},{TEXT("Texture"),Object(UTexture2D::StaticClass())}});
 TArray<Function> Pages;for(auto Name:{TEXT("NextPage"),TEXT("PreviousPage"),TEXT("NextCraftPage"),TEXT("PreviousCraftPage")})Pages.Add(Declare(BP,Name));
 Compile(BP);
 {
  FlowUI B(BP,Refresh.Graph);auto* All=B.Call(UGameplayStatics::StaticClass(),TEXT("GetAllActorsOfClass"));B.P(All,TEXT("ActorClass"))->DefaultObject=SessionClass;
  auto Loop=B.Each(B.Exec(B.P(Refresh.Entry,TEXT("then")),All),B.P(All,TEXT("OutActors")));auto* Cast=B.Cast(Loop.Body,Loop.Element,SessionClass);
  auto* Match=B.If(Cast->GetValidCastPin(),B.Math(TEXT("EqualEqual_StrStr"),B.Field(SessionClass,Cast->GetCastResultPin(),TEXT("FlowId")),B.Get(TEXT("FlowId"))));B.Assign(Match->GetThenPin(),TEXT("FlowSession"),Cast->GetCastResultPin());
  auto* Has=B.If(Loop.Done,B.Valid(B.Get(TEXT("FlowSession"))));auto* Init=B.Call(SessionClass,TEXT("Initialize"));B.L(B.Get(TEXT("FlowSession")),B.P(Init,TEXT("self")));auto* Sync=B.Call(SessionClass,TEXT("RefreshAdapter"));B.L(B.Get(TEXT("FlowSession")),B.P(Sync,TEXT("self")));auto* Prev=B.Exec(B.Exec(Has->GetThenPin(),Init),Sync);
  auto* Clear=B.Call(UKismetArrayLibrary::StaticClass(),TEXT("Array_Clear"));B.L(B.Get(TEXT("VisibleItems")),B.P(Clear,TEXT("TargetArray")));B.Exec(Has->GetElsePin(),Clear);Prev=B.Exec(Prev,Clear);
  auto Items=B.Each(Prev,B.Get(TEXT("Items")));auto* Valid=B.If(Items.Body,B.Valid(Items.Element));auto* HasFlow=B.If(Valid->GetThenPin(),B.Valid(B.Get(TEXT("FlowSession"))));
  auto* Owned=B.If(HasFlow->GetThenPin(),B.Math(TEXT("Greater_IntInt"),B.Find(B.Session(TEXT("Inventory")),B.Field(ItemClass,Items.Element,TEXT("ItemId"))),B.Num(0)));
  if(Kind==TEXT("inventory"))B.Append(Owned->GetThenPin(),B.Get(TEXT("VisibleItems")),Items.Element);else B.Append(HasFlow->GetThenPin(),B.Get(TEXT("VisibleItems")),Items.Element);
  B.Append(HasFlow->GetElsePin(),B.Get(TEXT("VisibleItems")),Items.Element);
  auto* Clamp=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Clamp"));B.L(B.Get(TEXT("Page")),B.P(Clamp,TEXT("Value")));B.L(B.Math(TEXT("Max"),B.Num(0),B.Math(TEXT("Divide_IntInt"),B.Math(TEXT("Subtract_IntInt"),B.Length(B.Get(TEXT("VisibleItems"))),B.Num(1)),B.Num(16))),B.P(Clamp,TEXT("Max")));
  Prev=B.Assign(Items.Done,TEXT("Page"),B.Out(Clamp));B.Return(Refresh,B.Exec(Prev,B.Call(BP->SkeletonGeneratedClass,TEXT("PaintItems"))));
 }
 {
  FlowUI B(BP,Paint.Graph);auto* Seq=B.Node<UK2Node_ExecutionSequence>();Seq->AllocateDefaultPins();for(int i=2;i<Count+3;i++)Seq->AddInputPin();B.L(B.P(Paint.Entry,TEXT("then")),B.P(Seq,TEXT("execute")));
  for(int i=0;i<Count;i++){
   FString ItemName=FString::Printf(TEXT("Item%d"),i),Icon=FString::Printf(TEXT("Icon%d"),i),ButtonName=FString::Printf(TEXT("Slot%d"),i),Quantity=FString::Printf(TEXT("Quantity%d"),i);
   auto* Offset=B.Math(TEXT("Add_IntInt"),B.Math(TEXT("Multiply_IntInt"),B.Get(TEXT("Page")),B.Num(16)),B.Num(i));auto* InRange=B.If(B.P(Seq,*FString::Printf(TEXT("Then_%d"),i)),B.Math(TEXT("Less_IntInt"),Offset,B.Length(B.Get(TEXT("VisibleItems")))));
   auto* Prev=B.Assign(InRange->GetThenPin(),*ItemName,B.At(B.Get(TEXT("VisibleItems")),Offset));auto* Item=B.Get(*ItemName);Prev=B.Image(Prev,*Icon,B.Field(ItemClass,Item,TEXT("Icon")));Prev=B.Visible(Prev,*Icon,true);
   auto* Clear=B.Set(*ItemName);B.D(Clear,*ItemName,TEXT("None"));auto* Empty=B.Exec(InRange->GetElsePin(),Clear);Empty=B.Visible(Empty,*Icon,false);
   if(Kind==TEXT("inventory")){
    Prev=B.Enabled(Prev,*ButtonName,B.Lit(TEXT("MakeLiteralBool"),TEXT("true")));Prev=B.Tip(Prev,*ButtonName,B.Field(ItemClass,Item,TEXT("Description")));
    auto* Has=B.If(Prev,B.Valid(B.Get(TEXT("FlowSession"))));B.Text(Has->GetThenPin(),*Quantity,B.ToText(B.Find(B.Session(TEXT("Inventory")),B.Field(ItemClass,Item,TEXT("ItemId"))),true));B.Text(Has->GetElsePin(),*Quantity,B.ToText(B.Str(TEXT(""))));
    Empty=B.Enabled(Empty,*ButtonName,B.Lit(TEXT("MakeLiteralBool"),TEXT("false")));B.Text(Empty,*Quantity,B.ToText(B.Str(TEXT(""))));
   }
  }
  auto* Prev=B.P(Seq,*FString::Printf(TEXT("Then_%d"),Count));
  if(Kind==TEXT("inventory")){
   Prev=B.Text(Prev,TEXT("PageLabel"),B.PageText(TEXT("Page"),B.Length(B.Get(TEXT("VisibleItems"))),16));Prev=B.Enabled(Prev,TEXT("Previous"),B.Math(TEXT("Greater_IntInt"),B.Get(TEXT("Page")),B.Num(0)));
   Prev=B.Enabled(Prev,TEXT("Next"),B.Math(TEXT("Less_IntInt"),B.Math(TEXT("Multiply_IntInt"),B.Math(TEXT("Add_IntInt"),B.Get(TEXT("Page")),B.Num(1)),B.Num(16)),B.Length(B.Get(TEXT("VisibleItems")))));
   auto* Empty=B.If(Prev,B.Math(TEXT("EqualEqual_IntInt"),B.Length(B.Get(TEXT("VisibleItems"))),B.Num(0)));B.Visible(Empty->GetThenPin(),TEXT("EmptyLabel"),true);B.Visible(Empty->GetElsePin(),TEXT("EmptyLabel"),false);
   B.Exec(B.P(Seq,*FString::Printf(TEXT("Then_%d"),Count+1)),B.Call(BP->SkeletonGeneratedClass,TEXT("PaintDetails")));
   // Recipe controls use the same native transaction checks as world interactions.
   auto* Has=B.If(B.P(Seq,*FString::Printf(TEXT("Then_%d"),Count+2)),B.Valid(B.Get(TEXT("FlowSession"))));
   auto* Clamp=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Clamp"));B.L(B.Get(TEXT("CraftPage")),B.P(Clamp,TEXT("Value")));B.L(B.Math(TEXT("Max"),B.Num(0),B.Math(TEXT("Divide_IntInt"),B.Math(TEXT("Subtract_IntInt"),B.Length(B.Session(TEXT("CraftRules"))),B.Num(1)),B.Num(8))),B.P(Clamp,TEXT("Max")));
   auto* CraftPrev=B.Assign(B.Visible(Has->GetThenPin(),TEXT("CraftingPanel"),true),TEXT("CraftPage"),B.Out(Clamp));B.Collapse(Has->GetElsePin(),TEXT("CraftingPanel"));CraftPrev=B.Text(CraftPrev,TEXT("CraftPageLabel"),B.PageText(TEXT("CraftPage"),B.Length(B.Session(TEXT("CraftRules"))),8));
   CraftPrev=B.Enabled(CraftPrev,TEXT("CraftPrevious"),B.Math(TEXT("Greater_IntInt"),B.Get(TEXT("CraftPage")),B.Num(0)));CraftPrev=B.Enabled(CraftPrev,TEXT("CraftNext"),B.Math(TEXT("Less_IntInt"),B.Math(TEXT("Multiply_IntInt"),B.Math(TEXT("Add_IntInt"),B.Get(TEXT("CraftPage")),B.Num(1)),B.Num(8)),B.Length(B.Session(TEXT("CraftRules")))));
   auto* Recipes=B.Node<UK2Node_ExecutionSequence>();Recipes->AllocateDefaultPins();for(int i=2;i<9;i++)Recipes->AddInputPin();B.L(CraftPrev,B.P(Recipes,TEXT("execute")));
   for(int i=0;i<8;i++){
    auto Name=FString::Printf(TEXT("Craft%d"),i),Label=Name+TEXT("Label");auto* Offset=B.Math(TEXT("Add_IntInt"),B.Math(TEXT("Multiply_IntInt"),B.Get(TEXT("CraftPage")),B.Num(8)),B.Num(i));auto* Available=B.If(B.P(Recipes,*FString::Printf(TEXT("Then_%d"),i)),B.Math(TEXT("Less_IntInt"),Offset,B.Length(B.Session(TEXT("CraftRules")))));
    auto* Id=B.At(B.Session(TEXT("CraftRules")),Offset);auto* Rule=B.Find(B.Session(TEXT("Rules")),Id);auto* P=B.Text(B.Visible(Available->GetThenPin(),*Name,true),*Label,B.ToText(B.Field(RuleClass,Rule,TEXT("Label"))));UK2Node_CallFunction* Can;P=B.RuleCall(P,TEXT("CanRule"),Id,Can);P=B.Enabled(P,*Name,B.P(Can,TEXT("Allowed")));B.Tip(P,*Name,B.ToText(B.Session(TEXT("FailureReason"))));B.Collapse(Available->GetElsePin(),*Name);
   }
   Prev=B.P(Recipes,TEXT("Then_8"));
  }
  auto* Has=B.If(Prev,B.Valid(B.Get(TEXT("FlowSession"))));auto* Join=B.Call(UKismetStringLibrary::StaticClass(),TEXT("Concat_StrStr"));B.L(B.Session(TEXT("LastMessage")),B.P(Join,TEXT("A")));B.L(B.Session(TEXT("SaveError")),B.P(Join,TEXT("B")));auto* P=B.Text(Has->GetThenPin(),TEXT("Feedback"),B.ToText(B.Out(Join)));
  if(Kind==TEXT("hud")){auto* Set=B.Call(UProgressBar::StaticClass(),TEXT("SetPercent"));B.L(B.Get(TEXT("Health")),B.P(Set,TEXT("self")));B.L(B.Math(TEXT("Divide_DoubleDouble"),B.Session(TEXT("Health")),B.Session(TEXT("MaxHealth"))),B.P(Set,TEXT("InPercent")));B.Exec(P,Set);}
 }
 if(Kind==TEXT("inventory")){
  FlowUI B(BP,Detail.Graph);auto* Valid=B.If(B.P(Detail.Entry,TEXT("then")),B.Valid(B.Get(TEXT("SelectedItem"))));auto* Item=B.Get(TEXT("SelectedItem"));auto* P=B.Text(Valid->GetThenPin(),TEXT("DetailName"),B.Field(ItemClass,Item,TEXT("DisplayName")));P=B.Text(P,TEXT("DetailDescription"),B.Field(ItemClass,Item,TEXT("Description")));P=B.Image(P,TEXT("DetailIcon"),B.Field(ItemClass,Item,TEXT("Icon")));
  auto* Has=B.If(P,B.Valid(B.Get(TEXT("FlowSession"))));P=B.Text(Has->GetThenPin(),TEXT("DetailQuantity"),B.ToText(B.Find(B.Session(TEXT("Inventory")),B.Field(ItemClass,Item,TEXT("ItemId"))),true));
  auto* Id=B.Find(B.Session(TEXT("UseRules")),B.Field(ItemClass,Item,TEXT("ItemId")));UK2Node_CallFunction* Can;P=B.RuleCall(P,TEXT("CanRule"),Id,Can);P=B.Enabled(P,TEXT("UseButton"),B.P(Can,TEXT("Allowed")));B.Tip(P,TEXT("UseButton"),B.ToText(B.Session(TEXT("FailureReason"))));
  B.Enabled(Has->GetElsePin(),TEXT("UseButton"),B.Lit(TEXT("MakeLiteralBool"),TEXT("false")));B.Enabled(Valid->GetElsePin(),TEXT("UseButton"),B.Lit(TEXT("MakeLiteralBool"),TEXT("false")));
  FlowUI S(BP,Select.Graph);auto* Prev=S.P(Select.Entry,TEXT("then"));for(int i=0;i<Count;i++){auto* Match=S.If(Prev,S.Math(TEXT("EqualEqual_IntInt"),S.P(Select.Entry,TEXT("Index")),S.Num(i)));auto* Good=S.If(Match->GetThenPin(),S.Valid(S.Get(*FString::Printf(TEXT("Item%d"),i))));auto* P=S.Assign(Good->GetThenPin(),TEXT("SelectedItem"),S.Get(*FString::Printf(TEXT("Item%d"),i)));P=S.Exec(P,S.Call(BP->SkeletonGeneratedClass,TEXT("PaintDetails")));auto* Hook=S.Call(BP->SkeletonGeneratedClass,TEXT("OnItemSelected"));S.L(S.Field(ItemClass,S.Get(TEXT("SelectedItem")),TEXT("ItemId")),S.P(Hook,TEXT("ItemId")));S.Exec(P,Hook);Prev=Match->GetElsePin();}
  FlowUI U(BP,Use.Graph);auto* H=U.If(U.P(Use.Entry,TEXT("then")),U.Valid(U.Get(TEXT("FlowSession"))));auto* I=U.If(H->GetThenPin(),U.Valid(U.Get(TEXT("SelectedItem"))));UK2Node_CallFunction* Apply;auto* P2=U.RuleCall(I->GetThenPin(),TEXT("TryRule"),U.Find(U.Session(TEXT("UseRules")),U.Field(ItemClass,U.Get(TEXT("SelectedItem")),TEXT("ItemId"))),Apply);U.Exec(P2,U.Call(BP->SkeletonGeneratedClass,TEXT("RefreshItems")));
  FlowUI C(BP,Craft.Graph);auto* F=C.If(C.P(Craft.Entry,TEXT("then")),C.Valid(C.Get(TEXT("FlowSession"))));auto* Offset=C.Math(TEXT("Add_IntInt"),C.Math(TEXT("Multiply_IntInt"),C.Get(TEXT("CraftPage")),C.Num(8)),C.P(Craft.Entry,TEXT("Index")));auto* InRange=C.If(F->GetThenPin(),C.Math(TEXT("BooleanAND"),C.Math(TEXT("GreaterEqual_IntInt"),Offset,C.Num(0)),C.Math(TEXT("Less_IntInt"),Offset,C.Length(C.Session(TEXT("CraftRules"))))));UK2Node_CallFunction* Make;auto* P3=C.RuleCall(InRange->GetThenPin(),TEXT("TryRule"),C.At(C.Session(TEXT("CraftRules")),Offset),Make);C.Exec(P3,C.Call(BP->SkeletonGeneratedClass,TEXT("RefreshItems")));
 }
 for(int i=0;i<4;i++){auto F=Pages[i];FlowUI B(BP,F.Graph);const TCHAR* Name=i<2?TEXT("Page"):TEXT("CraftPage");auto* P=B.Assign(B.P(F.Entry,TEXT("then")),Name,B.Math(i%2==0?TEXT("Add_IntInt"):TEXT("Subtract_IntInt"),B.Get(Name),B.Num(1)));B.Exec(P,B.Call(BP->SkeletonGeneratedClass,TEXT("RefreshItems")));}
 {
  FlowUI B(BP,Resume.Graph);auto* Prev=B.Exec(B.P(Resume.Entry,TEXT("then")),B.Call(UWidget::StaticClass(),TEXT("RemoveFromParent")));
  if(Kind==TEXT("pause")){auto* Pause=B.Call(UGameplayStatics::StaticClass(),TEXT("SetGamePaused"));B.D(Pause,TEXT("bPaused"),TEXT("false"));Prev=B.Exec(Prev,Pause);}
  if(Kind!=TEXT("hud")){auto* Owner=B.Call(UUserWidget::StaticClass(),TEXT("GetOwningPlayer"));auto* Mode=B.Call(UWidgetBlueprintLibrary::StaticClass(),TEXT("SetInputMode_GameOnly"));B.L(B.Out(Owner),B.P(Mode,TEXT("PlayerController")));Prev=B.Exec(Prev,Mode);auto* Cursor=B.Node<UK2Node_VariableSet>();Cursor->VariableReference.SetExternalMember(TEXT("bShowMouseCursor"),APlayerController::StaticClass());Cursor->AllocateDefaultPins();B.L(B.Out(Owner),B.P(Cursor,TEXT("self")));B.D(Cursor,TEXT("bShowMouseCursor"),TEXT("false"));Prev=B.Exec(Prev,Cursor);}
  B.Exec(Prev,B.Call(BP->SkeletonGeneratedClass,TEXT("OnResume")));
 }
 if(Kind==TEXT("hud")){
  FlowUI B(BP,Health.Graph);auto* Set=B.Call(UProgressBar::StaticClass(),TEXT("SetPercent"));B.L(B.Get(TEXT("Health")),B.P(Set,TEXT("self")));B.L(B.P(Health.Entry,TEXT("Percent")),B.P(Set,TEXT("InPercent")));B.Exec(B.P(Health.Entry,TEXT("then")),Set);
  FlowUI S(BP,Skill.Graph);auto* Prev=S.P(Skill.Entry,TEXT("then"));for(int i=0;i<4;i++){auto* Match=S.If(Prev,S.Math(TEXT("EqualEqual_IntInt"),S.P(Skill.Entry,TEXT("Index")),S.Num(i)));S.Image(Match->GetThenPin(),*FString::Printf(TEXT("Icon%d"),i),S.P(Skill.Entry,TEXT("Texture")));Prev=Match->GetElsePin();}
 }
 auto* Graph=FBlueprintEditorUtils::CreateNewGraph(BP,TEXT("EventGraph"),UEdGraph::StaticClass(),UEdGraphSchema_K2::StaticClass());FBlueprintEditorUtils::AddUbergraphPage(BP,Graph);FlowUI E(BP,Graph);
 auto* Construct=E.Node<UK2Node_Event>();Construct->EventReference.SetExternalMember(TEXT("Construct"),UUserWidget::StaticClass());Construct->bOverrideFunction=true;Construct->AllocateDefaultPins();E.Exec(E.P(Construct,TEXT("then")),E.Call(BP->SkeletonGeneratedClass,TEXT("RefreshItems")));
 auto* Tick=E.Node<UK2Node_Event>();Tick->EventReference.SetExternalMember(TEXT("Tick"),UUserWidget::StaticClass());Tick->bOverrideFunction=true;Tick->AllocateDefaultPins();auto* P=E.Assign(E.P(Tick,TEXT("then")),TEXT("RefreshClock"),E.Math(TEXT("Add_DoubleDouble"),E.Get(TEXT("RefreshClock")),E.P(Tick,TEXT("InDeltaTime"))));auto* Due=E.If(P,E.Math(TEXT("Greater_DoubleDouble"),E.Get(TEXT("RefreshClock")),E.Lit(TEXT("MakeLiteralDouble"),TEXT("0.2"))));P=E.Assign(Due->GetThenPin(),TEXT("RefreshClock"),TEXT("0"));E.Exec(P,E.Call(BP->SkeletonGeneratedClass,TEXT("RefreshItems")));
 if(Kind==TEXT("inventory")){for(int i=0;i<Count;i++){E.Click(*FString::Printf(TEXT("Slot%d"),i),TEXT("SelectItem"),i);E.Click(*FString::Printf(TEXT("Slot%d"),i),TEXT("SelectItem"),i,TEXT("OnHovered"));}for(int i=0;i<8;i++)E.Click(*FString::Printf(TEXT("Craft%d"),i),TEXT("CraftItem"),i);E.Click(TEXT("UseButton"),TEXT("UseSelected"));E.Click(TEXT("Next"),TEXT("NextPage"));E.Click(TEXT("Previous"),TEXT("PreviousPage"));E.Click(TEXT("CraftNext"),TEXT("NextCraftPage"));E.Click(TEXT("CraftPrevious"),TEXT("PreviousCraftPage"));}
 if(Kind!=TEXT("hud"))E.Click(TEXT("Close"),TEXT("Resume"));if(Kind==TEXT("pause")){E.Click(TEXT("ResumeButton"),TEXT("Resume"));E.Click(TEXT("SettingsButton"),TEXT("OnSettings"));}
 if(Kind!=TEXT("hud")){
 auto* Focused=E.Call(UWidget::StaticClass(),TEXT("HasKeyboardFocus"));auto* Sequence=E.Node<UK2Node_ExecutionSequence>();Sequence->AllocateDefaultPins();E.L(E.P(Tick,TEXT("then")),E.P(Sequence,TEXT("execute")));
 auto* FocusGuard=E.If(E.P(Sequence,TEXT("Then_0")),E.Out(Focused));auto* FocusClose=E.Call(UWidget::StaticClass(),TEXT("SetKeyboardFocus"));E.L(E.Get(TEXT("Close")),E.P(FocusClose,TEXT("self")));E.Exec(FocusGuard->GetThenPin(),FocusClose);
 // Preserve the existing refresh chain after the focus check.
 for(auto Node:Graph->Nodes)if(auto* Set=Cast<UK2Node_VariableSet>(Node.Get()))if(Set->VariableReference.GetMemberName()==TEXT("RefreshClock") && Set->NodePosX>=0){auto* Value=Set->FindPin(TEXT("RefreshClock"));if(Value && Value->LinkedTo.Num()){E.L(E.P(Sequence,TEXT("Then_1")),E.P(Set,TEXT("execute")));break;}}
 }
 Compile(BP);CastChecked<UUserWidget>(BP->GeneratedClass->GetDefaultObject())->SetIsFocusable(true);BP->MarkPackageDirty();return BP;
}
