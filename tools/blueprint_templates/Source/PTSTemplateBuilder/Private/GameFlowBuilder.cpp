#include "PTSTemplateBuilder.h"
#include "GameFlowGraph.h"
#include "Engine/DataAsset.h"
#include "GameFramework/Actor.h"
#include "GameFramework/SaveGame.h"
#include "Kismet/GameplayStatics.h"
#include "UObject/Interface.h"

using namespace PTSGraph;

UBlueprint* UPTSTemplateBuilder::BuildProjectAdapterExample(const FString& Path)
{
 auto* Interface=LoadClass<UInterface>(nullptr,TEXT("/PromptToScene/Templates/BPI_PTSProjectAdapter.BPI_PTSProjectAdapter_C"));check(Interface);
 auto* BP=Plain(Path,AActor::StaticClass());Var(BP,TEXT("Inventory"),Map(Int()));Var(BP,TEXT("Health"),Float(),TEXT("50"));Var(BP,TEXT("MaxHealth"),Float(),TEXT("100"));Var(BP,TEXT("AllowTransactions"),Bool(),TEXT("true"));
 check(FBlueprintEditorUtils::ImplementNewInterface(BP,FTopLevelAssetPath(Interface)));Compile(BP);
 for(const auto& Description:BP->ImplementedInterfaces)for(auto Graph:Description.Graphs){
  TArray<UK2Node_FunctionEntry*> Entries;Graph->GetNodesOfClass(Entries);check(Entries.Num());G B(BP,Graph);auto* Entry=Entries[0];
  if(Graph->GetName()==TEXT("ReadQuantity")){
   Function F{Graph,Entry,{{TEXT("Quantity"),Int()}}};B.Return(F,B.P(Entry,TEXT("then")),{{TEXT("Quantity"),B.Find(B.Get(TEXT("Inventory")),B.P(Entry,TEXT("ItemId")))}});
  }else if(Graph->GetName()==TEXT("ReadHealth")){
   Function F{Graph,Entry,{{TEXT("Current"),Float()},{TEXT("Maximum"),Float()}}};B.Return(F,B.P(Entry,TEXT("then")),{{TEXT("Current"),B.Get(TEXT("Health"))},{TEXT("Maximum"),B.Get(TEXT("MaxHealth"))}});
  }else if(Graph->GetName()==TEXT("CommitGameplay")){
   Function F{Graph,Entry,{{TEXT("Success"),Bool()}}};auto* Allowed=B.If(B.P(Entry,TEXT("then")),B.Get(TEXT("AllowTransactions")));B.Return(F,Allowed->GetElsePin());
   auto* Costs=B.P(Entry,TEXT("Costs"));auto* Rewards=B.P(Entry,TEXT("Rewards"));auto Check=B.Keys(Allowed->GetThenPin(),Costs);
   auto* Enough=B.If(Check.Body,B.Math(TEXT("BooleanAND"),B.Math(TEXT("Greater_IntInt"),B.Find(Costs,Check.Element),B.Num(0)),B.Math(TEXT("GreaterEqual_IntInt"),B.Find(B.Get(TEXT("Inventory")),Check.Element),B.Find(Costs,Check.Element))));B.Return(F,Enough->GetElsePin());
   auto Spend=B.Keys(Check.Done,Costs);B.Add(Spend.Body,B.Get(TEXT("Inventory")),Spend.Element,B.Math(TEXT("Subtract_IntInt"),B.Find(B.Get(TEXT("Inventory")),Spend.Element),B.Find(Costs,Spend.Element)));
   auto Receive=B.Keys(Spend.Done,Rewards);B.Add(Receive.Body,B.Get(TEXT("Inventory")),Receive.Element,B.Math(TEXT("Add_IntInt"),B.Find(B.Get(TEXT("Inventory")),Receive.Element),B.Find(Rewards,Receive.Element)));
   auto* NewHealth=B.Call(UKismetMathLibrary::StaticClass(),TEXT("FMin"));B.L(B.Math(TEXT("Add_DoubleDouble"),B.Get(TEXT("Health")),B.P(Entry,TEXT("Heal"))),B.P(NewHealth,TEXT("A")));B.L(B.Get(TEXT("MaxHealth")),B.P(NewHealth,TEXT("B")));
   B.Return(F,B.Assign(Receive.Done,TEXT("Health"),B.Out(NewHealth)),{{TEXT("Success"),B.Lit(TEXT("MakeLiteralBool"),TEXT("true"))}});
  }
 }
 Compile(BP);return BP;
}

