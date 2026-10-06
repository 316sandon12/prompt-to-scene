#include "PTSTemplateBuilder.h"
#include "EditorUtilityWidget.h"
#include "EditorUtilityWidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Components/ScrollBox.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Components/EditableTextBox.h"
#include "Components/Image.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/SizeBox.h"
#include "Components/ScaleBox.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_CallFunction.h"
#include "UObject/UnrealType.h"
#include "Misc/PackageName.h"

UBlueprint* UPTSTemplateBuilder::BuildWorkshopTemplate(const FString& PackagePath)
{
    auto* Package=CreatePackage(*PackagePath);
    auto* BP=CastChecked<UEditorUtilityWidgetBlueprint>(FKismetEditorUtilities::CreateBlueprint(
        UEditorUtilityWidget::StaticClass(),Package,*FPackageName::GetLongPackageAssetName(PackagePath),
        BPTYPE_Normal,UEditorUtilityWidgetBlueprint::StaticClass(),UWidgetBlueprintGeneratedClass::StaticClass()));
    BP->WidgetTree=NewObject<UWidgetTree>(BP,TEXT("WidgetTree"),RF_Transactional);
    auto* Scroll=BP->WidgetTree->ConstructWidget<UScrollBox>(UScrollBox::StaticClass(),TEXT("WorkshopScroll"));
    auto* Box=BP->WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(),TEXT("WorkshopContent"));
    Scroll->AddChild(Box);BP->WidgetTree->RootWidget=Scroll;
    auto AddText=[&](const TCHAR* Name,const TCHAR* Value)
    {
        auto* Text=BP->WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(),Name);
        Text->SetText(FText::FromString(Value));Text->SetAutoWrapText(true);Text->bIsVariable=true;
        auto Font=Text->GetFont();Font.Size=12;Font.TypefaceFontName=TEXT("Regular");Text->SetFont(Font);
        auto* Slot=Box->AddChildToVerticalBox(Text);Slot->SetPadding(FMargin(12));return Text;
    };
    AddText(TEXT("Title"),TEXT("Prompt-to-Scene | Asset Workshop"));
    AddText(TEXT("Status"),TEXT("Select assets in the Content Browser, then choose an action."));
    AddText(TEXT("Details"),TEXT("Naming plans and material slot changes appear here before applying."));
    AddText(TEXT("SlotHelp"),TEXT("Apply material slots: enter row IDs separated by commas; leave blank for all."));
    auto* Slots=BP->WidgetTree->ConstructWidget<UEditableTextBox>(UEditableTextBox::StaticClass(),TEXT("SelectedSlots"));
    Slots->bIsVariable=true;Box->AddChildToVerticalBox(Slots)->SetPadding(FMargin(12,4));
    auto* Images=BP->WidgetTree->ConstructWidget<UHorizontalBox>();Box->AddChildToVerticalBox(Images);
    for(const TCHAR* ImageName:{TEXT("BeforeImage"),TEXT("AfterImage")})
    {
        const FString FrameName=FString(ImageName).Replace(TEXT("Image"),TEXT("Frame"));
        auto* Frame=BP->WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass(),*FrameName);
        Frame->bIsVariable=true;Frame->SetHeightOverride(200);Frame->SetVisibility(ESlateVisibility::Collapsed);
        auto* Scale=BP->WidgetTree->ConstructWidget<UScaleBox>();
        Scale->SetStretch(EStretch::ScaleToFit);Frame->AddChild(Scale);
        auto* Image=BP->WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(),ImageName);
        Image->bIsVariable=true;Image->SetDesiredSizeOverride(FVector2D(960,640));
        Image->SetVisibility(ESlateVisibility::Collapsed);
        Scale->AddChild(Image);
        auto* Slot=Images->AddChildToHorizontalBox(Frame);
        Slot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));Slot->SetPadding(FMargin(12,4));
    }
    const TArray<TPair<FString,FString>> Buttons={
        {TEXT("inspect_selected"),TEXT("Inspect selection")},{TEXT("organize_selected"),TEXT("Preview organization")},
        {TEXT("organize_apply"),TEXT("Apply organization")},{TEXT("organize_undo"),TEXT("Undo organization")},
        {TEXT("semantic"),TEXT("Capture selection for AI recognition")},{TEXT("reference"),TEXT("Use first selected asset as reference")},
        {TEXT("adapt_preview"),TEXT("Preview reference look on selected meshes")},{TEXT("preview_assets"),TEXT("Open preview variants")},
        {TEXT("adapt_apply"),TEXT("Apply material preview")},{TEXT("adapt_undo"),TEXT("Undo material adaptation")},
        {TEXT("inbox"),TEXT("Open source inbox")},{TEXT("intake"),TEXT("Import settled inbox files now")},
        {TEXT("defaults"),TEXT("Toggle automatic intake / save project defaults")},{TEXT("cancel"),TEXT("Cancel current task")}
    };
    for(const auto& Row:Buttons)
    {
        auto* Button=BP->WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(),*Row.Key);Button->bIsVariable=true;
        auto* Label=BP->WidgetTree->ConstructWidget<UTextBlock>();Label->SetText(FText::FromString(Row.Value));
        auto Font=Label->GetFont();Font.Size=12;Font.TypefaceFontName=TEXT("Regular");Label->SetFont(Font);Label->SetAutoWrapText(true);
        Button->AddChild(Label);auto* Slot=Box->AddChildToVerticalBox(Button);Slot->SetPadding(FMargin(12,4));
    }
    FKismetEditorUtilities::CompileBlueprint(BP);
    auto* Graph=BP->UbergraphPages.Num()?BP->UbergraphPages[0].Get():FBlueprintEditorUtils::CreateNewGraph(BP,TEXT("EventGraph"),UEdGraph::StaticClass(),UEdGraphSchema_K2::StaticClass());
    if(!BP->UbergraphPages.Contains(Graph))FBlueprintEditorUtils::AddUbergraphPage(BP,Graph);
    auto* Python=LoadObject<UClass>(nullptr,TEXT("/Script/PythonScriptPlugin.PythonScriptLibrary"));check(Python);
    auto* Fn=Python->FindFunctionByName(TEXT("ExecutePythonCommand"));check(Fn);
    const auto* Schema=GetDefault<UEdGraphSchema_K2>();int Index=0;
    for(const auto& Row:Buttons)
    {
        auto* Property=FindFProperty<FObjectProperty>(BP->SkeletonGeneratedClass,*Row.Key);check(Property);
        auto* Delegate=FindFProperty<FMulticastDelegateProperty>(UButton::StaticClass(),TEXT("OnClicked"));check(Delegate);
        auto* Event=NewObject<UK2Node_ComponentBoundEvent>(Graph);Graph->AddNode(Event,false,false);Event->CreateNewGuid();
        Event->InitializeComponentBoundEventParams(Property,Delegate);Event->AllocateDefaultPins();Event->NodePosY=Index++*200;
        auto* Call=NewObject<UK2Node_CallFunction>(Graph);Graph->AddNode(Call,false,false);Call->CreateNewGuid();Call->SetFromFunction(Fn);Call->AllocateDefaultPins();Call->NodePosY=Event->NodePosY;Call->NodePosX=400;
        Schema->TrySetDefaultValue(*Call->FindPinChecked(TEXT("PythonCommand")),TEXT("from prompt_to_scene_unreal import panel; panel.button('")+Row.Key+TEXT("')"));
        check(Schema->TryCreateConnection(Event->FindPinChecked(TEXT("then")),Call->FindPinChecked(TEXT("execute"))));
    }
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);FKismetEditorUtilities::CompileBlueprint(BP);
    check(BP->Status!=BS_Error);BP->MarkPackageDirty();return BP;
}
