using System;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using PromptToScene.Editor;

[InitializeOnLoad]
public static class UnityOrganization
{
    [Serializable] class Config { public string folder, destination, plan_id, operation; public bool fresh; }
    [Serializable] class Fixture { public string material, texture, mesh, prefab, scene; }
    static string Root=>AssetBridge.StateRoot;
    static Config config;
    static Fixture fixture;
    static string cancelPlan;
    static UnityOrganization(){EditorApplication.update+=Tick;}
    static void Folder(string path){if(AssetDatabase.IsValidFolder(path))return;Folder(Path.GetDirectoryName(path).Replace('\\','/'));AssetDatabase.CreateFolder(Path.GetDirectoryName(path).Replace('\\','/'),Path.GetFileName(path));}
    static string Guid(string path)=>AssetDatabase.AssetPathToGUID(path);
    public static void Run()
    {
        config=JsonUtility.FromJson<Config>(File.ReadAllText(Path.Combine(Root,"organization-fixture.json")));
        if(config.fresh)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            Folder(config.folder+"/PackA");Folder(config.folder+"/PackB");Folder(config.folder+"/Resources");Folder(config.destination+"/Materials");
            var texture=new Texture2D(2,2);texture.SetPixels(new[]{Color.white,Color.red,Color.green,Color.blue});texture.Apply();
            var texturePath=config.folder+"/PackA/oak albedo.png";File.WriteAllBytes(texturePath,texture.EncodeToPNG());UnityEngine.Object.DestroyImmediate(texture);AssetDatabase.ImportAsset(texturePath);
            var material=new Material(Shader.Find(AssetBridge.Pipeline.Contains("Universal")?"Universal Render Pipeline/Lit":"Standard"));
            material.mainTexture=AssetDatabase.LoadAssetAtPath<Texture>(texturePath);
            var matPath=config.folder+"/PackA/oak.mat";AssetDatabase.CreateAsset(material,matPath);
            AssetDatabase.CreateAsset(new Material(material),config.folder+"/PackB/oak.mat");
            AssetDatabase.CreateAsset(new Material(material),config.destination+"/Materials/M_Oak.mat");
            AssetDatabase.CreateAsset(new Material(material),config.folder+"/Resources/runtime.mat");
            File.WriteAllText(config.folder+"/settings.json","{}");AssetDatabase.ImportAsset(config.folder+"/settings.json");
            var cube=GameObject.CreatePrimitive(PrimitiveType.Cube);cube.name="organization reference";
            var mesh=UnityEngine.Object.Instantiate(cube.GetComponent<MeshFilter>().sharedMesh);
            var meshPath=config.folder+"/PackA/cube shape.asset";AssetDatabase.CreateAsset(mesh,meshPath);
            cube.GetComponent<MeshFilter>().sharedMesh=mesh;cube.GetComponent<MeshRenderer>().sharedMaterial=material;
            var prefabPath=config.folder+"/PackA/my prefab.prefab";PrefabUtility.SaveAsPrefabAsset(cube,prefabPath);UnityEngine.Object.DestroyImmediate(cube);
            PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath));
            AssetDatabase.CreateAsset(new AnimationClip(),config.folder+"/walk.anim");
            for(int i=0;i<9;i++)AssetDatabase.CreateAsset(new Material(material),config.folder+"/extra_"+i+".mat");
            fixture=new Fixture{material=Guid(matPath),texture=Guid(texturePath),mesh=Guid(meshPath),prefab=Guid(prefabPath),scene=config.folder+"_Reference.unity"};
            AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),fixture.scene);
            File.WriteAllText(Path.Combine(Root,"organization-fixture-assets.json"),JsonUtility.ToJson(fixture,true));
        }
        else
        {
            fixture=JsonUtility.FromJson<Fixture>(File.ReadAllText(Path.Combine(Root,"organization-fixture-assets.json")));
            EditorSceneManager.OpenScene(fixture.scene);
        }
        File.WriteAllText(Path.Combine(Root,"organization-ready"),"ready");
    }
    static void Check(bool moved)
    {
        string prefix=moved?config.destination:config.folder;
        foreach(var id in new[]{fixture.material,fixture.texture,fixture.mesh,fixture.prefab})
            if(!AssetDatabase.GUIDToAssetPath(id).StartsWith(prefix+"/"))throw new Exception("Native GUID/path mismatch: "+id);
        var mat=AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(fixture.material));
        if(Guid(AssetDatabase.GetAssetPath(mat.mainTexture))!=fixture.texture)throw new Exception("Texture reference lost");
        var obj=GameObject.Find("my prefab")??GameObject.Find("organization reference");
        if(!obj)obj=UnityEngine.Object.FindObjectsOfType<MeshRenderer>().Single().gameObject;
        if(Guid(AssetDatabase.GetAssetPath(obj.GetComponent<MeshRenderer>().sharedMaterial))!=fixture.material)throw new Exception("Scene material reference lost");
        if(Guid(AssetDatabase.GetAssetPath(obj.GetComponent<MeshFilter>().sharedMesh))!=fixture.mesh)throw new Exception("Scene mesh reference lost");
        if(Guid(PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(obj))!=fixture.prefab)throw new Exception("Prefab link lost");
        if(!AssetDatabase.LoadAssetAtPath<Material>(config.folder+"/Resources/runtime.mat"))throw new Exception("Resources asset moved");
    }
    static void Tick()
    {
        if(config==null)return;
        try
        {
            if(cancelPlan!=null)
            {
                var journalPath=Path.Combine(Root,"organization","journals",cancelPlan+".json");
                if(File.Exists(journalPath))
                {
                    var journal=JsonUtility.FromJson<OrganizationJournal>(File.ReadAllText(journalPath));
                    if(journal.events.Count>0 && journal.status=="applying")
                        foreach(var receiptPath in Directory.GetFiles(Path.Combine(Root,"action-receipts"),"*.json"))
                        {
                            var receipt=JsonUtility.FromJson<SceneResult>(File.ReadAllText(receiptPath));
                            if(receipt.status=="queued" && receipt.development?.plan_id==cancelPlan)
                            {Directory.CreateDirectory(Path.Combine(Root,"cancel"));File.WriteAllText(Path.Combine(Root,"cancel",receipt.request_id),"cancel after native moves");cancelPlan=null;break;}
                        }
                }
            }
            AssetBridge.ImportPending();
            var path=Path.Combine(Root,"organization-command.json");if(!File.Exists(path))return;
            var c=JsonUtility.FromJson<Config>(File.ReadAllText(path));File.Delete(path);
            if(c.operation=="cancel_after_moves")cancelPlan=c.plan_id;
            if(c.operation=="check_moved")Check(true);
            if(c.operation=="check_restored")Check(false);
            if(c.operation=="mutate")
            {var mat=AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(fixture.material));mat.color=Color.cyan;EditorUtility.SetDirty(mat);AssetDatabase.SaveAssets();}
            if(c.operation=="block_undo")
            {var material=new Material(Shader.Find("Standard"));AssetDatabase.CreateAsset(material,config.folder+"/PackA/oak.mat");AssetDatabase.SaveAssets();}
            if(c.operation=="unblock_undo")AssetDatabase.DeleteAsset(config.folder+"/PackA/oak.mat");
            if(c.operation=="save_stop")
            {AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),fixture.scene);EditorApplication.Exit(0);return;}
            File.WriteAllText(Path.Combine(Root,"organization-command-done"),"done");
        }
        catch(Exception error){File.WriteAllText(Path.Combine(Root,"organization-error.txt"),error.ToString());EditorApplication.Exit(1);}
    }
}
