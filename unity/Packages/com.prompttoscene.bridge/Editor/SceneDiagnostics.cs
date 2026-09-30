using System;
using System.Linq;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace PromptToScene.Editor
{
    [Serializable] public class AssetMetrics
    {
        public string id, asset_id, mesh_key;
        public int triangles, vertices, material_slots, missing_materials, texture_count;
        public long texture_bytes_estimate, texture_bytes_editor;
        public int[] lod_triangles, lod_vertices;
        public float[] lod_screen_heights;
        public bool support_known;
        public float support_gap;
        public string[] overlap_candidates;
    }
    public static class SceneDiagnostics
    {
        public static Renderer[] BaseRenderers(GameObject obj)
        {
            var group = obj.GetComponentInChildren<LODGroup>();
            return group != null && group.lodCount > 0 ? group.GetLODs()[0].renderers.Where(r => r != null).ToArray() : obj.GetComponentsInChildren<Renderer>();
        }
        public static void Oriented(GameObject obj, SceneObject state)
        {
            var points = new List<Vector3>();
            foreach (var renderer in BaseRenderers(obj))
            {
                var filter = renderer.GetComponent<MeshFilter>();
                for (int n=0;n<8;n++)
                {
                    var bounds = filter != null && filter.sharedMesh != null ? filter.sharedMesh.bounds : renderer.bounds;
                    var point = new Vector3((n&1)==0?bounds.min.x:bounds.max.x,(n&2)==0?bounds.min.y:bounds.max.y,(n&4)==0?bounds.min.z:bounds.max.z);
                    if (filter != null && filter.sharedMesh != null) point = filter.transform.TransformPoint(point);
                    points.Add(Quaternion.Inverse(obj.transform.rotation) * (point - obj.transform.position));
                }
            }
            if (points.Count == 0) return;
            var low = new Vector3(points.Min(v=>v.x),points.Min(v=>v.y),points.Min(v=>v.z));
            var high = new Vector3(points.Max(v=>v.x),points.Max(v=>v.y),points.Max(v=>v.z));
            state.oriented_min = new[]{low.x,low.y,low.z}; state.oriented_max = new[]{high.x,high.y,high.z};
            var footprint = new List<float>();
            foreach (var point in new[]{new Vector3(low.x,0,low.z),new Vector3(high.x,0,low.z),new Vector3(high.x,0,high.z),new Vector3(low.x,0,high.z)})
            { var p = obj.transform.rotation * point + obj.transform.position; footprint.Add(p.x); footprint.Add(p.z); }
            state.footprint = footprint.ToArray();
        }
        public static bool Support(GameObject obj, out float gap)
        {
            var renderers = BaseRenderers(obj); gap = 0;
            if (renderers.Length == 0) return false;
            Bounds bounds = renderers[0].bounds;
            foreach (var r in renderers.Skip(1)) bounds.Encapsulate(r.bounds);
            Physics.SyncTransforms();
            foreach (var hit in Physics.RaycastAll(new Vector3(bounds.center.x,bounds.max.y+1,bounds.center.z),Vector3.down,10000).OrderBy(h=>h.distance))
                if (!hit.transform.IsChildOf(obj.transform) && hit.normal.y > .7f && hit.point.y <= bounds.min.y + .5f)
                { gap = bounds.min.y-hit.point.y; return true; }
            return false;
        }
        public static void Ground(GameObject obj, bool required=true)
        {
            if (!Support(obj,out float gap)) { if (required) throw new Exception("No collision surface was detected beneath " + obj.name); return; }
            Undo.RecordObject(obj.transform,"Align prop to surface");
            obj.transform.position -= Vector3.up * gap;
            PrefabUtility.RecordPrefabInstancePropertyModifications(obj.transform);
        }
        static Mesh[] Meshes(Renderer[] renderers) => renderers.Where(r=>r!=null).Select(r=>r.GetComponent<MeshFilter>()?.sharedMesh).Where(m=>m!=null).ToArray();
        public static AssetMetrics Inspect(GameObject obj)
        {
            var renderers = BaseRenderers(obj); var meshes = Meshes(renderers);
            var materials = renderers.SelectMany(r=>r.sharedMaterials).ToArray();
            var textures = materials.Where(m=>m!=null).SelectMany(m=>m.GetTexturePropertyNames().Select(n=>m.GetTexture(n))).Where(t=>t!=null).Distinct().ToArray();
            var group = obj.GetComponentInChildren<LODGroup>();
            var levels = group == null ? new[]{new LOD(0,renderers)} : group.GetLODs();
            var state = SceneLayout.Describe(obj);
            bool support = Support(obj,out float gap);
            return new AssetMetrics { id=state.id, asset_id=state.asset_id,
                mesh_key=string.Join("|",meshes.Select(m=>AssetDatabase.GetAssetPath(m)+":"+m.name).Distinct().OrderBy(s=>s)),
                triangles=meshes.Sum(m=>Enumerable.Range(0,m.subMeshCount).Sum(i=>(int)m.GetIndexCount(i)/3)),
                vertices=meshes.Sum(m=>m.vertexCount), material_slots=materials.Length,
                missing_materials=materials.Count(m=>m==null || m.shader==null || m.shader.name=="Hidden/InternalErrorShader"),
                texture_count=textures.Length, texture_bytes_estimate=textures.Sum(t=>(long)t.width*t.height*4*4/3),
                texture_bytes_editor=textures.Sum(t=>UnityEngine.Profiling.Profiler.GetRuntimeMemorySizeLong(t)),
                lod_triangles=levels.Select(l=>Meshes(l.renderers).Sum(m=>Enumerable.Range(0,m.subMeshCount).Sum(i=>(int)m.GetIndexCount(i)/3))).ToArray(),
                lod_vertices=levels.Select(l=>Meshes(l.renderers).Sum(m=>m.vertexCount)).ToArray(),
                lod_screen_heights=levels.Select(l=>l.screenRelativeTransitionHeight).ToArray(),
                support_known=support, support_gap=gap,
                overlap_candidates=SceneLayout.Objects().Where(o=>o!=obj).Select(SceneLayout.Describe)
                    .Where(o=>SceneLayout.Overlap(state.bounds_min,state.bounds_max,state.footprint,o)).Select(o=>o.id).ToArray() };
        }
    }
}
