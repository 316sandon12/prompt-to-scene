using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

public static class UnityWorkflow
{
    [Serializable] class Command { public string operation, asset_id; }
    static string Root => AssetBridge.StateRoot;
    static double deadline, next;
    public static void Run()
    {
        EditorSceneManager.OpenScene("Assets/Smoke.unity");
        var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
        floor.name = "Workflow fixture floor";
        floor.transform.position = new Vector3(0,.5f,0);
        floor.transform.localScale = new Vector3(30,1,30);
        Physics.SyncTransforms();
        deadline = EditorApplication.timeSinceStartup + 400;
        EditorApplication.update += Tick;
        File.WriteAllText(Path.Combine(Root,"workflow-ready"), "ready");
    }
    static void Tick()
    {
        if (EditorApplication.timeSinceStartup < next) return;
        next = EditorApplication.timeSinceStartup + .3;
        try
        {
            if (EditorApplication.timeSinceStartup > deadline) throw new Exception("Workflow timeout");
            AssetBridge.ImportPending();
            string path = Path.Combine(Root,"workflow-command.json");
            if (!File.Exists(path)) return;
            var command = JsonUtility.FromJson<Command>(File.ReadAllText(path));
            File.Delete(path);
            if (command.operation == "stop") { EditorApplication.Exit(0); return; }
            var source = Object.FindObjectsOfType<AssetIdentity>().First(a => a.assetId == command.asset_id);
            if (command.operation == "duplicate")
            {
                var copy = (GameObject)PrefabUtility.InstantiatePrefab(PrefabUtility.GetCorrespondingObjectFromSource(source.gameObject));
                copy.transform.position = source.transform.position + new Vector3(3,0,0);
                Selection.activeGameObject = source.gameObject;
            }
            if (command.operation == "check")
            {
                foreach (var obj in Object.FindObjectsOfType<AssetIdentity>().Where(a => a.assetId == command.asset_id))
                    if (obj.GetComponent<BoxCollider>() != null) throw new Exception("collider=false lost on revision/restore");
            }
            File.WriteAllText(Path.Combine(Root,"workflow-command-done"), "done");
        }
        catch (Exception error)
        {
            File.WriteAllText(Path.Combine(Root,"workflow-error.txt"), error.ToString());
            EditorApplication.Exit(1);
        }
    }
}
