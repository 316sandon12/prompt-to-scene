using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using Object = UnityEngine.Object;

namespace PromptToScene.Editor
{
    [Serializable] public class MaterialBinding { public string slot, material_path; }
    [Serializable] public class SocketSetting { public string name; public float[] position, rotation; }
    [Serializable] public class BlockSetting { public string name, material; public float[] position, size; public float yaw; }
    [Serializable] public class Checkpoint { public float[] position; }
    [Serializable] public class DevelopmentCommand
    {
        public string command, mode, template, moving_asset_id, preset, level_id, path, candidate_request_id;
        public string scope_path, plan_id, plan_sha256;
        public string event_id, label, depleted_asset_id;
        public int uses = 3;
        public float[] interaction_point = new float[] { 0, 0, 0 };
        public float angle, distance, duration, player_radius, player_height, max_step;
        public float[] pivot, offset, position;
        public bool demo_input, capture, preserve_configuration;
        public int module_count;
        public string[] slots, asset_ids, object_names, paths;
        public MaterialBinding[] bindings;
        public SocketSetting[] sockets;
        public BlockSetting[] boxes;
        public Checkpoint[] checkpoints;
    }
    [Serializable] public class LibraryEntry
    {
        public string path, name, kind, thumbnail, asset_id;
        public string[] tags;
        public float[] size;
        public int triangles;
    }
    [Serializable] public class PlayAssertion
    { public string asset_id, check, detail; public bool passed; }
    [Serializable] public class DevelopmentResult
    {
        public string command, message, preset, template, prefab, level_id, candidate_request_id;
        public string mode, plan_id, scan_id, organization_status;
        public string plan_json;
        public bool passed, truncated;
        public int changed, module_count, samples, frames;
        public float mean_frame_ms, p95_frame_ms;
        public string[] conflicts, warnings, screenshots;
        public MaterialBinding[] bindings;
        public SocketSetting[] sockets;
        public LibraryEntry[] entries;
        public PlayAssertion[] checks;
    }

    public static class DevelopmentActions
    {
        public static UnityEngine.SceneManagement.Scene Scene => UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        public static Vector3 Vec(float[] v) { if(v==null || v.Length!=3 || v.Any(x=>float.IsNaN(x)||float.IsInfinity(x))) throw new Exception("Expected three finite coordinates"); return new Vector3(v[0],v[1],v[2]); }
        public static T Ensure<T>(GameObject obj) where T:Component {var component=obj.GetComponent<T>();return component?component:obj.AddComponent<T>();}
        public static float[] Vec(Vector3 v) => new[]{v.x,v.y,v.z};
        public static T[] Loaded<T>() where T:Component => Resources.FindObjectsOfTypeAll<T>().Where(o=>!EditorUtility.IsPersistent(o) && o.gameObject.scene==Scene).ToArray();
        public static AssetIdentity[] Assets(string id) => Loaded<AssetIdentity>().Where(a=>!a.nestedPart && a.assetId==id).ToArray();
        public static SceneResult Execute(SceneAction a)
        {
            var c=JsonUtility.FromJson<DevelopmentCommand>(a.development_json);
            if(c==null) throw new Exception("Missing development command");
            var result=new SceneResult{request_id=a.request_id,scene=Scene.path};
            switch(c.command)
            {
                case "interaction": result.development=Configure(a.asset_id,c); break;
                case "protection": result.development=SceneProtection.Edit(a.asset_id,c); break;
                case "update_review": result.development=SceneProtection.Review(a.asset_id,c); break;
                case "look": return ScenePresentation.Execute(a,c);
                case "level": result.development=Level(c); break;
                case "library": return Library(a,c);
                case "playcheck": return PlayChecks.Start(a,c);
                case "organize": return AssetOrganization.Execute(a,c);
                case "adapt": return MaterialAdaptation.Execute(a,c);
                default: throw new Exception("Unknown development command");
            }
            return result;
        }

