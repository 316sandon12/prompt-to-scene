using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PromptToScene.Editor
{
    [Serializable] public class Placement
    {
        public string source_id, asset_id;
        public bool duplicate;
        public float[] position, rotation, scale, bounds_min, bounds_max;
        public float[] footprint;
        public SceneObject expected;
    }
    public static class SceneLayout
    {
        static UnityEngine.SceneManagement.Scene Scene => UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        static float[] Vec(Vector3 v) => new[] {v.x,v.y,v.z};
        static Vector3 Vec(float[] v) => new Vector3(v[0],v[1],v[2]);
        public static string Id(GameObject obj)
        {
            var id = GlobalObjectId.GetGlobalObjectIdSlow(obj);
            return id.targetObjectId == 0 ? "instance:" + obj.GetInstanceID() : id.ToString();
        }
        public static GameObject[] Objects()
        {
            return Resources.FindObjectsOfTypeAll<Renderer>()
                .Where(r => !EditorUtility.IsPersistent(r) && r.gameObject.scene == Scene && r.gameObject.activeInHierarchy && r.enabled)
                .Select(r => { var identity = r.GetComponentInParent<AssetIdentity>(); return identity == null ? r.gameObject : identity.gameObject; })
                .Distinct().ToArray();
        }
        public static SceneObject Describe(GameObject obj)
        {
            var identity = obj.GetComponent<AssetIdentity>();
            var renderers = obj.GetComponentsInChildren<Renderer>();
            var bounds = new Bounds(obj.transform.position, Vector3.zero);
            if (renderers.Length > 0) { bounds = renderers[0].bounds; foreach (var r in renderers.Skip(1)) bounds.Encapsulate(r.bounds); }
            var q = obj.transform.rotation;
            var result = new SceneObject { id = Id(obj), instance_id = obj.GetInstanceID(), name = obj.name,
                asset_id = identity == null ? "" : identity.assetId, position = Vec(obj.transform.position),
                rotation = Vec(obj.transform.eulerAngles), quaternion = new[] {q.x,q.y,q.z,q.w}, scale = Vec(obj.transform.localScale),
                bounds_min = Vec(bounds.min), bounds_max = Vec(bounds.max),
                renderers = renderers.Select(r => new RendererState { path = AnimationUtility.CalculateTransformPath(r.transform, obj.transform),
                    materials = r.sharedMaterials.Select(m => m == null ? "" : AssetDatabase.GetAssetPath(m)).ToArray() }).ToArray() };
            SceneDiagnostics.Oriented(obj,result);
            return result;
        }
        public static GameObject Find(string id)
        {
            GameObject obj = null;
            if (id != null && id.StartsWith("instance:") && int.TryParse(id.Substring(9), out int instanceId)) obj = EditorUtility.InstanceIDToObject(instanceId) as GameObject;
            else if (GlobalObjectId.TryParse(id, out GlobalObjectId global)) obj = GlobalObjectId.GlobalObjectIdentifierToObjectSlow(global) as GameObject;
            return obj != null && obj.scene == Scene ? obj : null;
        }
        public static SceneObject[] Selected()
        {
            return Selection.gameObjects.Where(o => o.scene == Scene).Select(o => {
                var identity = o.GetComponentInParent<AssetIdentity>(); return identity == null ? o : identity.gameObject;
            }).Distinct().Where(o => o.GetComponentsInChildren<Renderer>().Length > 0).Select(Describe).ToArray();
        }
        static bool Near(float[] a, float[] b) => a != null && b != null && a.Length == b.Length && a.Zip(b,(x,y) => Mathf.Abs(x-y) < .002f).All(v => v);
        public static bool Overlap(float[] low, float[] high, float[] footprint, SceneObject other)
        {
            if (!Enumerable.Range(0,3).All(i => Mathf.Min(high[i], other.bounds_max[i]) - Mathf.Max(low[i], other.bounds_min[i]) > .005f)) return false;
            if (footprint == null || footprint.Length != 8 || other.footprint == null || other.footprint.Length != 8) return true;
            foreach (var polygon in new[]{footprint,other.footprint})
                for(int i=0;i<4;i++)
                { int j=(i+1)%4; var axis=new Vector2(polygon[2*i+1]-polygon[2*j+1],polygon[2*j]-polygon[2*i]).normalized;
                  var a=Enumerable.Range(0,4).Select(n=>Vector2.Dot(axis,new Vector2(footprint[2*n],footprint[2*n+1]))).ToArray();
                  var b=Enumerable.Range(0,4).Select(n=>Vector2.Dot(axis,new Vector2(other.footprint[2*n],other.footprint[2*n+1]))).ToArray();
                  if(Mathf.Min(a.Max(),b.Max())-Mathf.Max(a.Min(),b.Min()) <= .005f) return false; }
            return true;
        }
        static void VectorValid(float[] value, bool positive = false)
        {
            if (value == null || value.Length != 3 || value.Any(v => float.IsNaN(v) || float.IsInfinity(v) || (positive && (v <= 0 || v > 100)))) throw new Exception("Invalid placement vector");
        }
        public static SceneResult Arrange(SceneAction request, string sceneKey)
        {
            if (request.scene != sceneKey) throw new Exception("Scene changed; inspect and plan again");
            var placements = request.placements;
            if (placements == null || placements.Length == 0 || placements.Length > 32 || request.anchor == null) throw new Exception("Invalid layout plan");
            var anchor = Find(request.anchor.id);
            if (anchor == null) throw new Exception("Anchor is no longer loaded");
            var anchorState = Describe(anchor);
            if (!Near(anchorState.position, request.anchor.position) || !Near(anchorState.rotation, request.anchor.rotation) || !Near(anchorState.scale, request.anchor.scale) || !Near(anchorState.bounds_min, request.anchor.bounds_min) || !Near(anchorState.bounds_max, request.anchor.bounds_max)) throw new Exception("Anchor changed; plan again");
            var sources = placements.Select(p => Find(p.source_id)).ToArray();
            for (int i=0; i<placements.Length; i++)
            {
                var p = placements[i];
                VectorValid(p.position); VectorValid(p.rotation); VectorValid(p.scale,true); VectorValid(p.bounds_min); VectorValid(p.bounds_max);
                if (sources[i] == null || sources[i].GetComponent<AssetIdentity>()?.assetId != p.asset_id || p.expected == null) throw new Exception("Source instance is missing");
                var state = Describe(sources[i]);
                if (!Near(state.position,p.expected.position) || !Near(state.rotation,p.expected.rotation) || !Near(state.scale,p.expected.scale) || !Near(state.bounds_min,p.expected.bounds_min) || !Near(state.bounds_max,p.expected.bounds_max)) throw new Exception("Source changed; plan again");
                if (!p.duplicate && placements.Take(i).Any(r => !r.duplicate && r.source_id == p.source_id)) throw new Exception("Duplicate target in layout");
            }
            var moved = new HashSet<string>(placements.Where(p => !p.duplicate).Select(p => p.source_id));
            foreach (var obstacle in Objects().Select(Describe).Where(o => o.id != request.anchor.id && !moved.Contains(o.id)))
                if (placements.Any(p => Overlap(p.bounds_min,p.bounds_max,p.footprint,obstacle))) throw new Exception("Layout overlaps " + obstacle.name + "; plan again");
            var existing = sources.Where((o,i) => !placements[i].duplicate).Distinct().ToArray();
            var before = new SceneResult { scene = sceneKey, objects = existing.Select(Describe).ToArray(), created_ids = new string[0] };
            var created = new List<GameObject>();
            var changed = new List<GameObject>();
            string snapshot = Path.Combine(AssetBridge.StateRoot,"edits",request.request_id + ".json");
            AssetBridge.WriteJson(snapshot,before);
            try
            {
                for (int i=0;i<placements.Length;i++)
                {
                    var p = placements[i]; var obj = sources[i];
                    if (p.duplicate)
                    {
                        var prefab = PrefabUtility.GetCorrespondingObjectFromSource(obj);
                        if (prefab == null) throw new Exception("Source must be a managed prefab instance");
                        obj = (GameObject)PrefabUtility.InstantiatePrefab(prefab,Scene);
                        created.Add(obj); Undo.RegisterCreatedObjectUndo(obj,"Arrange generated props");
                        SceneActions.Restore(obj,Describe(sources[i]));
                    }
                    Undo.RecordObject(obj.transform,"Arrange generated props");
                    obj.transform.position = Vec(p.position); obj.transform.eulerAngles = Vec(p.rotation); obj.transform.localScale = Vec(p.scale);
                    if(request.snap_to_surface) SceneDiagnostics.Ground(obj,false);
                    PrefabUtility.RecordPrefabInstancePropertyModifications(obj.transform); changed.Add(obj);
                }
                before.created_ids = created.Select(Id).ToArray(); AssetBridge.WriteJson(snapshot,before);
                EditorSceneManager.MarkSceneDirty(Scene);
                return new SceneResult { request_id = request.request_id, scene = sceneKey, undo_id = request.request_id, changed = changed.Count, objects = changed.Select(Describe).ToArray(), created_ids = before.created_ids };
            }
            catch
            {
                foreach (var obj in created) Object.DestroyImmediate(obj);
                for (int i=0;i<existing.Length;i++) SceneActions.Restore(existing[i],before.objects[i]);
                throw;
            }
        }
    }
}
