using System;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using PromptToScene.Editor;

[InitializeOnLoad] public static class UnityPipelineSmoke
{
    [Serializable] class Command {public string operation,plan_id;}
    static string Root=>AssetBridge.StateRoot;
    static UnityPipelineSmoke(){EditorApplication.update+=Tick;}
    public static void Run()
    {
        EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects,NewSceneMode.Single);
        Directory.CreateDirectory(Path.Combine(AssetBridge.ProjectRoot,"Assets/PipelineSmoke"));AssetDatabase.Refresh();
        var shader=Shader.Find(AssetBridge.Pipeline.Contains("Universal")?"Universal Render Pipeline/Lit":"Standard");
        var reference=new Material(shader);reference.color=new Color(.8f,.25f,.12f);reference.SetFloat(reference.HasProperty("_Smoothness")?"_Smoothness":"_Glossiness",.25f);reference.mainTextureScale=new Vector2(2,2);
        AssetDatabase.CreateAsset(reference,"Assets/PipelineSmoke/Reference.mat");
        for(int i=0;i<2;i++)
        {
            var material=new Material(shader);material.color=Color.blue;material.SetFloat(material.HasProperty("_Smoothness")?"_Smoothness":"_Glossiness",.8f);
            AssetDatabase.CreateAsset(material,"Assets/PipelineSmoke/Original"+i+".mat");
            var obj=GameObject.CreatePrimitive(i==0?PrimitiveType.Cube:PrimitiveType.Sphere);obj.GetComponent<Renderer>().sharedMaterial=material;
            PrefabUtility.SaveAsPrefabAsset(obj,"Assets/PipelineSmoke/Prop"+i+".prefab");UnityEngine.Object.DestroyImmediate(obj);
        }
        AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),"Assets/PipelineSmoke/Scene.unity");
        WorkshopWindow.Open();SessionState.SetBool("PTS.PipelineSmoke",true);
        File.WriteAllText(Path.Combine(Root,"pipeline-ready"),"ready");
    }
    static void Tick()
    {
        if(!SessionState.GetBool("PTS.PipelineSmoke",false)||EditorApplication.isCompiling)return;
        AssetBridge.ImportPending();
        string path=Path.Combine(Root,"pipeline-command.json");if(!File.Exists(path))return;
        try
        {
            var c=JsonUtility.FromJson<Command>(File.ReadAllText(path));File.Delete(path);
            if(c.operation=="stop"){EditorSceneManager.SaveOpenScenes();EditorApplication.Exit(0);return;}
            if(c.operation=="verify_apply"||c.operation=="verify_undo")
            {
                var first=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/PipelineSmoke/Prop0.prefab").GetComponent<Renderer>().sharedMaterial;
                var second=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/PipelineSmoke/Prop1.prefab").GetComponent<Renderer>().sharedMaterial;
                var reference=AssetDatabase.LoadAssetAtPath<Material>("Assets/PipelineSmoke/Reference.mat");
                if(c.operation=="verify_apply" && (first.color!=reference.color || first.mainTextureScale!=reference.mainTextureScale))throw new Exception("Reference parameters were not copied");
                if(second.color!=Color.blue)throw new Exception("Unselected target changed");
                if(c.operation=="verify_undo"&&first.color!=Color.blue)throw new Exception("Original assignment was not restored");
                if(reference.color.b!=.12f)throw new Exception("Reference was modified");
            }
            File.WriteAllText(Path.Combine(Root,"pipeline-command-done"),"done");
        }
        catch(Exception error){File.WriteAllText(Path.Combine(Root,"pipeline-error.txt"),error.ToString());}
    }
}