        static DevelopmentResult Configure(string id, DevelopmentCommand c)
        {
            if(!new[]{"door","chest","pickup","resource","switch"}.Contains(c.template) || c.distance<.1f || c.distance>20 || Mathf.Abs(c.angle)>170 || c.uses<1 || c.uses>1000)
                throw new Exception("Invalid interaction settings");
            string path=NativeLocations.Get(id).Prefab;
            var source=AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if(!source) throw new Exception("Import the base asset first");
            GameObject moving=null;
            if(c.template=="door" || c.template=="chest")
            {
                moving=AssetDatabase.LoadAssetAtPath<GameObject>(NativeLocations.Get(c.moving_asset_id).Prefab);
                if(!moving || c.moving_asset_id==id) throw new Exception("Import a separate moving asset first");
            }
            var root=PrefabUtility.LoadPrefabContents(path);
            try
            {
                var previousInteraction=root.GetComponent<Interaction>();
                var keep=c.preserve_configuration && previousInteraction;
                var interact=Ensure<Interaction>(root);
                if(keep && interact.template!=c.template) throw new Exception("Use configure_interaction explicitly to change the template kind");
                interact.template=c.template;
                if(!keep){interact.interactionRange=c.distance; interact.demoInput=c.demo_input;}
                if(!keep)
                {
                    interact.eventId=c.event_id ?? ""; interact.interactionLabel=c.label ?? "";
                    interact.usesRequired=c.uses; interact.interactionPoint=Vec(c.interaction_point);
                    var depleted=root.transform.Find("DepletedVisual");
                    if(depleted) Object.DestroyImmediate(depleted.gameObject);
                    interact.depletedVisual=null;
                    if(!string.IsNullOrEmpty(c.depleted_asset_id))
                    {
                        var depletedSource=AssetDatabase.LoadAssetAtPath<GameObject>(NativeLocations.Get(c.depleted_asset_id).Prefab);
                        if(!depletedSource) throw new Exception("Import the depleted-state asset first");
                        var instance=(GameObject)PrefabUtility.InstantiatePrefab(depletedSource,root.scene);
                        instance.transform.SetParent(root.transform,false);instance.name="DepletedVisual";
                        instance.GetComponent<AssetIdentity>().nestedPart=true;
                        instance.SetActive(false);interact.depletedVisual=instance;
                    }
                }
                var pivot=root.transform.Find("MovingPivot");
                if(!pivot) {pivot=new GameObject("MovingPivot").transform; pivot.SetParent(root.transform,false);}
                pivot.localPosition=Vec(c.pivot); pivot.localRotation=Quaternion.identity;
                interact.movingPivot=pivot;
                if(!keep)interact.openRotation=c.template=="chest"?new Vector3(-c.angle,0,0):new Vector3(0,c.angle,0);
                if(moving)
                {
                    var child=pivot.Find("MovingVisual");
                    if(child && child.GetComponent<AssetIdentity>().assetId!=c.moving_asset_id){Object.DestroyImmediate(child.gameObject);child=null;}
                    if(!child) { var instance=(GameObject)PrefabUtility.InstantiatePrefab(moving,root.scene); child=instance.transform; child.SetParent(pivot,false); child.name="MovingVisual"; }
                    child.localPosition=Vec(c.offset);
                    child.GetComponent<AssetIdentity>().nestedPart=true;
                    PrefabUtility.RecordPrefabInstancePropertyModifications(child.GetComponent<AssetIdentity>());
                    AddMeshColliders(child.gameObject);
                }
                else {var child=pivot.Find("MovingVisual");if(child)Object.DestroyImmediate(child.gameObject);}
                AddMeshColliders(root.transform.Find("Visual").gameObject);
                var oldBox=root.GetComponent<BoxCollider>(); if(oldBox) Object.DestroyImmediate(oldBox);
                PrefabUtility.SaveAsPrefabAsset(root,path);
            }
            finally { PrefabUtility.UnloadPrefabContents(root); }
            if(moving) foreach(var leaf in Assets(c.moving_asset_id)) Undo.DestroyObjectImmediate(leaf.gameObject);
            AssetDatabase.SaveAssets(); EditorSceneManager.MarkSceneDirty(Scene); Physics.SyncTransforms();
            return new DevelopmentResult{command="interaction",template=c.template,prefab=path,changed=Assets(id).Length,
                message="TryInteract(worldPosition) and onInteracted are ready. Demo input: aim the main camera and press E."};
        }
        public static void AddMeshColliders(GameObject root)
        {
            foreach(var mesh in root.GetComponentsInChildren<MeshFilter>())
            {
                if(mesh.name.StartsWith("LOD") && mesh.name!="LOD0") continue;
                if(mesh.GetComponentsInParent<Transform>().Any(t=>t.name.StartsWith("LOD") && t.name!="LOD0")) continue;
                var col=Ensure<MeshCollider>(mesh.gameObject);
                col.sharedMesh=mesh.sharedMesh;
            }
        }
        public static string[] Clearance(LevelMarker level, GameObject ignore=null)
        {
            Physics.SyncTransforms(); var failures=new HashSet<string>();
            foreach(var p in level.checkpoints)
            {
                var low=p+Vector3.up*level.playerRadius;
                var high=p+Vector3.up*(level.playerHeight-level.playerRadius);
                foreach(var hit in Physics.OverlapCapsule(low,high,level.playerRadius,~0,QueryTriggerInteraction.Ignore))
                { if(ignore && hit.transform.IsChildOf(ignore.transform)) continue;
                  if(hit.bounds.max.y <= p.y+level.maxStep+.005f) continue;
                  failures.Add(hit.name); }
                if(failures.Count>20) break;
            }
            return failures.ToArray();
        }
        static DevelopmentResult Level(DevelopmentCommand c)
        {
            var previous=Loaded<LevelMarker>().FirstOrDefault(l=>l.levelId==c.level_id);
            if(c.mode=="inspect")
            {
                if(!previous) throw new Exception("Generated level is not loaded");
                var plan=new DevelopmentCommand {
                    boxes=previous.GetComponentsInChildren<MeshRenderer>().Select(r=>new BlockSetting {
                        name=r.name,position=Vec(r.transform.position),size=Vec(r.transform.lossyScale),
                        yaw=r.transform.eulerAngles.y,material=r.name.StartsWith("floor")?"floor":"wall"
                    }).ToArray(),
                    checkpoints=previous.checkpoints.Select(p=>new Checkpoint{position=Vec(p)}).ToArray(),
                    player_radius=previous.playerRadius,player_height=previous.playerHeight,max_step=previous.maxStep
                };
                return new DevelopmentResult{command="level",level_id=c.level_id,plan_json=JsonUtility.ToJson(plan)};
            }
            if(c.mode=="check")
            {
                if(!previous) throw new Exception("Generated level is not loaded");
                var conflicts=Clearance(previous);
                return new DevelopmentResult{command="level",level_id=c.level_id,passed=conflicts.Length==0,conflicts=conflicts,samples=previous.checkpoints.Length,module_count=previous.moduleCount};
            }
            if(c.mode=="remove") {if(previous) Undo.DestroyObjectImmediate(previous.gameObject); return new DevelopmentResult{command="level",changed=previous?1:0};}
            if(c.mode!="build" || c.boxes==null || c.boxes.Length>1000 || c.checkpoints==null || c.checkpoints.Length>2000)
                throw new Exception("Invalid level plan");
            var root=new GameObject("PTS Level: "+c.level_id);
            try
            {
                var marker=root.AddComponent<LevelMarker>(); marker.levelId=c.level_id;
                marker.checkpoints=c.checkpoints.Select(p=>Vec(p.position)).ToArray();
                marker.playerRadius=c.player_radius; marker.playerHeight=c.player_height; marker.moduleCount=c.module_count;marker.maxStep=c.max_step;
                foreach(var b in c.boxes)
                {
                    var size=Vec(b.size); if(size.x<=0||size.y<=0||size.z<=0) throw new Exception("Invalid block size");
                    var cube=GameObject.CreatePrimitive(PrimitiveType.Cube); cube.name=b.name; cube.transform.SetParent(root.transform,false);
                    cube.transform.position=Vec(b.position); cube.transform.localScale=size; cube.transform.rotation=Quaternion.Euler(0,b.yaw,0);
                    cube.GetComponent<Renderer>().sharedMaterial=LevelMaterial(b.material);
                }
                var conflicts=Clearance(marker,previous?previous.gameObject:null);
                if(conflicts.Length>0) throw new Exception("Walk clearance blocked by: "+string.Join(", ",conflicts));
                if(previous) Undo.DestroyObjectImmediate(previous.gameObject);
                Undo.RegisterCreatedObjectUndo(root,"Build Prompt-to-Scene level");
                EditorSceneManager.MarkSceneDirty(Scene);
                return new DevelopmentResult{command="level",level_id=c.level_id,changed=c.boxes.Length,passed=true,module_count=c.module_count,samples=marker.checkpoints.Length};
            }
            catch {Object.DestroyImmediate(root); throw;}
        }
        static Material LevelMaterial(string name)
        {
            if(!new[]{"floor","wall","trim"}.Contains(name))throw new Exception("Unknown block material");
            string folder="Assets/PromptToScene/LevelMaterials"; if(!Directory.Exists(folder)){Directory.CreateDirectory(folder); AssetDatabase.Refresh();}
            string path=folder+"/"+name+".mat"; var material=AssetDatabase.LoadAssetAtPath<Material>(path);
            if(!material)
            {
                material=new Material(Shader.Find(AssetBridge.Pipeline.Contains("Universal")?"Universal Render Pipeline/Lit":"Standard"));
                material.color=name=="floor"?new Color(.30f,.25f,.20f):name=="trim"?new Color(.24f,.38f,.40f):new Color(.73f,.69f,.58f);
                material.SetFloat("_Smoothness",.25f); material.SetFloat("_Glossiness",.25f);
                AssetDatabase.CreateAsset(material,path);
            }
            return material;
        }
        static SceneResult Library(SceneAction a, DevelopmentCommand c)
        {
            var result=new SceneResult{request_id=a.request_id,scene=Scene.path,development=new DevelopmentResult{command="library"}};
            if(c.mode=="index")
            {
                var paths=AssetDatabase.FindAssets("t:GameObject",new[]{"Assets"}).Select(AssetDatabase.GUIDToAssetPath).OrderBy(p=>p).ToArray();
                var entries=new List<LibraryEntry>();
                foreach(var path in paths.Take(2000))
                {
                    var obj=AssetDatabase.LoadAssetAtPath<GameObject>(path); if(!obj) continue;
                    var meshes=obj.GetComponentsInChildren<MeshFilter>(); if(meshes.Length==0) continue;
                    var renderers=obj.GetComponentsInChildren<Renderer>();
                    if(renderers.Length==0) continue;
                    Bounds bounds=renderers[0].bounds; foreach(var r in renderers.Skip(1)) bounds.Encapsulate(r.bounds);
                    var tags=AssetDatabase.GetLabels(obj).Concat(renderers.SelectMany(r=>r.sharedMaterials).Where(m=>m).Select(m=>m.name)).Distinct().ToArray();
                    entries.Add(new LibraryEntry{path=path,name=obj.name,kind=path.EndsWith(".prefab")?"prefab":"model",size=Vec(bounds.size),
                        asset_id=obj.GetComponent<AssetIdentity>()?.assetId,tags=tags,triangles=meshes.Where(m=>m.sharedMesh).Sum(m=>Enumerable.Range(0,m.sharedMesh.subMeshCount).Sum(i=>(int)m.sharedMesh.GetIndexCount(i)/3))});
                }
                result.development.entries=entries.ToArray(); result.development.truncated=paths.Length>2000; return result;
            }
            if(string.IsNullOrEmpty(c.path)||!c.path.StartsWith("Assets/")||c.path.Contains("..")) throw new Exception("Asset must be inside Assets/");
            var source=AssetDatabase.LoadAssetAtPath<GameObject>(c.path); if(!source) throw new Exception("Project model/prefab is missing");
            if(c.mode=="preview")
            {
                string file=Path.Combine(AssetBridge.StateRoot,"previews",a.request_id+".png");
                ScenePresentation.PreviewAsset(source,file); result.preview="previews/"+a.request_id+".png"; return result;
            }
            if(c.mode!="place") throw new Exception("Choose index, preview or place");
            var instance=(GameObject)PrefabUtility.InstantiatePrefab(source,Scene); instance.transform.position=Vec(c.position);
            Undo.RegisterCreatedObjectUndo(instance,"Reuse project asset"); Selection.activeGameObject=instance;
            EditorSceneManager.MarkSceneDirty(Scene); result.development.changed=1; return result;
        }
    }
}
