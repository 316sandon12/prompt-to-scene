using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PromptToScene.Editor
{
    [Serializable] public class SceneAction
    {
        public int schema_version;
        public string request_id, target_engine, operation, scope, asset_id, undo_id, material;
        public float[] move, rotate, scale, color;
        public string scene;
        public SceneObject anchor;
        public Placement[] placements;
    }
    [Serializable] public class RendererState { public string path; public string[] materials; }
    [Serializable] public class SceneObject
    {
        public string id, name, asset_id;
        public int instance_id;
        public float[] position, rotation, quaternion, scale, bounds_min, bounds_max;
        public RendererState[] renderers;
    }
    [Serializable] public class SceneResult
    {
        public string status = "completed", engine = "unity", request_id, error, scene, undo_id, preview, restored_edit;
        public SceneObject[] selected, assets, objects, context, selected_context;
        public string[] created_ids;
        public int changed;
    }

    public static class SceneActions
    {
        static string Root => AssetBridge.StateRoot;
        static UnityEngine.SceneManagement.Scene Scene => UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        static string SceneKey => string.IsNullOrEmpty(Scene.path) ? "unsaved:" + Scene.handle : Scene.path;
        static float[] Vec(Vector3 v) => new[] { v.x, v.y, v.z };
        static Vector3 Vec(float[] v) => new Vector3(v[0], v[1], v[2]);
        static bool Id(string s) => s != null && Regex.IsMatch(s, "^[a-f0-9]{32}$");
        static AssetIdentity[] All => Resources.FindObjectsOfTypeAll<AssetIdentity>().Where(a =>
            !EditorUtility.IsPersistent(a) && a.gameObject.scene == Scene).ToArray();
        static AssetIdentity[] Selected => Selection.gameObjects.Select(g => g.GetComponentInParent<AssetIdentity>())
            .Where(a => a != null && a.gameObject.scene == Scene).Distinct().ToArray();

        public static Dictionary<AssetIdentity, Dictionary<string, Material>> RememberTints(string assetId)
        {
            return All.Where(a => a.assetId == assetId).ToDictionary(a => a, a =>
                a.GetComponentsInChildren<Renderer>().SelectMany(r => r.sharedMaterials)
                .Where(m => m != null && AssetDatabase.GetAssetPath(m).StartsWith("Assets/PromptToScene/Overrides/"))
                .GroupBy(m => m.name).ToDictionary(g => g.Key, g => g.First()));
        }

        public static void RestoreTints(Dictionary<AssetIdentity, Dictionary<string, Material>> snapshots)
        {
            foreach (var entry in snapshots)
                if (entry.Key != null && entry.Value.Count > 0)
                    foreach (var renderer in entry.Key.GetComponentsInChildren<Renderer>())
                    {
                        renderer.sharedMaterials = renderer.sharedMaterials.Select(m =>
                            m != null && entry.Value.TryGetValue(m.name, out Material tint) ? tint : m).ToArray();
                        PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);
                    }
        }

        public static SceneObject Describe(AssetIdentity identity) => SceneLayout.Describe(identity.gameObject);

        public static void Focus(GameObject[] objects)
        {
            Selection.objects = objects;
            var renderers = objects.SelectMany(o => o.GetComponentsInChildren<Renderer>()).ToArray();
            if (renderers.Length == 0) return;
            Bounds bounds = renderers[0].bounds;
            foreach (var renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
            if (SceneView.lastActiveSceneView != null) SceneView.lastActiveSceneView.Frame(bounds, false);
        }

        public static Vector3 AutoPosition(GameObject instance)
        {
            var view = SceneView.lastActiveSceneView;
            Vector3 point = view == null ? Vector3.zero : view.camera.transform.position + view.camera.transform.forward * 4;
            point.y = 0;
            // Exclude the new prop's own colliders while looking for the scene's ground.
            foreach (var hit in Physics.RaycastAll(new Vector3(point.x, 10000, point.z), Vector3.down, 20000).OrderBy(h => h.distance))
                if (!hit.transform.IsChildOf(instance.transform)) { point = hit.point; break; }
            var renderers = instance.GetComponentsInChildren<Renderer>();
            if (renderers.Length > 0)
            {
                Bounds b = renderers[0].bounds;
                foreach (var r in renderers.Skip(1)) b.Encapsulate(r.bounds);
                point.y -= b.min.y - instance.transform.position.y;
            }
            return point;
        }

        public static void Process()
        {
            string folder = Path.Combine(Root, "actions");
            if (!Directory.Exists(folder)) return;
            foreach (string path in Directory.GetFiles(folder, "*.json").OrderBy(p => p))
            {
                string id = Path.GetFileNameWithoutExtension(path);
                var result = new SceneResult { request_id = id, scene = SceneKey };
                try
                {
                    if (!Id(id) || new FileInfo(path).Length > 100000 || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                        throw new Exception("Invalid action file");
                    var request = JsonUtility.FromJson<SceneAction>(File.ReadAllText(path));
                    if (request.schema_version != 1 || request.target_engine != "unity" || request.request_id != id)
                        throw new Exception("Unsupported editor action");
                    Validate(request);
                    if (File.Exists(Path.Combine(Root, "cancel", id))) result.status = "cancelled";
                    else result = Execute(request);
                }
                catch (Exception e) { result.status = "error"; result.error = e.Message; }
                result.request_id = id;
                AssetBridge.WriteJson(Path.Combine(Root, "action-receipts", id + ".json"), result);
                File.Delete(path);
            }
        }

        static void Validate(SceneAction a)
        {
            if (a.scope != "selected" && a.scope != "asset") throw new Exception("Invalid scope");
            if (a.scope == "asset" && (a.asset_id == null || !Regex.IsMatch(a.asset_id, "^[a-z][a-z0-9_-]{0,63}$")))
                throw new Exception("Choose an asset");
            foreach (var vector in new[] { a.move, a.rotate, a.scale, a.color })
                if (vector != null && (vector.Length != 3 || vector.Any(v => float.IsNaN(v) || float.IsInfinity(v))))
                    throw new Exception("Invalid vector");
            if (a.scale != null && a.scale.Any(v => v <= 0 || v > 100)) throw new Exception("Invalid scale");
            if (a.color != null && a.color.Any(v => v < 0 || v > 1)) throw new Exception("Invalid color");
        }

        static SceneResult Execute(SceneAction a)
        {
            var result = new SceneResult { request_id = a.request_id, scene = SceneKey };
            if (a.operation == "inspect") { result.selected = Selected.Select(Describe).ToArray(); result.assets = All.Select(Describe).ToArray(); result.context = SceneLayout.Objects().Select(SceneLayout.Describe).ToArray(); result.selected_context = SceneLayout.Selected(); return result; }
            if (a.operation == "arrange") return SceneLayout.Arrange(a, SceneKey);
            if (a.operation == "undo")
            {
                if (!Id(a.undo_id)) throw new Exception("Invalid undo ID");
                var snapshot = JsonUtility.FromJson<SceneResult>(File.ReadAllText(Path.Combine(Root, "edits", a.undo_id + ".json")));
                if (snapshot.scene != SceneKey) throw new Exception("Open the scene where this edit was made");
                var objects = snapshot.objects.Select(Resolve).ToArray();
                if (objects.Any(o => o == null)) throw new Exception("An edited object is no longer loaded");
                for (int i = 0; i < objects.Length; i++) Restore(objects[i], snapshot.objects[i]);
                foreach (var createdId in snapshot.created_ids ?? new string[0])
                { var created = SceneLayout.Find(createdId); if (created != null) Undo.DestroyObjectImmediate(created); }
                EditorSceneManager.MarkSceneDirty(Scene);
                result.restored_edit = a.undo_id; result.objects = snapshot.objects;
                return result;
            }
            var targets = (a.scope == "asset" ? All : Selected).Where(o => string.IsNullOrEmpty(a.asset_id) || o.assetId == a.asset_id).ToArray();
            if (targets.Length == 0) throw new Exception("Select a Prompt-to-Scene prop, or choose an asset scope");
            if (a.operation == "focus") { Focus(targets.Select(t => t.gameObject).ToArray()); result.objects = targets.Select(Describe).ToArray(); return result; }
            if (a.operation == "preview")
            {
                result.preview = "previews/" + a.request_id + ".png";
                Capture(targets, Path.Combine(Root, result.preview));
                return result;
            }
            if (a.operation != "transform" && a.operation != "tint") throw new Exception("Unknown action");
            if (a.operation == "tint" && a.color == null) throw new Exception("Tint needs a color");
            var before = new SceneResult { scene = SceneKey, objects = targets.Select(Describe).ToArray() };
            AssetBridge.WriteJson(Path.Combine(Root, "edits", a.request_id + ".json"), before);
            try
            {
                foreach (var target in targets)
                {
                    if (a.operation == "transform")
                    {
                        Undo.RecordObject(target.transform, "Prompt-to-Scene transform");
                        if (a.move != null) target.transform.position += Vec(a.move);
                        if (a.rotate != null) target.transform.Rotate(Vec(a.rotate), Space.World);
                        if (a.scale != null) target.transform.localScale = Vector3.Scale(target.transform.localScale, Vec(a.scale));
                        PrefabUtility.RecordPrefabInstancePropertyModifications(target.transform);
                        result.changed++;
                    }
                    else
                    {
                        string directory = "Assets/PromptToScene/Overrides";
                        Directory.CreateDirectory(Path.Combine(AssetBridge.ProjectRoot, directory));
                        AssetDatabase.Refresh();
                        var copies = new Dictionary<Material, Material>();
                        foreach (var renderer in target.GetComponentsInChildren<Renderer>())
                        {
                            Undo.RecordObject(renderer, "Prompt-to-Scene tint");
                            var mats = renderer.sharedMaterials;
                            for (int i = 0; i < mats.Length; i++)
                            {
                                if (mats[i] == null || (!string.IsNullOrEmpty(a.material) && mats[i].name != a.material)) continue;
                                if (!copies.TryGetValue(mats[i], out Material material))
                                {
                                    material = new Material(mats[i]);
                                    Color color = new Color(a.color[0], a.color[1], a.color[2], 1).gamma;
                                    material.SetColor(material.HasProperty("_BaseColor") ? "_BaseColor" : "_Color", color);
                                    AssetDatabase.CreateAsset(material, directory + "/mat_" + a.request_id + "_" + target.GetInstanceID() + "_" + copies.Count + ".mat");
                                    material.name = mats[i].name;
                                    EditorUtility.SetDirty(material);
                                    copies[mats[i]] = material;
                                }
                                mats[i] = material; result.changed++;
                            }
                            renderer.sharedMaterials = mats;
                            PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);
                        }
                    }
                }
                if (result.changed == 0) throw new Exception("No matching material was found");
                AssetDatabase.SaveAssets(); EditorSceneManager.MarkSceneDirty(Scene);
            }
            catch { for (int i = 0; i < targets.Length; i++) Restore(targets[i].gameObject, before.objects[i]); throw; }
            result.undo_id = a.request_id; result.objects = targets.Select(Describe).ToArray();
            return result;
        }

        static GameObject Resolve(SceneObject state)
        {
            GameObject obj = null;
            if (GlobalObjectId.TryParse(state.id, out GlobalObjectId id)) obj = GlobalObjectId.GlobalObjectIdentifierToObjectSlow(id) as GameObject;
            if (obj == null) obj = EditorUtility.InstanceIDToObject(state.instance_id) as GameObject;
            var identity = obj == null ? null : obj.GetComponent<AssetIdentity>();
            return identity != null && identity.assetId == state.asset_id && obj.scene == Scene ? obj : null;
        }

        public static void Restore(GameObject obj, SceneObject state)
        {
            Undo.RecordObject(obj.transform, "Restore Prompt-to-Scene edit");
            obj.transform.position = Vec(state.position);
            obj.transform.rotation = new Quaternion(state.quaternion[0],state.quaternion[1],state.quaternion[2],state.quaternion[3]);
            obj.transform.localScale = Vec(state.scale);
            PrefabUtility.RecordPrefabInstancePropertyModifications(obj.transform);
            foreach (var row in state.renderers)
            {
                var child = string.IsNullOrEmpty(row.path) ? obj.transform : obj.transform.Find(row.path);
                var renderer = child == null ? null : child.GetComponent<Renderer>();
                if (renderer == null) continue;
                Undo.RecordObject(renderer, "Restore Prompt-to-Scene material");
                renderer.sharedMaterials = row.materials.Select(p => string.IsNullOrEmpty(p) ? null : AssetDatabase.LoadAssetAtPath<Material>(p)).ToArray();
                PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);
            }
        }

        static void Capture(AssetIdentity[] objects, string path)
        {
            var renderers = objects.SelectMany(o => o.GetComponentsInChildren<Renderer>()).ToArray();
            Bounds bounds = renderers[0].bounds;
            foreach (var renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
            var cameraObject = new GameObject("Prompt-to-Scene preview") { hideFlags = HideFlags.HideAndDontSave };
            var lightObject = new GameObject("Prompt-to-Scene preview light") { hideFlags = HideFlags.HideAndDontSave };
            RenderTexture texture = null; Texture2D image = null;
            var previous = RenderTexture.active;
            try
            {
                var camera = cameraObject.AddComponent<Camera>();
                float size = Mathf.Max(bounds.extents.magnitude, .2f);
                camera.transform.position = bounds.center + new Vector3(1.8f, 1.25f, -2.2f) * size;
                camera.transform.LookAt(bounds.center);
                camera.nearClipPlane = .01f; camera.farClipPlane = Mathf.Max(100, size * 20);
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(.07f, .09f, .13f);
                var light = lightObject.AddComponent<Light>();
                light.type = LightType.Directional; light.intensity = 1.5f;
                light.transform.rotation = Quaternion.Euler(40, -35, 0);
                texture = new RenderTexture(1024, 768, 24); camera.targetTexture = texture;
                camera.Render(); RenderTexture.active = texture;
                image = new Texture2D(1024,768,TextureFormat.RGB24,false);
                image.ReadPixels(new Rect(0,0,1024,768),0,0); image.Apply();
                Directory.CreateDirectory(Path.GetDirectoryName(path)); File.WriteAllBytes(path, image.EncodeToPNG());
            }
            finally
            {
                RenderTexture.active = previous;
                Object.DestroyImmediate(cameraObject); Object.DestroyImmediate(lightObject);
                if (image != null) Object.DestroyImmediate(image);
                if (texture != null) { texture.Release(); Object.DestroyImmediate(texture); }
            }
        }
    }
}
