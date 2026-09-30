using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

public static class UnityAuthoring
{
    [Serializable] class Command { public string operation, asset_id; }
    [Serializable] class MaterialReference { public string path, file; }
    [Serializable] class GeometryEvidence { public int[] triangles; public int colliders; }
    [Serializable] class GeometryReceipt { public int triangles, lod_count, collision_count; }
    static string Root => AssetBridge.StateRoot;
    static double deadline,next;
    public static void Run()
    {
        EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects,NewSceneMode.Single);
        var floor=GameObject.CreatePrimitive(PrimitiveType.Cube);
        floor.name="Authoring fixture floor";
        floor.transform.position=new Vector3(0,-.5f,0); floor.transform.localScale=new Vector3(100,1,100);
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),"Assets/AuthoringSmoke.unity");
        Physics.SyncTransforms(); deadline=EditorApplication.timeSinceStartup+1800;
        EditorApplication.update+=Tick; File.WriteAllText(Path.Combine(Root,"authoring-ready"),"ready");
    }
    static void Tick()
    {
        if(EditorApplication.timeSinceStartup<next)return;next=EditorApplication.timeSinceStartup+.3;
        try
        {
            if(EditorApplication.timeSinceStartup>deadline)throw new Exception("Authoring timeout");
            AssetBridge.ImportPending();
            string path=Path.Combine(Root,"authoring-command.json");if(!File.Exists(path))return;
            var command=JsonUtility.FromJson<Command>(File.ReadAllText(path));File.Delete(path);
            if(command.operation=="stop"){EditorApplication.Exit(0);return;}
            var targets=Object.FindObjectsOfType<AssetIdentity>().Where(a=>command.operation=="select_all"?a.assetId.StartsWith(command.asset_id):a.assetId==command.asset_id).ToArray();
            if(targets.Length==0)throw new Exception("Fixture asset missing");
            if(command.operation=="select"||command.operation=="select_all")Selection.objects=targets.Select(t=>t.gameObject).ToArray();
            if(command.operation=="check")
            {
                var materials=targets.SelectMany(t=>t.GetComponentsInChildren<Renderer>()).SelectMany(r=>r.sharedMaterials).Distinct();
                foreach(var material in materials)
                {
                    if(material.GetTexture("_BumpMap")==null||material.GetTexture("_MetallicGlossMap")==null)throw new Exception("Baked PBR map missing in Unity");
                    var texture=material.GetTexture("_MetallicGlossMap");
                    if(((TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(texture))).sRGBTexture)throw new Exception("Unity mask is incorrectly sRGB");
                }
            }
            if(command.operation=="check_preparation")
            {
                var receipt=JsonUtility.FromJson<GeometryReceipt>(File.ReadAllText(Path.Combine(Root,"receipts",command.asset_id+".json")));
                var group=targets[0].GetComponentInChildren<LODGroup>();
                var levels=group ? group.GetLODs() : new[]{new LOD(0,targets[0].GetComponentsInChildren<Renderer>())};
                if(levels.Length!=receipt.lod_count)throw new Exception("Native LOD count mismatch");
                var counts=levels.Select(l=>l.renderers.Sum(r=>r.GetComponent<MeshFilter>().sharedMesh.triangles.Length/3)).ToArray();
                if(counts[0]!=receipt.triangles)throw new Exception("LOD0 geometry mismatch");
                for(int i=1;i<counts.Length;i++)if(counts[i]>=counts[i-1])throw new Exception("Native LOD does not reduce geometry");
                var collisions=targets[0].GetComponentsInChildren<Collider>();
                if(collisions.Length!=receipt.collision_count)throw new Exception("Native collision count mismatch");
                Physics.SyncTransforms();
                foreach(var collider in collisions)
                {
                    var center=collider.bounds.center;
                    var ray=new Ray(center+Vector3.up*(collider.bounds.extents.y+1),Vector3.down);
                    if(!collider.Raycast(ray,out _,100))throw new Exception("Cooked collider cannot be hit");
                }
                File.WriteAllText(Path.Combine(Root,"preparation-native.json"),JsonUtility.ToJson(new GeometryEvidence{triangles=counts,colliders=collisions.Length}));
            }
            if(command.operation=="capture_material")
            {
                var material=targets[0].GetComponentsInChildren<Renderer>().SelectMany(r=>r.sharedMaterials).First(m=>m.name=="Wood");
                var materialPath=AssetDatabase.GetAssetPath(material);
                File.WriteAllText(Path.Combine(Root,"authoring-material.json"),JsonUtility.ToJson(new MaterialReference{path=materialPath,file=Path.Combine(AssetBridge.ProjectRoot,materialPath)}));
            }
            if(command.operation=="check_reuse")
            {
                var reference=JsonUtility.FromJson<MaterialReference>(File.ReadAllText(Path.Combine(Root,"authoring-material.json")));
                if(!targets[0].GetComponentsInChildren<Renderer>().SelectMany(r=>r.sharedMaterials).Any(m=>AssetDatabase.GetAssetPath(m)==reference.path))throw new Exception("Existing material was not reused");
            }
            File.WriteAllText(Path.Combine(Root,"authoring-command-done"),"done");
        }
        catch(Exception error){File.WriteAllText(Path.Combine(Root,"authoring-error.txt"),error.ToString());EditorApplication.Exit(1);}
    }
}
