using System;
using System.IO;
using System.Linq;
using System.Reflection;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object=UnityEngine.Object;

[InitializeOnLoad]
public static class UnityProduction
{
    [Serializable] class Command {public string operation,asset_id;}
    static string Root=>AssetBridge.StateRoot;
    static double next;
    static UnityProduction(){EditorApplication.update+=Tick;}
    static void Require(bool value,string reason){if(!value)throw new Exception(reason);}
    public static void Run()
    {
        typeof(UnitySmoke).GetMethod("ConfigurePipeline",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,null);
        EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects,NewSceneMode.Single);
        Camera.main.transform.position=new Vector3(7,8,-7);Camera.main.transform.LookAt(Vector3.up);
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),"Assets/ProductionSmoke.unity");
        SessionState.SetBool("PTS.ProductionSmoke",true);
        Directory.CreateDirectory(Root);File.WriteAllText(Path.Combine(Root,"production-ready"),"ready");
    }
    public static void Existing()
    {
        EditorSceneManager.OpenScene("Assets/ProductionSmoke.unity");
        Camera.main.aspect=16f/9f;
        SessionState.SetBool("PTS.ProductionSmoke",true);
        Directory.CreateDirectory(Root);File.WriteAllText(Path.Combine(Root,"production-ready"),"ready");
    }
    static void Tick()
    {
        if(!SessionState.GetBool("PTS.ProductionSmoke",false)||EditorApplication.isPlayingOrWillChangePlaymode||EditorApplication.timeSinceStartup<next)return;
        next=EditorApplication.timeSinceStartup+.15;
        try
        {
            AssetBridge.ImportPending();
            var path=Path.Combine(Root,"production-command.json");if(!File.Exists(path))return;
            var c=JsonUtility.FromJson<Command>(File.ReadAllText(path));File.Delete(path);
            if(c.operation=="stop"){SessionState.SetBool("PTS.ProductionSmoke",false);EditorApplication.Exit(0);return;}
            var obj=DevelopmentActions.Assets(c.asset_id).FirstOrDefault();
            if(c.operation=="lens"){Camera.main.fieldOfView=90;Camera.main.aspect=4f/3f;}
            if(c.operation=="camera")
            {
                Require(obj,"Missing capture subject");var rs=obj.GetComponentsInChildren<Renderer>();var bounds=rs[0].bounds;
                foreach(var r in rs.Skip(1))bounds.Encapsulate(r.bounds);
                Camera.main.transform.position=bounds.center+new Vector3(1.4f,1.1f,-2.7f)*Mathf.Max(1,bounds.extents.magnitude);
                Camera.main.transform.LookAt(bounds.center);EditorSceneManager.SaveOpenScenes();
            }
            if(c.operation=="materials")
            {
                var materials=obj.GetComponentsInChildren<Renderer>().SelectMany(r=>r.sharedMaterials).Distinct().ToArray();
                var glow=materials.Single(m=>m.name=="ProbeEmission");
                var cutout=materials.Single(m=>m.name=="ProbeMask");
                var glass=materials.Single(m=>m.name=="ProbeBlend");
                foreach(var m in materials)Require(!ShaderUtil.ShaderHasError(m.shader),"Shader compile error: "+m.shader.name);
                Require(glow.IsKeywordEnabled("_EMISSION")&&glow.GetColor("_EmissionColor").maxColorComponent>1,"Emission lost");
                Require(cutout.IsKeywordEnabled("_ALPHATEST_ON")&&cutout.renderQueue==2450&&cutout.GetFloat("_Cull")==0,"Cutout or two-sided mode lost");
                Require(glass.renderQueue==3000&&glass.GetFloat("_ZWrite")==0,"Transparent state lost");
                Require(Mathf.Abs(glass.color.a-.3f)<.01f,"Opacity lost");
                var texture=cutout.GetTexture(AssetBridge.Pipeline.Contains("Universal")?"_BaseMap":"_MainTex") as Texture2D;
                Require(texture&&((TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(texture))).DoesSourceTextureHaveAlpha(),"Packed opacity missing");
            }
            if(c.operation=="hooks")
            {
                var interaction=obj.GetComponent<Interaction>();
                Require(interaction&&interaction.eventId=="ore_mined"&&interaction.usesRequired==3,"Game hooks lost");
                Require(interaction.depletedVisual&&!interaction.depletedVisual.activeSelf,"Depleted prefab missing");
            }
            File.WriteAllText(Path.Combine(Root,"production-command-done"),"done");
        }
        catch(Exception error){File.WriteAllText(Path.Combine(Root,"production-error.txt"),error.ToString());SessionState.SetBool("PTS.ProductionSmoke",false);EditorApplication.Exit(1);}
    }
}
