using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

public static class UnitySmoke
{
    public static void Textures()
    {
        try
        {
            EditorSceneManager.OpenScene("Assets/Smoke.unity");
            ConfigurePipeline();
            AssetBridge.ImportPending();
            foreach (string id in new[] { "textured_cube", "saved_cube" })
            {
                var receipt = JsonUtility.FromJson<ImportReceipt>(File.ReadAllText(
                    Path.Combine(AssetBridge.StateRoot, "receipts/" + id + ".json")));
                Require(receipt.status == "imported", receipt.error ?? "Texture import failed");
                Require(receipt.triangles == 12 && receipt.mesh_count == 1, "Wrong textured geometry");
                var instance = Object.FindObjectsOfType<AssetIdentity>().Single(a => a.assetId == id);
                Require(instance.GetComponent<BoxCollider>() == null, "Collider=false was ignored");
                Material paint = instance.GetComponentInChildren<Renderer>().sharedMaterial;
                bool urp = AssetBridge.Pipeline.Contains("Universal");
                Require(paint.shader.name == (urp ? "Universal Render Pipeline/Lit" : "Standard"), "Wrong shader");
                var albedo = paint.GetTexture(urp ? "_BaseMap" : "_MainTex");
                var normal = paint.GetTexture("_BumpMap");
                Require(albedo != null && albedo.width == 8 && albedo.height == 8, "Base-color texture lost");
                Require(normal != null && normal.width == 8 && normal.height == 8, "Normal texture lost");
                var albedoImporter = (TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(albedo));
                var normalImporter = (TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(normal));
                Require(albedoImporter.sRGBTexture && albedoImporter.textureType == TextureImporterType.Default, "Incorrect albedo color space");
                Require(!normalImporter.sRGBTexture && normalImporter.textureType == TextureImporterType.NormalMap, "Incorrect normal import mode");
                Require(paint.IsKeywordEnabled("_NORMALMAP"), "Normal map keyword disabled");
                Require(Mathf.Abs(paint.GetFloat("_BumpScale") - 0.75f) < 0.001f, "Normal strength changed");
                Require(Mathf.Abs(paint.GetFloat("_Metallic") - 0.2f) < 0.001f, "Metallic changed");
                Require(Mathf.Abs(paint.GetFloat(urp ? "_Smoothness" : "_Glossiness") - 0.35f) < 0.001f, "Roughness conversion incorrect");
            }
            File.WriteAllText(Path.Combine(AssetBridge.StateRoot, "textures-passed.txt"), "PASS");
            Debug.Log("PROMPT_TO_SCENE_SMOKE_PASS textures");
            EditorApplication.Exit(0);
        }
        catch (Exception e) { Debug.LogException(e); EditorApplication.Exit(1); }
    }

    public static void Run()
    {
        try
        {
            string scenePath = "Assets/Smoke.unity";
            string baselinePath = Path.Combine(AssetBridge.StateRoot, "baseline.json");
            bool revision = File.Exists(baselinePath);
            if (revision) EditorSceneManager.OpenScene(scenePath);
            else EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ConfigurePipeline();
            AssetBridge.ImportPending();
            string receiptPath = Path.Combine(AssetBridge.StateRoot, "receipts/crate.json");
            Require(File.Exists(receiptPath), "No import receipt");
            var receipt = JsonUtility.FromJson<ImportReceipt>(File.ReadAllText(receiptPath));
            Require(receipt.status == "imported", receipt.error ?? "Import failed");
            Require(receipt.triangles > 100 && receipt.mesh_count == 13, "Wrong geometry counts");
            Require(Mathf.Abs(receipt.bounds_size[1] - 1) < 0.02f, "Wrong meter scale / up axis");
            Require(receipt.material_names.Contains("Wood") && receipt.material_names.Contains("Iron"), "Missing materials");
            var links = Object.FindObjectsOfType<AssetIdentity>();
            Require(links.Length == 1, "Duplicate scene instance");
            var instance = links[0].gameObject;
            Require(Vector3.Distance(instance.transform.position, new Vector3(2, 0, 3)) < 0.001f, "Instance position changed");
            Require(instance.GetComponent<BoxCollider>() != null, "Missing collider");
            if (revision)
            {
                var baseline = JsonUtility.FromJson<ImportReceipt>(File.ReadAllText(baselinePath));
                Require(receipt.prefab_guid == baseline.prefab_guid, "Prefab GUID changed");
                Require(receipt.request_id != baseline.request_id, "Revision was not applied");
                Require(instance.GetComponent<Rigidbody>() != null, "Prefab root component lost");
                Require(Mathf.Abs(instance.GetComponent<Rigidbody>().mass - 7) < 0.01f, "Custom component value changed");
                Material wood = instance.GetComponentsInChildren<Renderer>().SelectMany(r => r.sharedMaterials).First(m => m.name == "Wood");
                Color color = wood.GetColor(AssetBridge.Pipeline.Contains("Universal") ? "_BaseColor" : "_Color");
                Require(color.g > color.r, "Revised green material was not imported");
            }
            else
            {
                var root = PrefabUtility.LoadPrefabContents(receipt.prefab_path);
                root.AddComponent<Rigidbody>().mass = 7;
                root.GetComponent<Rigidbody>().isKinematic = true;
                PrefabUtility.SaveAsPrefabAsset(root, receipt.prefab_path);
                PrefabUtility.UnloadPrefabContents(root);
                AssetBridge.WriteJson(baselinePath, receipt);
            }
            EditorSceneManager.SaveScene(instance.scene, scenePath);
            File.WriteAllText(Path.Combine(AssetBridge.StateRoot, revision ? "revision-passed.txt" : "initial-passed.txt"), "PASS");
            Debug.Log("PROMPT_TO_SCENE_SMOKE_PASS " + (revision ? "revision" : "initial"));
            EditorApplication.Exit(0);
        }
        catch (Exception e)
        {
            Debug.LogException(e);
            EditorApplication.Exit(1);
        }
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void ConfigurePipeline()
    {
        if (!File.Exists(Path.Combine(AssetBridge.ProjectRoot, "use-urp.txt"))) return;
        var pipelineType = Type.GetType("UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset, Unity.RenderPipelines.Universal.Runtime");
        Require(pipelineType != null, "URP package unavailable");
        var pipeline = AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.RenderPipelineAsset>("Assets/SmokePipeline.asset");
        if (pipeline == null)
        {
            pipeline = (UnityEngine.Rendering.RenderPipelineAsset)ScriptableObject.CreateInstance(pipelineType);
            var rendererType = Type.GetType("UnityEngine.Rendering.Universal.UniversalRendererData, Unity.RenderPipelines.Universal.Runtime");
            var renderer = ScriptableObject.CreateInstance(rendererType);
            AssetDatabase.CreateAsset(renderer, "Assets/SmokeRenderer.asset");
            var serialized = new SerializedObject(pipeline);
            var renderers = serialized.FindProperty("m_RendererDataList");
            renderers.arraySize = 1;
            renderers.GetArrayElementAtIndex(0).objectReferenceValue = renderer;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.CreateAsset(pipeline, "Assets/SmokePipeline.asset");
        }
        UnityEngine.Rendering.GraphicsSettings.defaultRenderPipeline = pipeline;
        QualitySettings.renderPipeline = null;
    }
}
