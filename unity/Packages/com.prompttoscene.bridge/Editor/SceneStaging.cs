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
    [Serializable] public class MaterialEvidence
    {
        public string object_id, path, shader, color_property;
        public float[] color;
        public float roughness = -1;
    }
    [Serializable] public class SceneStage
    {
        public string mode, plan_id, scene, asset_id, model_revision, camera_id;
        public SceneCamera camera;
        public SceneObject target, source;
        public Placement placement;
        public bool replace_target;
        public float[] clearance_m;
    }
    [Serializable] public class StageJournal
    {
        public SceneStage plan;
        public SceneObject after;
        public bool target_active, undone;
    }

    // Transient previews contain only geometry and materials; user scripts never run on copies.
    public static class SceneStaging
    {
        static string Root => AssetBridge.StateRoot;
        static Vector3 Vec(float[] v) => new Vector3(v[0], v[1], v[2]);
        static bool Near(float[] a, float[] b) => a != null && b != null && a.Length == b.Length && a.Zip(b,(x,y)=>Mathf.Abs(x-y)<.002f).All(x=>x);
        static bool Same(SceneObject a, SceneObject b) => a != null && b != null && a.id == b.id
            && Near(a.position,b.position) && Near(a.rotation,b.rotation) && Near(a.scale,b.scale)
            && Near(a.bounds_min,b.bounds_min) && Near(a.bounds_max,b.bounds_max)
            && JsonUtility.ToJson(new SceneResult { objects = new[]{a} }) == JsonUtility.ToJson(new SceneResult { objects = new[]{b} });
        static string Journal(string id) => Path.Combine(Root,"native-scene-trials",id+".json");

        static MaterialEvidence[] Materials(SceneObject[] context)
        {
            var rows = new List<MaterialEvidence>();
            foreach(var item in context.Take(40))
            {
                var obj=SceneLayout.Find(item.id); if(!obj) continue;
                foreach(var m in obj.GetComponentsInChildren<Renderer>().SelectMany(r=>r.sharedMaterials).Where(m=>m).Distinct().Take(8))
                {
                    var prop=m.HasProperty("_BaseColor")?"_BaseColor":m.HasProperty("_Color")?"_Color":"";
                    var c=prop!=""?m.GetColor(prop):Color.clear;
                    rows.Add(new MaterialEvidence { object_id=item.id,path=AssetDatabase.GetAssetPath(m),shader=m.shader.name,
                        color_property=prop,color=prop!=""?new[]{c.r,c.g,c.b,c.a}:null,
                        roughness=m.HasProperty("_Roughness")?m.GetFloat("_Roughness"):m.HasProperty("_Smoothness")?1-m.GetFloat("_Smoothness"):m.HasProperty("_Glossiness")?1-m.GetFloat("_Glossiness"):-1 });
                }
            }
            return rows.ToArray();
        }

        static void Validate(SceneStage p,string scene,bool undo=false)
        {
            if(p.scene!=scene) throw new Exception("Scene changed; capture the target again");
            var receipt=Path.Combine(Root,"receipts",p.asset_id+".json");
            if(!File.Exists(receipt) || JsonUtility.FromJson<SceneResult>(File.ReadAllText(receipt)).request_id!=p.model_revision)
                throw new Exception("Model revision changed; prepare another preview");
            if(undo) return;
            var source=SceneLayout.Find(p.source.id);var target=SceneLayout.Find(p.target.id);
            if(!source || !target || !Same(SceneLayout.Describe(source),p.source) || !Same(SceneLayout.Describe(target),p.target))
                throw new Exception("Target or model changed; prepare another preview");
            var camera=SceneActions.Cameras().FirstOrDefault(c=>c.id==p.camera_id);
            if(camera==null || JsonUtility.ToJson(camera)!=JsonUtility.ToJson(p.camera))
                throw new Exception("Camera changed; prepare another preview");
            foreach(var o in SceneLayout.Objects().Where(o=>o!=source && o!=target).Select(SceneLayout.Describe).Where(o=>o.has_collision))
            {
                if(SceneLayout.Overlap(p.placement.bounds_min,p.placement.bounds_max,p.placement.footprint,o))
                    throw new Exception("Placement overlaps "+o.name);
                if(p.clearance_m!=null && p.clearance_m.Any(v=>v>0) && SceneLayout.Overlap(
                    p.placement.bounds_min.Select((v,i)=>v-p.clearance_m[i]).ToArray(),
                    p.placement.bounds_max.Select((v,i)=>v+p.clearance_m[i]).ToArray(),null,o))
                    throw new Exception("Reserved interaction space overlaps "+o.name);
            }
        }

        static GameObject CopyGeometry(Transform source,Transform parent)
        {
            var obj=new GameObject(source.name) { hideFlags=HideFlags.HideAndDontSave, layer=source.gameObject.layer };
            obj.transform.SetParent(parent,false);obj.transform.localPosition=source.localPosition;
            obj.transform.localRotation=source.localRotation;obj.transform.localScale=source.localScale;
            var filter=source.GetComponent<MeshFilter>();var renderer=source.GetComponent<MeshRenderer>();
            if(filter && renderer && renderer.enabled)
            {
                obj.AddComponent<MeshFilter>().sharedMesh=filter.sharedMesh;
                var copy=obj.AddComponent<MeshRenderer>();copy.sharedMaterials=renderer.sharedMaterials;
                copy.shadowCastingMode=renderer.shadowCastingMode;copy.receiveShadows=renderer.receiveShadows;
                copy.lightProbeUsage=renderer.lightProbeUsage;copy.reflectionProbeUsage=renderer.reflectionProbeUsage;
                copy.renderingLayerMask=renderer.renderingLayerMask;
                var block=new MaterialPropertyBlock();renderer.GetPropertyBlock(block);copy.SetPropertyBlock(block);
                for(int i=0;i<renderer.sharedMaterials.Length;i++){block.Clear();renderer.GetPropertyBlock(block,i);copy.SetPropertyBlock(block,i);}
            }
            foreach(Transform child in source) if(child.gameObject.activeSelf) CopyGeometry(child,obj.transform);
            return obj;
        }

        public static SceneResult Execute(SceneAction request,string scene)
        {
            var p=JsonUtility.FromJson<SceneStage>(request.scene_json);
            if(p==null) throw new Exception("Missing scene operation");
            var result=new SceneResult { request_id=request.request_id,scene=scene };
            request.view="game";request.camera_id=p.camera_id;
            string output=Path.Combine(Root,"previews",request.request_id+".png");
            if(p.mode=="reference")
            {
                result.context=SceneLayout.Objects().Select(SceneLayout.Describe).ToArray();
                result.selected_context=SceneLayout.Selected();result.cameras=SceneActions.Cameras();
                result.assets=result.context.Where(o=>!string.IsNullOrEmpty(o.asset_id)).ToArray();
                if(string.IsNullOrEmpty(p.camera_id))
                {
                    var preferred=result.cameras.Where(c=>c.primary).ToArray();
                    var choices=preferred.Length>0?preferred:result.cameras;
                    if(choices.Length!=1) throw new Exception("Choose one game camera before capturing the scene");
                    request.camera_id=choices[0].id;
                }
                var center=result.selected_context.FirstOrDefault()?.position ?? result.cameras.FirstOrDefault(c=>c.id==request.camera_id)?.position ?? new float[3];
                result.materials=Materials(result.context.Concat(result.selected_context).GroupBy(o=>o.id).Select(g=>g.First())
                    .OrderBy(o=>(Vec(o.position)-Vec(center)).sqrMagnitude).ToArray());
                SceneActions.Capture(new GameObject[0],output,request);
                result.reference_camera_id=request.camera_id;result.preview="previews/"+request.request_id+".png";return result;
            }
            if(!Regex.IsMatch(p.plan_id??"","^[a-f0-9]{32}$")) throw new Exception("Invalid preview ID");
            if(p.mode=="undo")
            {
                var journal=JsonUtility.FromJson<StageJournal>(File.ReadAllText(Journal(p.plan_id)));
                Validate(journal.plan,scene,true);
                if(journal.undone) return result;
                var source=SceneLayout.Find(journal.after.id);var target=SceneLayout.Find(journal.plan.target.id);
                if(!source || !target || !Same(SceneLayout.Describe(source),journal.after)
                    || (journal.plan.replace_target && target.activeSelf)) throw new Exception("Objects changed after adoption; undo was not applied");
                SceneActions.Restore(source,journal.plan.source);
                if(journal.plan.replace_target){Undo.RecordObject(target,"Restore placeholder");target.SetActive(journal.target_active);}
                journal.undone=true;AssetBridge.WriteJson(Journal(p.plan_id),journal);
                EditorSceneManager.MarkSceneDirty(source.scene);result.changed=1;return result;
            }
            if(p.mode=="adopt" && File.Exists(Journal(p.plan_id)))
            {
                var saved=JsonUtility.FromJson<StageJournal>(File.ReadAllText(Journal(p.plan_id)));
                if(saved.undone) throw new Exception("This preview was undone; prepare a new one");
                result.scene_trial_id=p.plan_id;return result;
            }
            Validate(p,scene);
            var original=SceneLayout.Find(p.source.id);var anchor=SceneLayout.Find(p.target.id);
            if(p.mode=="adopt")
            {
                var journal=new StageJournal { plan=p,target_active=anchor.activeSelf };
                // Existing layout validation rechecks collision and preserves the source pose.
                var edit=new SceneAction { request_id=request.request_id,scene=scene,anchor=p.target,placements=new[]{p.placement},ignore_noncolliding=true };
                SceneLayout.Arrange(edit,scene);
                if(p.replace_target){Undo.RecordObject(anchor,"Replace placeholder");anchor.SetActive(false);}
                journal.after=SceneLayout.Describe(original);AssetBridge.WriteJson(Journal(p.plan_id),journal);
                result.scene_trial_id=p.plan_id;result.changed=1;return result;
            }
            if(p.mode!="before" && p.mode!="trial") throw new Exception("Unknown scene operation");
            GameObject copy=null;var hidden=new Dictionary<Renderer,bool>();
            try
            {
                if(p.mode=="trial")
                {
                    if(original.GetComponentsInChildren<SkinnedMeshRenderer>().Length>0) throw new Exception("Scene placement preview currently supports static meshes");
                    copy=CopyGeometry(original.transform,original.transform.parent);
                    copy.transform.SetPositionAndRotation(Vec(p.placement.position),Quaternion.Euler(Vec(p.placement.rotation)));
                    copy.transform.localScale=Vec(p.placement.scale);
                    foreach(var r in original.GetComponentsInChildren<Renderer>().Concat(p.replace_target?anchor.GetComponentsInChildren<Renderer>():new Renderer[0]))
                    { hidden[r]=r.forceRenderingOff;r.forceRenderingOff=true; }
                }
                SceneActions.Capture(new GameObject[0],output,request);
            }
            finally {foreach(var row in hidden) if(row.Key) row.Key.forceRenderingOff=row.Value;if(copy) Object.DestroyImmediate(copy);}
            result.preview="previews/"+request.request_id+".png";return result;
        }
    }
}
