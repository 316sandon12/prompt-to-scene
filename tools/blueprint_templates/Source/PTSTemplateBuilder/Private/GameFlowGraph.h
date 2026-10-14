#pragma once
#include "Engine/Blueprint.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "EdGraphSchema_K2.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet/BlueprintMapLibrary.h"
#include "Kismet/KismetArrayLibrary.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/KismetStringLibrary.h"
#include "K2Node_FunctionEntry.h"
#include "K2Node_FunctionResult.h"
#include "K2Node_CallFunction.h"
#include "K2Node_CallArrayFunction.h"
#include "K2Node_Message.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_MacroInstance.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_DynamicCast.h"
#include "K2Node_Event.h"
#include "K2Node_Self.h"
#include "Misc/PackageName.h"

namespace PTSGraph {
inline FEdGraphPinType Type(FName Category,UObject* Class=nullptr){FEdGraphPinType T;T.PinCategory=Category;T.PinSubCategoryObject=Class;if(Category==UEdGraphSchema_K2::PC_Real)T.PinSubCategory=UEdGraphSchema_K2::PC_Float;return T;}
inline FEdGraphPinType String(){return Type(UEdGraphSchema_K2::PC_String);}
inline FEdGraphPinType Int(){return Type(UEdGraphSchema_K2::PC_Int);}
inline FEdGraphPinType Bool(){return Type(UEdGraphSchema_K2::PC_Boolean);}
inline FEdGraphPinType Float(){return Type(UEdGraphSchema_K2::PC_Real);}
inline FEdGraphPinType Object(UClass* C){return Type(UEdGraphSchema_K2::PC_Object,C);}
inline FEdGraphPinType Array(FEdGraphPinType T){T.ContainerType=EPinContainerType::Array;return T;}
inline FEdGraphPinType Map(FEdGraphPinType V){auto T=String();T.ContainerType=EPinContainerType::Map;T.PinValueType.TerminalCategory=V.PinCategory;T.PinValueType.TerminalSubCategory=V.PinSubCategory;T.PinValueType.TerminalSubCategoryObject=V.PinSubCategoryObject;return T;}
inline UBlueprint* Plain(const FString& Path,UClass* Parent,EBlueprintType Kind=BPTYPE_Normal){return FKismetEditorUtilities::CreateBlueprint(Parent,CreatePackage(*Path),*FPackageName::GetLongPackageAssetName(Path),Kind,UBlueprint::StaticClass(),UBlueprintGeneratedClass::StaticClass());}
inline void Compile(UBlueprint* BP){FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);FKismetEditorUtilities::CompileBlueprint(BP);checkf(BP->Status!=BS_Error,TEXT("Gameplay compile failed: %s"),*BP->GetName());BP->MarkPackageDirty();}
inline void Var(UBlueprint* BP,const TCHAR* Name,FEdGraphPinType T,FString Default=TEXT("")){FBlueprintEditorUtils::AddMemberVariable(BP,Name,T,Default);if(auto* Flags=FBlueprintEditorUtils::GetBlueprintVariablePropertyFlags(BP,Name))*Flags=(*Flags&~CPF_DisableEditOnInstance)|CPF_Edit|CPF_BlueprintVisible;}
struct Function { UEdGraph* Graph; UK2Node_FunctionEntry* Entry; TArray<TPair<FString,FEdGraphPinType>> Outputs; };
inline Function Declare(UBlueprint* BP,const TCHAR* Name,TArray<TPair<FString,FEdGraphPinType>> Inputs={},TArray<TPair<FString,FEdGraphPinType>> Outputs={}){
 auto* Graph=FBlueprintEditorUtils::CreateNewGraph(BP,Name,UEdGraph::StaticClass(),UEdGraphSchema_K2::StaticClass());
 FBlueprintEditorUtils::AddFunctionGraph<UClass>(BP,Graph,true,nullptr);
 TArray<UK2Node_FunctionEntry*> Entries;Graph->GetNodesOfClass(Entries);check(Entries.Num());auto* Entry=Entries[0];Entry->AddExtraFlags(FUNC_Public|FUNC_BlueprintCallable);
 for(auto P:Inputs)Entry->CreateUserDefinedPin(*P.Key,P.Value,EGPD_Output);
 auto* Result=NewObject<UK2Node_FunctionResult>(Graph);Graph->AddNode(Result,false,false);Result->CreateNewGuid();Result->FunctionReference.SetSelfMember(Name);Result->AllocateDefaultPins();
 for(auto P:Outputs)Result->CreateUserDefinedPin(*P.Key,P.Value,EGPD_Input);
 return {Graph,Entry,Outputs};
}
struct Loop { UEdGraphPin* Body; UEdGraphPin* Element; UEdGraphPin* Index; UEdGraphPin* Done; };
struct G {
 UBlueprint* BP; UEdGraph* Graph; const UEdGraphSchema_K2* S=GetDefault<UEdGraphSchema_K2>(); int Count=0;
 G(UBlueprint* B,UEdGraph* In):BP(B),Graph(In){}
 template<class T>T* Node(){auto* N=NewObject<T>(Graph);Graph->AddNode(N,false,false);N->CreateNewGuid();N->NodePosX=(Count%8)*360;N->NodePosY=(Count++/8)*280;return N;}
 UEdGraphPin* P(UEdGraphNode* N,const TCHAR* Name){auto* Pin=N->FindPin(Name);checkf(Pin,TEXT("Missing pin %s on %s"),Name,*N->GetNodeTitle(ENodeTitleType::FullTitle).ToString());return Pin;}
 void L(UEdGraphPin* A,UEdGraphPin* B){checkf(A&&B&&S->TryCreateConnection(A,B),TEXT("Gameplay connection failed: %s -> %s"),A?*A->PinName.ToString():TEXT("null"),B?*B->PinName.ToString():TEXT("null"));}
 void D(UEdGraphNode* N,const TCHAR* Name,FString V){S->TrySetDefaultValue(*P(N,Name),V);}
 UEdGraphPin* Out(UEdGraphNode* N){return P(N,TEXT("ReturnValue"));}
 UK2Node_CallFunction* Call(UClass* C,const TCHAR* Name){auto* F=C->FindFunctionByName(Name);checkf(F,TEXT("Missing gameplay function: %s on %s"),Name,*C->GetName());UK2Node_CallFunction* N=C==UKismetArrayLibrary::StaticClass()?Node<UK2Node_CallArrayFunction>():Node<UK2Node_CallFunction>();N->SetFromFunction(F);N->AllocateDefaultPins();return N;}
 UK2Node_Message* Message(UClass* C,const TCHAR* Name,UEdGraphPin* Target){auto* F=C->FindFunctionByName(Name);check(F);auto* N=Node<UK2Node_Message>();N->SetFromFunction(F);N->AllocateDefaultPins();L(Target,P(N,TEXT("self")));return N;}
 UEdGraphPin* Exec(UEdGraphPin* Prev,UEdGraphNode* N){L(Prev,P(N,TEXT("execute")));return P(N,TEXT("then"));}
 UEdGraphPin* Get(const TCHAR* Name){auto* N=Node<UK2Node_VariableGet>();N->VariableReference.SetSelfMember(Name);N->AllocateDefaultPins();return P(N,Name);}
 UEdGraphPin* Field(UClass* C,UEdGraphPin* Object,const TCHAR* Name){auto* N=Node<UK2Node_VariableGet>();N->VariableReference.SetExternalMember(Name,C);N->AllocateDefaultPins();L(Object,P(N,TEXT("self")));return P(N,Name);}
 UK2Node_VariableSet* Set(const TCHAR* Name){auto* N=Node<UK2Node_VariableSet>();N->VariableReference.SetSelfMember(Name);N->AllocateDefaultPins();return N;}
 UEdGraphPin* Assign(UEdGraphPin* Prev,const TCHAR* Name,UEdGraphPin* Value){auto* N=Set(Name);L(Value,P(N,Name));return Exec(Prev,N);}
 UEdGraphPin* Assign(UEdGraphPin* Prev,const TCHAR* Name,FString Value){auto* N=Set(Name);D(N,Name,Value);return Exec(Prev,N);}
 UEdGraphPin* SetField(UEdGraphPin* Prev,UClass* C,UEdGraphPin* Object,const TCHAR* Name,UEdGraphPin* Value){auto* N=Node<UK2Node_VariableSet>();N->VariableReference.SetExternalMember(Name,C);N->AllocateDefaultPins();L(Object,P(N,TEXT("self")));L(Value,P(N,Name));return Exec(Prev,N);}
 UK2Node_IfThenElse* If(UEdGraphPin* Prev,UEdGraphPin* Test){auto* N=Node<UK2Node_IfThenElse>();N->AllocateDefaultPins();L(Prev,N->GetExecPin());L(Test,N->GetConditionPin());return N;}
 UEdGraphPin* Valid(UEdGraphPin* Object){auto* N=Call(UKismetSystemLibrary::StaticClass(),TEXT("IsValid"));L(Object,P(N,TEXT("Object")));return Out(N);}
 UEdGraphPin* Math(const TCHAR* Name,UEdGraphPin* A,UEdGraphPin* B=nullptr){auto* N=Call(FString(Name).EndsWith(TEXT("StrStr"))?UKismetStringLibrary::StaticClass():UKismetMathLibrary::StaticClass(),Name);L(A,P(N,TEXT("A")));if(B)L(B,P(N,TEXT("B")));return Out(N);}
 UEdGraphPin* Lit(const TCHAR* Function,FString Value){auto* N=Call(UKismetSystemLibrary::StaticClass(),Function);D(N,TEXT("Value"),Value);return Out(N);}
 UEdGraphPin* Str(FString V){return Lit(TEXT("MakeLiteralString"),V);}
 UEdGraphPin* Num(int V){return Lit(TEXT("MakeLiteralInt"),FString::FromInt(V));}
 UEdGraphPin* Length(UEdGraphPin* Values){auto* N=Call(UKismetArrayLibrary::StaticClass(),TEXT("Array_Length"));L(Values,P(N,TEXT("TargetArray")));return Out(N);}
 UEdGraphPin* At(UEdGraphPin* Values,UEdGraphPin* Index){auto* N=Call(UKismetArrayLibrary::StaticClass(),TEXT("Array_Get"));L(Values,P(N,TEXT("TargetArray")));L(Index,P(N,TEXT("Index")));return P(N,TEXT("Item"));}
 UEdGraphPin* Append(UEdGraphPin* Prev,UEdGraphPin* Values,UEdGraphPin* Item){auto* N=Call(UKismetArrayLibrary::StaticClass(),TEXT("Array_Add"));L(Values,P(N,TEXT("TargetArray")));L(Item,P(N,TEXT("NewItem")));return Exec(Prev,N);}
 UEdGraphPin* Find(UEdGraphPin* MapValue,UEdGraphPin* Key){auto* N=Call(UBlueprintMapLibrary::StaticClass(),TEXT("Map_Find"));L(MapValue,P(N,TEXT("TargetMap")));L(Key,P(N,TEXT("Key")));return P(N,TEXT("Value"));}
 UEdGraphPin* Contains(UEdGraphPin* MapValue,UEdGraphPin* Key){auto* N=Call(UBlueprintMapLibrary::StaticClass(),TEXT("Map_Contains"));L(MapValue,P(N,TEXT("TargetMap")));L(Key,P(N,TEXT("Key")));return Out(N);}
 UEdGraphPin* Add(UEdGraphPin* Prev,UEdGraphPin* MapValue,UEdGraphPin* Key,UEdGraphPin* Value){auto* N=Call(UBlueprintMapLibrary::StaticClass(),TEXT("Map_Add"));L(MapValue,P(N,TEXT("TargetMap")));L(Key,P(N,TEXT("Key")));L(Value,P(N,TEXT("Value")));return Exec(Prev,N);}
 Loop Each(UEdGraphPin* Prev,UEdGraphPin* Values){auto* Macros=LoadObject<UBlueprint>(nullptr,TEXT("/Engine/EditorBlueprintResources/StandardMacros.StandardMacros"));check(Macros);UEdGraph* Macro=nullptr;for(auto Candidate:Macros->MacroGraphs)if(Candidate->GetName()==TEXT("ForEachLoop"))Macro=Candidate;check(Macro);auto* N=Node<UK2Node_MacroInstance>();N->SetMacroGraph(Macro);N->AllocateDefaultPins();L(Values,P(N,TEXT("Array")));L(Prev,P(N,TEXT("exec")));return {P(N,TEXT("LoopBody")),P(N,TEXT("Array Element")),P(N,TEXT("Array Index")),P(N,TEXT("Completed"))};}
 Loop Keys(UEdGraphPin* Prev,UEdGraphPin* Value){auto* N=Call(UBlueprintMapLibrary::StaticClass(),TEXT("Map_Keys"));L(Value,P(N,TEXT("TargetMap")));return Each(Exec(Prev,N),P(N,TEXT("Keys")));}
 void Return(Function F,UEdGraphPin* Prev,TMap<FString,UEdGraphPin*> Values={}){auto* N=Node<UK2Node_FunctionResult>();N->FunctionReference.SetSelfMember(Graph->GetFName());N->AllocateDefaultPins();for(auto Pair:F.Outputs){auto* Pin=N->FindPin(*Pair.Key);if(!Pin)Pin=N->CreateUserDefinedPin(*Pair.Key,Pair.Value,EGPD_Input);if(Values.Contains(Pair.Key))L(Values[Pair.Key],Pin);}if(Prev)L(Prev,P(N,TEXT("execute")));}
 UEdGraphPin* Self(){auto* N=Node<UK2Node_Self>();N->AllocateDefaultPins();return P(N,TEXT("self"));}
 UK2Node_DynamicCast* Cast(UEdGraphPin* Prev,UEdGraphPin* Object,UClass* C){auto* N=Node<UK2Node_DynamicCast>();N->TargetType=C;N->AllocateDefaultPins();L(Object,N->GetCastSourcePin());L(Prev,N->GetExecPin());return N;}
};
}
