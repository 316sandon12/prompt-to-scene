// Native read-only scene-contract check. Runs only in the dedicated disposable fixture.
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using PromptToScene;
using PromptToScene.Editor;

public static class UnitySceneContext
{
    public static void Run()
    {
        try
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var target = GameObject.CreatePrimitive(PrimitiveType.Cube);
            target.name = "Measured blockout";
            target.transform.localScale = new Vector3(2, 1, .5f);
            var identity = target.AddComponent<AssetIdentity>(); identity.assetId = "blockout";
            var camera = new GameObject("Player camera").AddComponent<Camera>();
            camera.tag = "MainCamera"; camera.transform.position = new Vector3(0, 1, -10);
            camera.fieldOfView = 60; camera.aspect = 2;
            Selection.activeGameObject = target;
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(), "Assets/SceneContext.unity");
            var execute = typeof(SceneActions).GetMethod("Execute", BindingFlags.NonPublic | BindingFlags.Static);
            var result = (SceneResult)execute.Invoke(null, new object[] {
                new SceneAction {operation="inspect",scope="selected",request_id=new string('a',32)} });
            if (result.cameras.Length != 1 || !result.cameras[0].primary || !result.cameras[0].projection_supported)
                throw new Exception("Camera selection/projection unavailable");
            if (Mathf.Abs(result.cameras[0].vertical_fov-60)>.001f || Mathf.Abs(result.cameras[0].aspect-2)>.001f)
                throw new Exception("Camera intrinsics changed");
            if (Mathf.Abs(result.selected_context[0].bounds_max[0]-result.selected_context[0].bounds_min[0]-2)>.001f)
                throw new Exception("Bounds must use metres");
            File.WriteAllText(Path.Combine(Application.dataPath,"../scene-context-result.json"), JsonUtility.ToJson(result,true));
            camera.orthographic=true;camera.orthographicSize=3;
            result=(SceneResult)execute.Invoke(null,new object[]{new SceneAction {operation="inspect",scope="selected"}});
            if (!result.cameras[0].orthographic || Mathf.Abs(result.cameras[0].ortho_height_m-6)>.001f)
                throw new Exception("Orthographic height must use metres");
            Debug.Log("PTS SCENE CONTEXT PASS: measured bounds, perspective, orthographic, primary camera");
            EditorApplication.Exit(0);
        }
        catch(Exception error){Debug.LogException(error);EditorApplication.Exit(1);}
    }
}