UBlueprint* UPTSTemplateBuilder::BuildGameRuleTemplate(const FString& Path)
{
 auto* BP=Plain(Path,UPrimaryDataAsset::StaticClass());
 for(auto Name:{TEXT("RuleId"),TEXT("Label"),TEXT("Trigger"),TEXT("ItemId")})Var(BP,Name,String());
 Var(BP,TEXT("Costs"),Map(Int()));Var(BP,TEXT("Rewards"),Map(Int()));Var(BP,TEXT("Requires"),Array(String()));
 Var(BP,TEXT("Heal"),Float(),TEXT("0"));Var(BP,TEXT("Once"),Bool(),TEXT("false"));Compile(BP);return BP;
}
UBlueprint* UPTSTemplateBuilder::BuildGameSaveTemplate(const FString& Path)
{
 auto* BP=Plain(Path,USaveGame::StaticClass());Var(BP,TEXT("FlowId"),String());Var(BP,TEXT("SaveKey"),String());
 Var(BP,TEXT("Schema"),Int(),TEXT("1"));Var(BP,TEXT("Health"),Float());Var(BP,TEXT("Inventory"),Map(Int()));Var(BP,TEXT("Completed"),Map(Bool()));Compile(BP);return BP;
}
UBlueprint* UPTSTemplateBuilder::BuildProjectAdapterInterface(const FString& Path)
{
 auto* BP=Plain(Path,UInterface::StaticClass(),BPTYPE_Interface);
 Declare(BP,TEXT("ReadQuantity"),{{TEXT("ItemId"),String()}},{{TEXT("Quantity"),Int()}});
 Declare(BP,TEXT("ReadHealth"),{},{{TEXT("Current"),Float()},{TEXT("Maximum"),Float()}});
 Declare(BP,TEXT("CommitGameplay"),{{TEXT("Costs"),Map(Int())},{TEXT("Rewards"),Map(Int())},{TEXT("Heal"),Float()}},{{TEXT("Success"),Bool()}});
 Compile(BP);return BP;
}
UBlueprint* UPTSTemplateBuilder::BuildGameSessionTemplate(const FString& Path)
{
 auto* RuleClass=LoadClass<UObject>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameRule.BP_PTSGameRule_C"));check(RuleClass);
 auto* SaveClass=LoadClass<USaveGame>(nullptr,TEXT("/PromptToScene/Templates/BP_PTSGameSave.BP_PTSGameSave_C"));check(SaveClass);
 auto* AdapterClass=LoadClass<UInterface>(nullptr,TEXT("/PromptToScene/Templates/BPI_PTSProjectAdapter.BPI_PTSProjectAdapter_C"));check(AdapterClass);
 auto* BP=Plain(Path,AActor::StaticClass());
 for(auto Name:{TEXT("FlowId"),TEXT("SaveKey"),TEXT("LastMessage"),TEXT("FailureReason"),TEXT("SaveError")})Var(BP,Name,String());
 Var(BP,TEXT("Health"),Float(),TEXT("100"));Var(BP,TEXT("MaxHealth"),Float(),TEXT("100"));
 Var(BP,TEXT("Inventory"),Map(Int()));Var(BP,TEXT("Limits"),Map(Int()));Var(BP,TEXT("Completed"),Map(Bool()));
 Var(BP,TEXT("Rules"),Map(Object(RuleClass)));Var(BP,TEXT("UseRules"),Map(String()));Var(BP,TEXT("CraftRules"),Array(String()));
 Var(BP,TEXT("ItemIds"),Array(String()));Var(BP,TEXT("Adapter"),Object(AActor::StaticClass()));
 for(auto Name:{TEXT("Initialized"),TEXT("Busy"),TEXT("SaveBlocked"),TEXT("LastSuccess")})Var(BP,Name,Bool(),TEXT("false"));
 Var(BP,TEXT("Autosave"),Bool(),TEXT("true"));
 auto Init=Declare(BP,TEXT("Initialize"));auto Sync=Declare(BP,TEXT("RefreshAdapter"));
 auto Check=Declare(BP,TEXT("CanRule"),{{TEXT("RuleId"),String()}},{{TEXT("Allowed"),Bool()}});
 auto Apply=Declare(BP,TEXT("TryRule"),{{TEXT("RuleId"),String()}},{{TEXT("Success"),Bool()}});
 auto Save=Declare(BP,TEXT("SaveProgress"),{},{{TEXT("Success"),Bool()}});
 Compile(BP);
 // Mirror external state only for display and validation. Never write it during load.
 {
  G B(BP,Sync.Graph);auto* Guard=B.If(B.P(Sync.Entry,TEXT("then")),B.Valid(B.Get(TEXT("Adapter"))));B.Return(Sync,Guard->GetElsePin());
  auto Loop=B.Each(Guard->GetThenPin(),B.Get(TEXT("ItemIds")));
  auto* Read=B.Message(AdapterClass,TEXT("ReadQuantity"),B.Get(TEXT("Adapter")));B.L(Loop.Element,B.P(Read,TEXT("ItemId")));
  B.Add(B.Exec(Loop.Body,Read),B.Get(TEXT("Inventory")),Loop.Element,B.P(Read,TEXT("Quantity")));
  auto* Health=B.Message(AdapterClass,TEXT("ReadHealth"),B.Get(TEXT("Adapter")));auto* Prev=B.Exec(Loop.Done,Health);
  Prev=B.Assign(Prev,TEXT("Health"),B.P(Health,TEXT("Current")));Prev=B.Assign(Prev,TEXT("MaxHealth"),B.P(Health,TEXT("Maximum")));B.Return(Sync,Prev);
 }
 // Initialize once, refusing to replace an unreadable or foreign save slot.
 {
  G B(BP,Init.Graph);auto* Already=B.If(B.P(Init.Entry,TEXT("then")),B.Get(TEXT("Initialized")));B.Return(Init,Already->GetThenPin());
  auto* Prev=B.Assign(Already->GetElsePin(),TEXT("Initialized"),TEXT("true"));
  auto* Exists=B.Call(UGameplayStatics::StaticClass(),TEXT("DoesSaveGameExist"));B.L(B.Get(TEXT("SaveKey")),B.P(Exists,TEXT("SlotName")));
  Prev=B.Assign(Prev,TEXT("SaveBlocked"),TEXT("false"));Prev=B.Assign(Prev,TEXT("SaveError"),TEXT(""));
  auto* Has=B.If(B.Exec(Prev,Exists),B.Out(Exists));auto* Refresh=B.Call(BP->SkeletonGeneratedClass,TEXT("RefreshAdapter"));B.Return(Init,B.Exec(Has->GetElsePin(),Refresh));
  auto* Load=B.Call(UGameplayStatics::StaticClass(),TEXT("LoadGameFromSlot"));B.L(B.Get(TEXT("SaveKey")),B.P(Load,TEXT("SlotName")));Prev=B.Exec(Has->GetThenPin(),Load);
  auto* Cast=B.Cast(Prev,B.Out(Load),SaveClass);auto* Data=Cast->GetCastResultPin();
  auto* SameKey=B.Math(TEXT("EqualEqual_StrStr"),B.Field(SaveClass,Data,TEXT("SaveKey")),B.Get(TEXT("SaveKey")));
  auto* SameFlow=B.Math(TEXT("EqualEqual_StrStr"),B.Field(SaveClass,Data,TEXT("FlowId")),B.Get(TEXT("FlowId")));
  auto* SameSchema=B.Math(TEXT("EqualEqual_IntInt"),B.Field(SaveClass,Data,TEXT("Schema")),B.Num(1));
  auto* Match=B.If(Cast->GetValidCastPin(),B.Math(TEXT("BooleanAND"),B.Math(TEXT("BooleanAND"),SameKey,SameFlow),SameSchema));
  auto* Bad=B.Set(TEXT("SaveBlocked"));B.D(Bad,TEXT("SaveBlocked"),TEXT("true"));B.Exec(Cast->GetInvalidCastPin(),Bad);B.Exec(Match->GetElsePin(),Bad);
  B.Return(Init,B.Assign(B.P(Bad,TEXT("then")),TEXT("SaveError"),TEXT("Existing progress could not be loaded; choose a new save slot or restore it. The file is retained.")));
  Prev=Match->GetThenPin();for(auto Name:{TEXT("Inventory"),TEXT("Completed"),TEXT("Health")})Prev=B.Assign(Prev,Name,B.Field(SaveClass,Data,Name));
  B.Return(Init,B.Exec(Prev,B.Call(BP->SkeletonGeneratedClass,TEXT("RefreshAdapter"))));
 }
 // Validation is read-only: all conditions and stack limits precede any debit.
 {
  G B(BP,Check.Graph);auto* Id=B.P(Check.Entry,TEXT("RuleId"));auto* Prev=B.Exec(B.P(Check.Entry,TEXT("then")),B.Call(BP->SkeletonGeneratedClass,TEXT("Initialize")));
  Prev=B.Exec(Prev,B.Call(BP->SkeletonGeneratedClass,TEXT("RefreshAdapter")));
  auto Fail=[&](UEdGraphPin* Pin,const TCHAR* Reason){B.Return(Check,B.Assign(Pin,TEXT("FailureReason"),Reason));};
  auto* Rule=B.Find(B.Get(TEXT("Rules")),Id);auto* Valid=B.If(Prev,B.Valid(Rule));Fail(Valid->GetElsePin(),TEXT("Unknown action"));
  auto* Once=B.If(Valid->GetThenPin(),B.Math(TEXT("BooleanAND"),B.Field(RuleClass,Rule,TEXT("Once")),B.Contains(B.Get(TEXT("Completed")),Id)));
  Fail(Once->GetThenPin(),TEXT("Already completed"));
  auto Needs=B.Each(Once->GetElsePin(),B.Field(RuleClass,Rule,TEXT("Requires")));
  auto* Prerequisite=B.If(Needs.Body,B.Contains(B.Get(TEXT("Completed")),Needs.Element));Fail(Prerequisite->GetElsePin(),TEXT("Complete the prerequisite first"));
  auto* Heal=B.Field(RuleClass,Rule,TEXT("Heal"));auto* Positive=B.Call(UKismetMathLibrary::StaticClass(),TEXT("Greater_DoubleDouble"));B.L(Heal,B.P(Positive,TEXT("A")));
  auto* Full=B.If(Needs.Done,B.Math(TEXT("BooleanAND"),B.Out(Positive),B.Math(TEXT("GreaterEqual_DoubleDouble"),B.Get(TEXT("Health")),B.Get(TEXT("MaxHealth")))));
  Fail(Full->GetThenPin(),TEXT("Health is already full"));
  auto* Costs=B.Field(RuleClass,Rule,TEXT("Costs"));auto* Rewards=B.Field(RuleClass,Rule,TEXT("Rewards"));
  auto Spend=B.Keys(Full->GetElsePin(),Costs);
  auto* Enough=B.If(Spend.Body,B.Math(TEXT("GreaterEqual_IntInt"),B.Find(B.Get(TEXT("Inventory")),Spend.Element),B.Find(Costs,Spend.Element)));
  Fail(Enough->GetElsePin(),TEXT("Not enough materials"));
  auto Receive=B.Keys(Spend.Done,Rewards);
  auto* NewCount=B.Math(TEXT("Add_IntInt"),B.Math(TEXT("Subtract_IntInt"),B.Find(B.Get(TEXT("Inventory")),Receive.Element),B.Find(Costs,Receive.Element)),B.Find(Rewards,Receive.Element));
  auto* Capacity=B.If(Receive.Body,B.Math(TEXT("LessEqual_IntInt"),NewCount,B.Find(B.Get(TEXT("Limits")),Receive.Element)));Fail(Capacity->GetElsePin(),TEXT("Item stack is full"));
  Prev=B.Assign(Receive.Done,TEXT("FailureReason"),TEXT(""));B.Return(Check,Prev,{{TEXT("Allowed"),B.Lit(TEXT("MakeLiteralBool"),TEXT("true"))}});
 }
 {
  G B(BP,Apply.Graph);auto* Id=B.P(Apply.Entry,TEXT("RuleId"));auto* Reentry=B.If(B.P(Apply.Entry,TEXT("then")),B.Get(TEXT("Busy")));B.Return(Apply,Reentry->GetThenPin());
  auto* Prev=B.Assign(Reentry->GetElsePin(),TEXT("Busy"),TEXT("true"));Prev=B.Assign(Prev,TEXT("LastSuccess"),TEXT("false"));
  auto Fail=[&](UEdGraphPin* Pin,UEdGraphPin* Reason){auto* P=B.Assign(Pin,TEXT("Busy"),TEXT("false"));B.Return(Apply,B.Assign(P,TEXT("LastMessage"),Reason));};
  auto* Can=B.Call(BP->SkeletonGeneratedClass,TEXT("CanRule"));B.L(Id,B.P(Can,TEXT("RuleId")));auto* Allowed=B.If(B.Exec(Prev,Can),B.P(Can,TEXT("Allowed")));Fail(Allowed->GetElsePin(),B.Get(TEXT("FailureReason")));
  auto* Rule=B.Find(B.Get(TEXT("Rules")),Id);auto* Costs=B.Field(RuleClass,Rule,TEXT("Costs"));auto* Rewards=B.Field(RuleClass,Rule,TEXT("Rewards"));auto* Heal=B.Field(RuleClass,Rule,TEXT("Heal"));
  auto* External=B.If(Allowed->GetThenPin(),B.Valid(B.Get(TEXT("Adapter"))));
  auto* Commit=B.Message(AdapterClass,TEXT("CommitGameplay"),B.Get(TEXT("Adapter")));B.L(Costs,B.P(Commit,TEXT("Costs")));B.L(Rewards,B.P(Commit,TEXT("Rewards")));B.L(Heal,B.P(Commit,TEXT("Heal")));
  auto* Accepted=B.If(B.Exec(External->GetThenPin(),Commit),B.P(Commit,TEXT("Success")));Fail(Accepted->GetElsePin(),B.Str(TEXT("Project adapter rejected the action")));
  auto* Refreshed=B.Call(BP->SkeletonGeneratedClass,TEXT("RefreshAdapter"));B.Exec(Accepted->GetThenPin(),Refreshed);
  auto Spend=B.Keys(External->GetElsePin(),Costs);
  B.Add(Spend.Body,B.Get(TEXT("Inventory")),Spend.Element,B.Math(TEXT("Subtract_IntInt"),B.Find(B.Get(TEXT("Inventory")),Spend.Element),B.Find(Costs,Spend.Element)));
  auto Receive=B.Keys(Spend.Done,Rewards);
  B.Add(Receive.Body,B.Get(TEXT("Inventory")),Receive.Element,B.Math(TEXT("Add_IntInt"),B.Find(B.Get(TEXT("Inventory")),Receive.Element),B.Find(Rewards,Receive.Element)));
  auto* NewHealth=B.Call(UKismetMathLibrary::StaticClass(),TEXT("FMin"));B.L(B.Math(TEXT("Add_DoubleDouble"),B.Get(TEXT("Health")),Heal),B.P(NewHealth,TEXT("A")));B.L(B.Get(TEXT("MaxHealth")),B.P(NewHealth,TEXT("B")));
  Prev=B.Assign(Receive.Done,TEXT("Health"),B.Out(NewHealth));
  auto* Completed=B.Call(UBlueprintMapLibrary::StaticClass(),TEXT("Map_Add"));B.L(B.Get(TEXT("Completed")),B.P(Completed,TEXT("TargetMap")));B.L(Id,B.P(Completed,TEXT("Key")));B.D(Completed,TEXT("Value"),TEXT("true"));B.Exec(B.P(Refreshed,TEXT("then")),Completed);Prev=B.Exec(Prev,Completed);
  auto* Autosave=B.If(Prev,B.Get(TEXT("Autosave")));auto* SaveCall=B.Call(BP->SkeletonGeneratedClass,TEXT("SaveProgress"));B.Exec(Autosave->GetThenPin(),SaveCall);
  auto* Done=B.Set(TEXT("LastSuccess"));B.D(Done,TEXT("LastSuccess"),TEXT("true"));B.Exec(Autosave->GetElsePin(),Done);B.Exec(B.P(SaveCall,TEXT("then")),Done);
  Prev=B.Assign(B.P(Done,TEXT("then")),TEXT("LastMessage"),B.Field(RuleClass,Rule,TEXT("Label")));Prev=B.Assign(Prev,TEXT("Busy"),TEXT("false"));B.Return(Apply,Prev,{{TEXT("Success"),B.Get(TEXT("LastSuccess"))}});
 }
 {
  G B(BP,Save.Graph);auto* Blocked=B.If(B.P(Save.Entry,TEXT("then")),B.Get(TEXT("SaveBlocked")));B.Return(Save,Blocked->GetThenPin());
  auto* Create=B.Call(UGameplayStatics::StaticClass(),TEXT("CreateSaveGameObject"));B.P(Create,TEXT("SaveGameClass"))->DefaultObject=SaveClass;
  auto* Cast=B.Cast(B.Exec(Blocked->GetElsePin(),Create),B.Out(Create),SaveClass);auto* Data=Cast->GetCastResultPin();auto* Prev=Cast->GetValidCastPin();
  for(auto Name:{TEXT("FlowId"),TEXT("SaveKey"),TEXT("Health"),TEXT("Inventory"),TEXT("Completed")})Prev=B.SetField(Prev,SaveClass,Data,Name,B.Get(Name));
  auto* Write=B.Call(UGameplayStatics::StaticClass(),TEXT("SaveGameToSlot"));B.L(Data,B.P(Write,TEXT("SaveGameObject")));B.L(B.Get(TEXT("SaveKey")),B.P(Write,TEXT("SlotName")));
  auto* Success=B.If(B.Exec(Prev,Write),B.Out(Write));auto* Clear=B.Assign(Success->GetThenPin(),TEXT("SaveError"),TEXT(""));B.Return(Save,Clear,{{TEXT("Success"),B.Out(Write)}});
  B.Return(Save,B.Assign(Success->GetElsePin(),TEXT("SaveError"),TEXT("Progress could not be saved; check disk access.")));
 }
 auto* EventGraph=FBlueprintEditorUtils::CreateNewGraph(BP,TEXT("EventGraph"),UEdGraph::StaticClass(),UEdGraphSchema_K2::StaticClass());FBlueprintEditorUtils::AddUbergraphPage(BP,EventGraph);
 G E(BP,EventGraph);auto* Begin=E.Node<UK2Node_Event>();Begin->EventReference.SetExternalMember(TEXT("ReceiveBeginPlay"),AActor::StaticClass());Begin->bOverrideFunction=true;Begin->AllocateDefaultPins();E.Exec(E.P(Begin,TEXT("then")),E.Call(BP->SkeletonGeneratedClass,TEXT("Initialize")));
 Compile(BP);return BP;
}
