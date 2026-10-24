using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object=UnityEngine.Object;

// Isolated v0.15 verification. Command files live only in the task's disposable project.
[InitializeOnLoad] public static class UnityContinuous
{
    [Serializable] class Command { public string operation; }
    static string Root=>AssetBridge.StateRoot;
    static double next;
    static UnityContinuous(){EditorApplication.update+=Tick;}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Done(string name){File.WriteAllText(Path.Combine(Root,"continuous-"+name),"passed");}
    static void Tick()
    {
        if(EditorApplication.timeSinceStartup<next)return;next=EditorApplication.timeSinceStartup+.3;
        try{
            int phase=SessionState.GetInt("PTS.ContinuousPhase",0);
            if(phase>0){
                if(!EditorApplication.isPlaying)return;
                var session=GameSession.Find("apothecary");if(!session)return;
                if(phase==1){
                    session.Initialize();Need(session.GetQuantity("apothecary_herb")==3&&session.GetQuantity("old_herb")==0,"Old item ID was not migrated");Need(session.IsComplete("collect_herb")&&!session.TryRule("collect_herb"),"Migrated once rule repeated");
                    Need(session.TryRule("collect_bottle")&&session.TryRule("craft_potion"),"Migrated state cannot craft");
                    Need(session.SaveProgress(),"Migrated save failed");
                    string save=Path.Combine(Application.persistentDataPath,"PromptToScene",session.definition.settings.save_key+".json");
                    Need(File.ReadAllText(save+".bak").Contains("old_herb"),"Migration backup missing");
                    Need(session.UseItem("apothecary_potion")&&session.Health==55,"Unsaved travel state setup failed");
                    SessionState.SetInt("PTS.ContinuousPhase",2);SceneManager.LoadScene("ContinuousB");return;
                }
                if(phase==2&&SceneManager.GetActiveScene().name=="ContinuousB"){
                    session.Initialize();Need(session.Health==55&&session.GetQuantity("apothecary_potion")==0&&session.GetQuantity("apothecary_herb")==1,"Cross-scene in-memory state lost");Need(session.IsComplete("collect_herb"),"Cross-scene once flags lost");
                    Done("travel-passed");SessionState.SetInt("PTS.ContinuousPhase",0);EditorApplication.isPlaying=false;return;
                }
                return;
            }
            if(EditorApplication.isPlayingOrWillChangePlaymode)return;
            string file=Path.Combine(Root,"continuous-command.json");if(!File.Exists(file))return;
            var c=JsonUtility.FromJson<Command>(File.ReadAllText(file));File.Delete(file);
            if(c.operation=="provider"){
                var obj=GameObject.Find("Existing inventory")??new GameObject("Existing inventory");if(!obj.GetComponent<FixtureInventory>())obj.AddComponent<FixtureInventory>();
                EditorSceneManager.SaveScene(SceneManager.GetActiveScene(),"Assets/ContinuousA.unity");AssetDatabase.SaveAssets();Selection.activeGameObject=obj;Done("provider-ready");return;
            }
            if(c.operation=="adapter"){
                var session=GameSession.Find("apothecary");Need(session&&session.projectAdapter is IGameProjectAdapter,"Generated adapter was not bound");
                var adapter=(IGameProjectAdapter)session.projectAdapter;var provider=Object.FindObjectOfType<FixtureInventory>();
                Need(adapter.TryCommit(new ItemQuantity[0],new[]{new ItemQuantity{item_id="apothecary_herb",quantity=4}},0),"Adapter did not forward rewards");provider.reject=true;
                Need(!adapter.TryCommit(new[]{new ItemQuantity{item_id="apothecary_herb",quantity=2}},new ItemQuantity[0],30)&&adapter.GetQuantity("apothecary_herb")==4&&adapter.Health==50,"Rejected adapter call mutated project state");
                session.projectAdapter=null;EditorUtility.SetDirty(session);EditorSceneManager.SaveScene(SceneManager.GetActiveScene());Done("adapter-passed");return;
            }
            if(c.operation=="second_scene"){
                EditorSceneManager.SaveScene(SceneManager.GetActiveScene(),"Assets/ContinuousA.unity");EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects,NewSceneMode.Single);EditorSceneManager.SaveScene(SceneManager.GetActiveScene(),"Assets/ContinuousB.unity");Done("second-ready");return;
            }
            if(c.operation=="travel"){
                Need(GameSession.Find("apothecary"),"Flow attach did not create second-scene session");EditorSceneManager.SaveScene(SceneManager.GetActiveScene());EditorSceneManager.OpenScene("Assets/ContinuousA.unity");
                var session=GameSession.Find("apothecary");var s=session.definition.settings;s.autosave=false;s.save_version=2;s.item_aliases=new[]{new SaveAlias{from_id="old_herb",to_id="apothecary_herb"}};s.rule_aliases=new[]{new SaveAlias{from_id="old_collect",to_id="collect_herb"}};
                EditorUtility.SetDirty(session.definition);AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(SceneManager.GetActiveScene());
                EditorBuildSettings.scenes=new[]{new EditorBuildSettingsScene("Assets/ContinuousA.unity",true),new EditorBuildSettingsScene("Assets/ContinuousB.unity",true)};
                string folder=Path.Combine(Application.persistentDataPath,"PromptToScene");Directory.CreateDirectory(folder);
                File.WriteAllText(Path.Combine(folder,s.save_key+".json"),"{\"schema\":1,\"version\":1,\"flow_id\":\"apothecary\",\"save_key\":\""+s.save_key+"\",\"health\":25,\"inventory\":[{\"item_id\":\"old_herb\",\"quantity\":3}],\"completed\":[\"old_collect\"]}");
                SessionState.SetInt("PTS.ContinuousPhase",1);EditorApplication.isPlaying=true;return;
            }
            if(c.operation=="save") {EditorSceneManager.SaveOpenScenes();AssetDatabase.SaveAssets();Done("saved");return;}
            throw new Exception("Unknown continuous smoke operation");
        }catch(Exception error){File.WriteAllText(Path.Combine(Root,"continuous-error.txt"),error.ToString());SessionState.SetInt("PTS.ContinuousPhase",0);EditorApplication.isPlaying=false;}
    }
}
