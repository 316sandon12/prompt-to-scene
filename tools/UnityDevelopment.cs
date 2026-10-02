using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class UnityDevelopment
{
    [Serializable] class Command {public string operation,asset_id;}
    static string Root=>AssetBridge.StateRoot;
    static double next;
    static UnityDevelopment(){EditorApplication.update+=Tick;}
    public static void Run()
    {
        EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects,NewSceneMode.Single);
        var floor=GameObject.CreatePrimitive(PrimitiveType.Cube);floor.name="Development floor";
        floor.transform.position=new Vector3(10,-.1f,10);floor.transform.localScale=new Vector3(80,.2f,80);
        var ground=new Material(Shader.Find(AssetBridge.Pipeline.Contains("Universal")?"Universal Render Pipeline/Lit":"Standard"));ground.color=new Color(.32f,.34f,.37f);floor.GetComponent<Renderer>().sharedMaterial=ground;
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),"Assets/DevelopmentSmoke.unity");
        SessionState.SetBool("PTS.DevelopmentSmoke",true);
        File.WriteAllText(Path.Combine(Root,"development-ready"),"ready");
    }
    public static void Probe()
    {
        var path=AssetDatabase.FindAssets("t:Prefab",new[]{"Assets/PromptToScene"}).Select(AssetDatabase.GUIDToAssetPath).Where(p=>p.EndsWith("_door_moving.prefab")).OrderBy(p=>p).Last();
        var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(path);
        var data=new SceneResult{objects=prefab.GetComponentsInChildren<MeshFilter>().Select(m=>new SceneObject{name=m.name,position=DevelopmentActions.Vec(m.transform.TransformPoint(m.sharedMesh.bounds.center))}).ToArray()};
        File.WriteAllText(Path.Combine(Root,"development-axis.json"),JsonUtility.ToJson(data,true));
    }
    static void Tick()
    {
        if(!SessionState.GetBool("PTS.DevelopmentSmoke",false)||EditorApplication.isPlayingOrWillChangePlaymode||EditorApplication.timeSinceStartup<next)return;
        next=EditorApplication.timeSinceStartup+.15;
        try
        {
            AssetBridge.ImportPending();
            string path=Path.Combine(Root,"development-command.json");if(!File.Exists(path))return;
            var c=JsonUtility.FromJson<Command>(File.ReadAllText(path));File.Delete(path);
            if(c.operation=="stop"){SessionState.SetBool("PTS.DevelopmentSmoke",false);EditorApplication.Exit(0);return;}
            if(c.operation=="material")
            {
                var material=new Material(Shader.Find(AssetBridge.Pipeline.Contains("Universal")?"Universal Render Pipeline/Lit":"Standard"));material.color=Color.cyan;
                AssetDatabase.CreateAsset(material,"Assets/PTS_Custom.mat");AssetDatabase.SaveAssets();
            }
            if(c.operation=="block")
            {var level=UnityEngine.Object.FindObjectOfType<LevelMarker>();var cube=GameObject.CreatePrimitive(PrimitiveType.Cube);cube.name="PTS Blocker";cube.transform.position=level.checkpoints[0]+Vector3.up*.9f;cube.transform.localScale=new Vector3(1,1.8f,1);Physics.SyncTransforms();}
            if(c.operation=="unblock"){UnityEngine.Object.DestroyImmediate(GameObject.Find("PTS Blocker"));Physics.SyncTransforms();}
            if(c.operation=="check_preserved")
            {
                var obj=DevelopmentActions.Assets(c.asset_id).Single();
                if(!obj.GetComponent<Interaction>()||obj.GetComponent<Interaction>().interactionRange!=3.5f)throw new Exception("Interaction config lost");
                if(!obj.GetComponentsInChildren<AttachmentPoint>().Any(s=>s.socketName=="handle"))throw new Exception("Socket lost");
                if(!obj.GetComponentsInChildren<Renderer>().Any(r=>r.sharedMaterials.Any(m=>AssetDatabase.GetAssetPath(m)=="Assets/PTS_Custom.mat")))throw new Exception("Material override lost");
            }
            if(c.operation=="check_restored")
            {if(UnityEngine.Object.FindObjectOfType<SceneLook>())throw new Exception("Look rig not removed");if(!GameObject.Find("Directional Light").GetComponent<Light>().enabled)throw new Exception("Original light not restored");}
            File.WriteAllText(Path.Combine(Root,"development-command-done"),"done");
        }
        catch(Exception error){File.WriteAllText(Path.Combine(Root,"development-error.txt"),error.ToString());SessionState.SetBool("PTS.DevelopmentSmoke",false);EditorApplication.Exit(1);}
    }
}
