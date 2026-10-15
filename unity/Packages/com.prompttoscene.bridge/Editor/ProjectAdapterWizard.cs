using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PromptToScene.Editor
{
    public static class ProjectAdapterWizard
    {
        [Serializable] class Provider { public string target, name, type; public bool compatible; public string[] quantity, health, max_health, commit; }
        [Serializable] class Scan { public string flow_id; public Provider[] providers; }
        [Serializable] class Receipt { public string path, flow_id, target, component; public bool ready, compilation_failed; }
        [Serializable] class Mapping { public string quantity, health, max_health, commit; }
        [Serializable] class Plan { public string flow_id, adapter_id, name; public Provider provider; public Mapping mapping; }
        static string Target(MonoBehaviour c) => GlobalObjectId.GetGlobalObjectIdSlow(c).ToString();
        static Provider Describe(MonoBehaviour c)
        {
            var t = c.GetType(); var methods = t.GetMethods(BindingFlags.Instance | BindingFlags.Public);
            Func<MethodInfo,Type[],bool> args = (m, a) => !m.IsGenericMethod && m.GetParameters().Select(p => p.ParameterType).SequenceEqual(a);
            var health = t.GetFields(BindingFlags.Instance|BindingFlags.Public).Where(f=>f.FieldType==typeof(float)).Select(f=>f.Name)
                .Concat(t.GetProperties(BindingFlags.Instance|BindingFlags.Public).Where(p=>p.PropertyType==typeof(float)&&p.GetGetMethod()!=null&&p.GetIndexParameters().Length==0).Select(p=>p.Name)).ToArray();
            return new Provider { target=Target(c), name=c.gameObject.name, type=t.FullName, compatible=c is IGameProjectAdapter,
                quantity=methods.Where(m=>m.ReturnType==typeof(int)&&args(m,new[]{typeof(string)})).Select(m=>m.Name).Distinct().ToArray(), health=health, max_health=health,
                commit=methods.Where(m=>m.ReturnType==typeof(bool)&&args(m,new[]{typeof(ItemQuantity[]),typeof(ItemQuantity[]),typeof(float)})).Select(m=>m.Name).Distinct().ToArray() };
        }
        static DevelopmentResult Result(object value, string message) => new DevelopmentResult {command="adapter_wizard",passed=true,message=message,plan_json=JsonUtility.ToJson(value)};
        static void Identifier(string s) { if(!System.Text.RegularExpressions.Regex.IsMatch(s??"", "^[A-Za-z_][A-Za-z0-9_]*$")) throw new Exception("Invalid C# identifier"); }
        public static DevelopmentResult Execute(DevelopmentCommand command)
        {
            var p=JsonUtility.FromJson<Plan>(command.content_json);
            if(command.mode=="inspect") {
                var selected=Selection.gameObjects.SelectMany(g=>g.GetComponents<MonoBehaviour>()).Where(c=>c).Distinct().ToArray();
                if(selected.Any(c=>string.IsNullOrEmpty(c.gameObject.scene.path))) throw new Exception("Save the scene before inspecting project systems");
                return Result(new Scan{flow_id=p.flow_id,providers=selected.Select(Describe).ToArray()}, "Selected project APIs inspected");
            }
            if(command.mode=="starter") {
                Identifier(p.name); string folder="Assets/PromptToScene/Adapters/"+p.name; Directory.CreateDirectory(folder);
                string file=folder+"/"+p.name+".cs"; if(File.Exists(file)) throw new Exception("Adapter source already exists");
                File.WriteAllText(file,"using UnityEngine;\nusing PromptToScene;\n// Connect your public inventory API. Commit every cost/reward/heal atomically.\npublic sealed class "+p.name+" : MonoBehaviour, IGameProjectAdapter {\n public int GetQuantity(string id) => 0;\n public float Health => 0;\n public float MaxHealth => 100;\n // Reject until the actual project transaction is implemented.\n public bool TryCommit(ItemQuantity[] costs, ItemQuantity[] rewards, float heal) => false;\n}\n");
                AssetDatabase.Refresh(); return Result(new Receipt {path=file},"Editable adapter starter created; implement its project API before binding");
            }
            if(!GlobalObjectId.TryParse(p.provider.target,out var id)) throw new Exception("Invalid provider identity");
            var provider=GlobalObjectId.GlobalObjectIdentifierToObjectSlow(id) as MonoBehaviour;
            if(!provider || provider.GetType().FullName!=p.provider.type) throw new Exception("Selected provider changed; inspect it again");
            string className="PTSAdapter"+p.adapter_id; Identifier(className);
            var live=Describe(provider);
            if(!p.provider.compatible) {
                if(!live.quantity.Contains(p.mapping.quantity)||!live.health.Contains(p.mapping.health)||!live.max_health.Contains(p.mapping.max_health)||!live.commit.Contains(p.mapping.commit)) throw new Exception("Public provider APIs changed; revise the mapping");
                foreach(var s in new[]{p.mapping.quantity,p.mapping.health,p.mapping.max_health,p.mapping.commit}) Identifier(s);
            }
            if(command.mode=="install") {
                if(!provider.GetType().IsVisible||provider.GetType().IsGenericType||provider.GetType().IsNested) throw new Exception("Use a public non-nested MonoBehaviour provider type");
                string folder="Assets/PromptToScene/Adapters/"+className; Directory.CreateDirectory(folder);
                string type="global::"+provider.GetType().FullName;
                string code="using UnityEngine;\nusing PromptToScene;\n// Generated forwarding adapter; the project owns its data and atomic commit.\npublic sealed class "+className+" : MonoBehaviour, IGameProjectAdapter {\n public "+type+" source;\n public int GetQuantity(string id) => source ? source."+p.mapping.quantity+"(id) : 0;\n public float Health => source ? source."+p.mapping.health+" : 0;\n public float MaxHealth => source ? source."+p.mapping.max_health+" : 1;\n public bool TryCommit(ItemQuantity[] costs, ItemQuantity[] rewards, float heal) => source && source."+p.mapping.commit+"(costs,rewards,heal);\n}\n";
                string file=folder+"/"+className+".cs"; if(File.Exists(file)&&File.ReadAllText(file)!=code) throw new Exception("Generated adapter was edited; preserve it and prepare another adapter");
                File.WriteAllText(file,code); AssetDatabase.Refresh(); return Result(new Receipt {path=file},"Adapter source generated; waiting for Unity compilation");
            }
            if(command.mode=="ready") {
                bool compiled=AppDomain.CurrentDomain.GetAssemblies().Any(a=>a.GetType(className)!=null);
                return Result(new Receipt{ready=compiled,compilation_failed=EditorUtility.scriptCompilationFailed},"Adapter compilation status");
            }
            if(command.mode!="bind") throw new Exception("Unknown adapter wizard operation");
            MonoBehaviour component=provider;
            if(!p.provider.compatible) {
                var type=AppDomain.CurrentDomain.GetAssemblies().Select(a=>a.GetType(className)).FirstOrDefault(t=>t!=null);
                if(type==null) throw new Exception("Adapter has not compiled. Resolve Unity Console errors, then resume this task");
                component=provider.GetComponent(type) as MonoBehaviour ?? Undo.AddComponent(provider.gameObject,type) as MonoBehaviour;
                Undo.RecordObject(component,"Bind generated project adapter"); type.GetField("source").SetValue(component,provider); EditorUtility.SetDirty(component);
            }
            if(!(component is IGameProjectAdapter)) throw new Exception("Provider no longer implements IGameProjectAdapter");
            var session=DevelopmentActions.Loaded<GameSession>().SingleOrDefault(s=>s.definition&&s.definition.settings.flow_id==p.flow_id);
            if(!session) throw new Exception("Attach the flow to this scene first");
            Undo.RecordObject(session,"Bind project system"); session.projectAdapter=component; EditorUtility.SetDirty(session); EditorSceneManager.MarkSceneDirty(session.gameObject.scene);
            return Result(new Receipt {flow_id=p.flow_id,target=Target(component),component=component.GetType().FullName},"Project inventory/health adapter bound");
        }
    }
}
