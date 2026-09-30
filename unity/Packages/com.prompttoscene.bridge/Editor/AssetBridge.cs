using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace PromptToScene.Editor
{
    [Serializable] public class TransferFile { public string name; public string sha256; }
    [Serializable] public class MaterialData
    {
        public string name;
        public string fbx_name;
        public float[] color;
        public float metallic;
        public float roughness;
        public string base_color_texture;
        public string normal_texture;
        public float normal_strength = 1;
    }
    [Serializable] public class TransferRequest
    {
        public int schema_version;
        public string target_engine;
        public string position_unit;
        public string asset_id;
        public string request_id;
        public string work_dir;
        public float[] position;
        public bool collider;
        public bool auto_place;
        public MaterialData[] materials;
        public TransferFile[] files;
    }
    [Serializable] public class ImportReceipt
    {
        public string status;
        public string engine = "unity";
        public string asset_id;
        public string request_id;
        public string prefab_path;
        public string prefab_guid;
        public string scene;
        public string pipeline;
        public string[] material_names;
        public int mesh_count;
        public int triangles;
        public float[] bounds_size;
        public string bounds_unit = "meters";
        public int scene_instances;
        public string error;
        public string completed_utc;
    }
    [Serializable] internal class EditorHeartbeat
    {
        public string unity_version;
        public string bridge_version = "0.3.0";
        public string engine = "unity";
        public string pipeline;
        public string scene;
        public bool playing;
        public string updated_utc;
    }

    [InitializeOnLoad]
    public static class AssetBridge
    {
        private static double nextTick;
        private static bool busy;
        public static string ProjectRoot => Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        public static string StateRoot => Path.Combine(ProjectRoot, ".prompt-to-scene");
        public static string Pipeline => GraphicsSettings.currentRenderPipeline == null ? "Built-in" :
            GraphicsSettings.currentRenderPipeline.GetType().Name;

        static AssetBridge() { EditorApplication.update += Tick; }

        private static void Tick()
        {
            if (busy || EditorApplication.timeSinceStartup < nextTick || EditorApplication.isCompiling ||
                EditorApplication.isUpdating) return;
            nextTick = EditorApplication.timeSinceStartup + 2;
            if (!Directory.Exists(StateRoot)) return;
            WriteJson(Path.Combine(StateRoot, "editor.json"), new EditorHeartbeat {
                unity_version = Application.unityVersion, pipeline = Pipeline,
                scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
                playing = EditorApplication.isPlayingOrWillChangePlaymode,
                updated_utc = DateTime.UtcNow.ToString("o")
            });
            if (!Application.isBatchMode && !EditorApplication.isPlayingOrWillChangePlaymode)
                ImportPending();
        }

        [MenuItem("Tools/Prompt-to-Scene/Import Pending Assets")]
        public static void ImportPending()
        {
            if (busy || EditorApplication.isPlayingOrWillChangePlaymode) return;
            string inbox = Path.Combine(StateRoot, "inbox");
            if (!Directory.Exists(inbox)) return;
            busy = true;
            try
            {
                foreach (string path in Directory.GetFiles(inbox, "*.json").OrderBy(p => p))
                {
                    var receipt = new ImportReceipt { status = "error", completed_utc = DateTime.UtcNow.ToString("o") };
                    try
                    {
                        if (new FileInfo(path).Length > 1024 * 1024) throw new Exception("Request too large");
                        var request = JsonUtility.FromJson<TransferRequest>(File.ReadAllText(path));
                        if (request == null) throw new Exception("Empty request");
                        receipt.asset_id = request.asset_id;
                        receipt.request_id = request.request_id;
                        ValidateRequest(request, Path.GetFileNameWithoutExtension(path));
                        if (File.Exists(Path.Combine(StateRoot, "cancel", request.request_id))) receipt.status = "cancelled";
                        else receipt = Import(request);
                        Debug.Log("[Prompt-to-Scene] Imported " + request.asset_id);
                    }
                    catch (Exception e)
                    {
                        receipt.error = e.Message;
                        Debug.LogError("[Prompt-to-Scene] " + e);
                    }
                    // Receipt names derive from the inbox filename, never unvalidated JSON.
                    string receiptPath = Path.Combine(StateRoot, "receipts", Path.GetFileName(path));
                    receipt.completed_utc = DateTime.UtcNow.ToString("o");
                    WriteJson(receiptPath, receipt);
                    if (receipt.status == "imported")
                        WriteJson(Path.Combine(StateRoot, "history", receipt.asset_id, receipt.request_id + ".json"), receipt);
                    File.Delete(path);
                }
                SceneActions.Process();
            }
            finally { busy = false; }
        }

        public static void ValidateRequest(TransferRequest request, string filename)
        {
            if (request.schema_version != 1 && request.schema_version != 2)
                throw new Exception("Unsupported schema_version; update the editor package");
            if (request.schema_version == 2 &&
                (request.target_engine != "unity" || request.position_unit != "meters"))
                throw new Exception("This request does not target Unity in meters");
            if (request.asset_id == null || !Regex.IsMatch(request.asset_id, "^[a-z][a-z0-9_-]{0,63}$") ||
                request.asset_id != filename) throw new Exception("Invalid asset_id");
            if (request.request_id == null || !Regex.IsMatch(request.request_id, "^[a-f0-9]{32}$"))
                throw new Exception("Invalid request_id");
            if (request.work_dir != "work/" + request.asset_id + "/" + request.request_id)
                throw new Exception("work_dir must match asset and request identity");
            if (request.position == null || request.position.Length != 3 ||
                request.position.Any(v => float.IsNaN(v) || float.IsInfinity(v)))
                throw new Exception("Invalid position");
            if (request.files == null || request.files.Length == 0 || request.files.Length > 128 ||
                request.files.Count(f => f.name == "model.fbx") != 1 ||
                request.files.Select(f => f.name).Distinct().Count() != request.files.Length)
                throw new Exception("Invalid file manifest");
            string source = Path.Combine(StateRoot, request.work_dir);
            foreach (TransferFile file in request.files)
            {
                if (file.name != "model.fbx" && !Regex.IsMatch(file.name ?? "", "^tex_[a-f0-9]{16}\\.png$"))
                    throw new Exception("Invalid transfer filename");
                string full = Path.Combine(source, file.name);
                if (!File.Exists(full) || Sha256(File.ReadAllBytes(full)) != file.sha256)
                    throw new Exception("Missing or changed file: " + file.name);
            }
            if (request.materials == null || request.materials.Length == 0 ||
                request.materials.Select(m => m.name).Distinct().Count() != request.materials.Length)
                throw new Exception("Missing or duplicate material definitions");
            foreach (MaterialData material in request.materials)
            {
                if (request.schema_version == 2 && material.fbx_name !=
                    "PTS_" + Sha256(Encoding.UTF8.GetBytes(material.name ?? "")).Substring(0, 16))
                    throw new Exception("Invalid FBX material identity");
                if (string.IsNullOrEmpty(material.name) || material.color == null || material.color.Length != 4 ||
                    material.color.Any(v => float.IsNaN(v) || float.IsInfinity(v) || v < 0 || v > 1) ||
                    !UnitInterval(material.metallic) || !UnitInterval(material.roughness) ||
                    float.IsNaN(material.normal_strength) || float.IsInfinity(material.normal_strength) ||
                    material.normal_strength < 0)
                    throw new Exception("Invalid material parameters");
                foreach (string texture in new[] { material.base_color_texture, material.normal_texture })
                    if (!string.IsNullOrEmpty(texture) && !request.files.Any(f => f.name == texture && texture.EndsWith(".png")))
                        throw new Exception("Texture is absent from manifest: " + texture);
            }
        }

        private static bool UnitInterval(float value) => !float.IsNaN(value) && value >= 0 && value <= 1;

        private static ImportReceipt Import(TransferRequest request)
        {
            bool urp = Pipeline.Contains("Universal");
            if (!urp && Pipeline != "Built-in") throw new Exception("v0.1 supports Built-in and URP only");
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if (!scene.IsValid() || !scene.isLoaded) throw new Exception("Open a scene before importing");
            string target = "Assets/PromptToScene/" + request.asset_id;
            var overrides = SceneActions.RememberTints(request.asset_id);
            string absoluteTarget = Path.Combine(ProjectRoot, target);
            Directory.CreateDirectory(absoluteTarget);
            foreach (TransferFile file in request.files)
            {
                File.Copy(Path.Combine(StateRoot, request.work_dir, file.name),
                    Path.Combine(absoluteTarget, file.name), true);
            }
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            string modelPath = target + "/model.fbx";
            var importer = AssetImporter.GetAtPath(modelPath) as ModelImporter;
            if (importer == null) throw new Exception("Unity did not recognize model.fbx");
            importer.importAnimation = false;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.globalScale = 1;
            importer.useFileScale = true;
            importer.SaveAndReimport();
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            if (model == null) throw new Exception("FBX import produced no model");
            var materials = new Dictionary<string, Material>();
            foreach (MaterialData data in request.materials)
            {
                string materialPath = target + "/mat_" + Sha256(Encoding.UTF8.GetBytes(data.name)).Substring(0, 16) + ".mat";
                var material = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
                Shader shader = Shader.Find(urp ? "Universal Render Pipeline/Lit" : "Standard");
                if (shader == null) throw new Exception("Target shader not installed");
                if (material == null)
                {
                    material = new Material(shader);
                    AssetDatabase.CreateAsset(material, materialPath);
                }
                material.shader = shader;
                material.name = data.name;
                // Blender's shader constants are scene-linear; Unity material colors are sRGB UI values.
                Color linear = new Color(data.color[0], data.color[1], data.color[2], data.color[3]);
                Color color = linear.gamma; color.a = linear.a;
                material.SetColor(urp ? "_BaseColor" : "_Color", color);
                material.SetFloat("_Metallic", data.metallic);
                material.SetFloat(urp ? "_Smoothness" : "_Glossiness", 1 - data.roughness);
                material.SetTexture(urp ? "_BaseMap" : "_MainTex", Texture(target, data.base_color_texture, false));
                material.SetTexture("_BumpMap", Texture(target, data.normal_texture, true));
                material.SetFloat("_BumpScale", data.normal_strength);
                if (string.IsNullOrEmpty(data.normal_texture)) material.DisableKeyword("_NORMALMAP");
                else material.EnableKeyword("_NORMALMAP");
                EditorUtility.SetDirty(material);
                materials.Add(data.name, material);
            }
            var slots = request.materials.ToDictionary(
                data => string.IsNullOrEmpty(data.fbx_name) ? data.name : data.fbx_name,
                data => materials[data.name]);
            string prefabPath = target + "/" + request.asset_id + ".prefab";
            bool existing = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath) != null;
            GameObject root = existing ? PrefabUtility.LoadPrefabContents(prefabPath) : new GameObject(request.asset_id);
            Bounds bounds;
            int triangles;
            int meshCount;
            try
            {
                Transform previous = root.transform.Find("Visual");
                if (previous != null) Object.DestroyImmediate(previous.gameObject);
                GameObject visual = Object.Instantiate(model, root.transform, false);
                visual.name = "Visual";
                foreach (Renderer renderer in visual.GetComponentsInChildren<Renderer>())
                {
                    renderer.sharedMaterials = renderer.sharedMaterials.Select(m => {
                        if (m == null || !slots.TryGetValue(m.name, out Material mapped))
                            throw new Exception("Cannot map imported material: " + (m == null ? "null" : m.name));
                        return mapped;
                    }).ToArray();
                }
                var meshes = visual.GetComponentsInChildren<MeshFilter>();
                if (meshes.Length == 0 || meshes.Any(m => m.sharedMesh == null))
                    throw new Exception("No valid static meshes imported");
                triangles = meshes.Sum(m => m.sharedMesh.triangles.Length / 3);
                meshCount = meshes.Length;
                var renderers = visual.GetComponentsInChildren<Renderer>();
                bounds = renderers[0].bounds;
                foreach (Renderer renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
                var identity = root.GetComponent<AssetIdentity>() ?? root.AddComponent<AssetIdentity>();
                identity.assetId = request.asset_id;
                identity.revision = request.request_id;
                BoxCollider box = root.GetComponent<BoxCollider>();
                if (request.collider)
                {
                    if (box == null) box = root.AddComponent<BoxCollider>();
                    box.center = root.transform.InverseTransformPoint(bounds.center);
                    box.size = bounds.size;
                }
                else if (box != null) Object.DestroyImmediate(box);
                PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
            }
            finally
            {
                if (existing) PrefabUtility.UnloadPrefabContents(root);
                else Object.DestroyImmediate(root);
            }
            AssetDatabase.SaveAssets();
            SceneActions.RestoreTints(overrides);
            var instances = Resources.FindObjectsOfTypeAll<AssetIdentity>().Where(a =>
                !EditorUtility.IsPersistent(a) && a.gameObject.scene.IsValid() &&
                a.gameObject.scene == scene && a.assetId == request.asset_id).ToArray();
            if (instances.Length == 0)
            {
                GameObject instance = (GameObject)PrefabUtility.InstantiatePrefab(
                    AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath), scene);
                Undo.RegisterCreatedObjectUndo(instance, "Place AI asset");
                instance.transform.position = request.auto_place ? SceneActions.AutoPosition(instance) : new Vector3(request.position[0], request.position[1], request.position[2]);
                PrefabUtility.RecordPrefabInstancePropertyModifications(instance.transform);
                Selection.activeGameObject = instance;
                if (request.auto_place) SceneActions.Focus(new[] { instance });
            }
            EditorSceneManager.MarkSceneDirty(scene);
            return new ImportReceipt {
                status = "imported", asset_id = request.asset_id, request_id = request.request_id,
                prefab_path = prefabPath, prefab_guid = AssetDatabase.AssetPathToGUID(prefabPath),
                scene = scene.path, pipeline = Pipeline, material_names = materials.Keys.ToArray(),
                mesh_count = meshCount, triangles = triangles,
                bounds_size = new[] { bounds.size.x, bounds.size.y, bounds.size.z },
                scene_instances = Math.Max(1, instances.Length)
            };
        }

        private static Texture2D Texture(string target, string name, bool normal)
        {
            if (string.IsNullOrEmpty(name)) return null;
            string path = target + "/" + name;
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) throw new Exception("Texture import failed: " + name);
            importer.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
            importer.sRGBTexture = !normal;
            importer.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        private static string Sha256(byte[] bytes)
        {
            using (var hash = SHA256.Create())
                return string.Concat(hash.ComputeHash(bytes).Select(b => b.ToString("x2")));
        }

        public static void WriteJson(string path, object data)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string temporary = path + ".tmp";
            File.WriteAllText(temporary, JsonUtility.ToJson(data, true));
            if (File.Exists(path)) File.Replace(temporary, path, null);
            else File.Move(temporary, path);
        }
    }
}
