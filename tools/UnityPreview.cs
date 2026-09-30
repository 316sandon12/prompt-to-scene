using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

// Run in the Built-in smoke-test project with graphics enabled.
public static class UnityPreview
{
    public static void Run()
    {
        try
        {
            EditorSceneManager.OpenScene("Assets/Smoke.unity");
            var prop = Object.FindObjectOfType<AssetIdentity>().gameObject;
            prop.transform.position = new Vector3(0.65f, 0, 0.2f);
            prop.transform.rotation = Quaternion.Euler(0, -12, 0);
            var original = Object.Instantiate(prop);
            original.transform.position = new Vector3(-0.65f, 0, 0);
            original.transform.rotation = Quaternion.Euler(0, 10, 0);
            foreach (var renderer in original.GetComponentsInChildren<Renderer>())
                renderer.materials = renderer.sharedMaterials.Select(m => {
                    var copy = new Material(m);
                    if (m.name == "Wood") copy.color = new Color(0.24f, 0.085f, 0.025f).gamma;
                    return copy;
                }).ToArray();
            var plane = GameObject.CreatePrimitive(PrimitiveType.Plane);
            plane.transform.localScale = Vector3.one * 20;
            var ground = new Material(Shader.Find("Standard"));
            ground.color = new Color(0.055f, 0.065f, 0.09f);
            ground.SetFloat("_Glossiness", 0.15f);
            plane.GetComponent<Renderer>().material = ground;
            RenderSettings.ambientMode = AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.42f, 0.45f, 0.52f);
            AddLight(new Vector3(40, -35, 0), Color.white, 1.3f);
            AddLight(new Vector3(65, 140, 0), new Color(0.5f, 0.7f, 1), 0.8f);
            var camera = new GameObject("Preview camera").AddComponent<Camera>();
            camera.transform.position = new Vector3(3, 2.5f, -4.2f);
            camera.transform.LookAt(new Vector3(0, 0.45f, 0));
            camera.orthographic = true;
            camera.orthographicSize = 1.4f;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = ground.color;
            var target = new RenderTexture(1400, 900, 24);
            camera.targetTexture = target;
            camera.Render();
            RenderTexture.active = target;
            var image = new Texture2D(target.width, target.height, TextureFormat.RGB24, false);
            image.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0);
            image.Apply();
            File.WriteAllBytes(Path.Combine(AssetBridge.ProjectRoot, "preview.png"), image.EncodeToPNG());
            RenderTexture.active = null;
            camera.targetTexture = null;
            Object.DestroyImmediate(image);
            target.Release();
            Object.DestroyImmediate(target);
            // Preview staging is never saved into the user's/test scene.
            EditorApplication.Exit(0);
        }
        catch (Exception e) { Debug.LogException(e); EditorApplication.Exit(1); }
    }

    private static void AddLight(Vector3 rotation, Color color, float intensity)
    {
        var light = new GameObject("Studio light").AddComponent<Light>();
        light.type = LightType.Directional;
        light.transform.rotation = Quaternion.Euler(rotation);
        light.color = color;
        light.intensity = intensity;
        light.shadows = LightShadows.Soft;
    }
}
