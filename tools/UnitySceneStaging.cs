// Disposable native regression: actual camera images, temporary geometry, adopt and guarded undo.
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using PromptToScene;
using PromptToScene.Editor;

public static class UnitySceneStaging
{
    static SceneResult Execute(SceneStage plan, char key)
    {
        var action=new SceneAction {request_id=new string(key,32),operation="scene_stage",scope="selected",scene_json=JsonUtility.ToJson(plan)};
        return SceneStaging.Execute(action,EditorSceneManager.GetActiveScene().path);
    }
    public static void Run()
    {
        if(!Application.dataPath.Replace("\\","/").EndsWith("/.local/scene-studio/unity/Assets")) {EditorApplication.Exit(2);return;}
        File.Delete(Path.Combine(Application.dataPath,"../native-error.txt"));
        File.Delete(Path.Combine(Application.dataPath,"../native-pass.txt"));
        try
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            for(int i=0;i<48;i++){var distant=GameObject.CreatePrimitive(PrimitiveType.Cube);distant.transform.position=new Vector3(1000+i*3,0,1000);}
            var target=GameObject.CreatePrimitive(PrimitiveType.Cube);target.name="Counter blockout";
            target.transform.position=new Vector3(0,.5f,0);target.transform.localScale=new Vector3(2,1,1);
            var source=GameObject.CreatePrimitive(PrimitiveType.Cube);source.name="Medicine chest";
            source.transform.position=new Vector3(4,.5f,0);source.AddComponent<AssetIdentity>().assetId="chest";
            target.layer=8;source.layer=8;
            var mat=new Material(Shader.Find("Standard"));mat.color=new Color(.1f,.7f,.3f);
            AssetDatabase.CreateAsset(mat,"Assets/Chest.mat");source.GetComponent<Renderer>().sharedMaterial=mat;
            var light=new GameObject("Sun").AddComponent<Light>();light.type=LightType.Directional;light.transform.eulerAngles=new Vector3(35,-25,0);
            var camera=new GameObject("Player camera").AddComponent<Camera>();camera.tag="MainCamera";
            camera.transform.position=new Vector3(0,3,-6);camera.transform.LookAt(new Vector3(0,.5f,0));camera.aspect=1.5f;
            camera.cullingMask=1<<8;
            Selection.activeGameObject=target;
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),"Assets/SceneStaging.unity");
            AssetBridge.WriteJson(Path.Combine(AssetBridge.StateRoot,"receipts/chest.json"),new SceneResult{request_id=new string('f',32),status="imported"});
            var reference=Execute(new SceneStage{mode="reference"},'a');
            if(reference.selected_context.Length!=1 || reference.materials.Length==0 || !File.Exists(Path.Combine(AssetBridge.StateRoot,reference.preview))) throw new Exception("Reference incomplete");
            if(!reference.materials.Any(m=>m.object_id==SceneLayout.Id(target))) throw new Exception("Nearby material omitted in a larger scene");
            var original=SceneLayout.Describe(source);var anchor=SceneLayout.Describe(target);
            var plan=new SceneStage {mode="before",plan_id=Guid.NewGuid().ToString("N"),scene=reference.scene,asset_id="chest",model_revision=new string('f',32),
                camera_id=reference.reference_camera_id,camera=reference.cameras.Single(c=>c.id==reference.reference_camera_id),
                source=original,target=anchor,replace_target=true,
                placement=new Placement{source_id=original.id,asset_id="chest",expected=original,position=new[]{0f,.5f,0f},rotation=new[]{0f,0f,0f},scale=new[]{1f,1f,1f},bounds_min=new[]{-.5f,0f,-.5f},bounds_max=new[]{.5f,1f,.5f}}};
            var before=Execute(plan,'c');plan.mode="trial";var after=Execute(plan,'d');
            if(source.transform.position.x!=4 || !target.activeSelf || source.GetComponent<Renderer>().forceRenderingOff) throw new Exception("Preview changed source state");
            if(Resources.FindObjectsOfTypeAll<GameObject>().Any(o=>o.name=="Medicine chest" && o!=source)) throw new Exception("Preview geometry leaked");
            if(File.ReadAllBytes(Path.Combine(AssetBridge.StateRoot,before.preview)).SequenceEqual(File.ReadAllBytes(Path.Combine(AssetBridge.StateRoot,after.preview)))) throw new Exception("Preview did not change pixels");
            var pixels=new Texture2D(2,2);pixels.LoadImage(File.ReadAllBytes(Path.Combine(AssetBridge.StateRoot,after.preview)));
            if(!pixels.GetPixels().Any(c=>c.g>c.r*1.5f && c.g>c.b*1.5f)) throw new Exception("Preview lost the source rendering layer/material");
            UnityEngine.Object.DestroyImmediate(pixels);
            plan.mode="adopt";Execute(plan,'e');
            if(source.transform.position.x!=0 || target.activeSelf) throw new Exception("Adoption failed");
            plan.mode="undo";source.transform.position+=Vector3.right;
            bool refused=false;try{Execute(plan,'1');}catch(Exception){refused=true;}
            if(!refused) throw new Exception("Stale undo was not rejected");
            source.transform.position-=Vector3.right;Execute(plan,'2');
            if(source.transform.position.x!=4 || !target.activeSelf || source.GetComponent<Renderer>().sharedMaterial!=mat) throw new Exception("Undo lost source state");
            File.WriteAllText(Path.Combine(Application.dataPath,"../native-pass.txt"),"reference pixels; temporary meshes cleaned; actual changed render; adopt; stale undo rejection; source and placeholder restored");
            File.WriteAllText(Path.Combine(Application.dataPath,"../scene-reference.json"),JsonUtility.ToJson(reference,true));
            Debug.Log("PTS SCENE STAGING PASS");EditorApplication.Exit(0);
        }
        catch(Exception e){File.WriteAllText(Path.Combine(Application.dataPath,"../native-error.txt"),e.ToString());Debug.LogException(e);EditorApplication.Exit(1);}
    }
}
