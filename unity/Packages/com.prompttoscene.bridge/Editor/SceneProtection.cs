using System;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace PromptToScene.Editor
{
    public static class SceneProtection
    {
        public sealed class Binding {public string path, slot; public Material material;}
        public sealed class Snapshot {public GameObject root; public Binding[] bindings;}
        static Binding[] Read(GameObject root)
        {
            var id=root.GetComponent<AssetIdentity>();
            var rows=new List<Binding>();
            foreach(var slots in root.GetComponentsInChildren<ProtectedSlots>(true))
            {
                if(slots.GetComponentInParent<AssetIdentity>()!=id) continue;
                var renderer=slots.GetComponent<Renderer>(); if(!renderer) continue;
                var materials=renderer.sharedMaterials;
                for(int i=0;i<Math.Min(materials.Length,slots.names.Length);i++)
                    if(materials[i] && (i>=slots.generated.Length || materials[i]!=slots.generated[i]))
                        rows.Add(new Binding{path=AnimationUtility.CalculateTransformPath(renderer.transform,root.transform),slot=slots.names[i],material=materials[i]});
            }
            return rows.ToArray();
        }
        public static List<Snapshot> Capture(string assetId, GameObject prefab)
        {
            var list=DevelopmentActions.Loaded<AssetIdentity>().Where(a=>a.assetId==assetId).Select(a=>a.gameObject).ToList();
            if(prefab) list.Insert(0,prefab);
            return list.Select(g=>new Snapshot{root=g,bindings=Read(g)}).ToList();
        }
        public static string[] Conflicts(IEnumerable<Snapshot> snapshots, string[] names, string[] objectNames=null)
        {
            var conflicts=new HashSet<string>();
            foreach(var s in snapshots) foreach(var b in s.bindings)
            {
                if(!names.Contains(b.slot)) conflicts.Add("Protected material slot is missing: "+b.slot);
                var node=b.path.Split('/').Last();
                if(objectNames!=null && objectNames.Length>0 && !objectNames.Contains(node)) conflicts.Add("Protected renderer is missing: "+node);
            }
            return conflicts.ToArray();
        }
        public static void Restore(GameObject root, Binding[] bindings)
        {
            foreach(var b in bindings)
            {
                var child=root.transform.Find(b.path); var slots=child?child.GetComponent<ProtectedSlots>():null;
                var renderer=child?child.GetComponent<Renderer>():null;
                if(!slots || !renderer) throw new Exception("Protected renderer could not be restored: "+b.path);
                int index=Array.IndexOf(slots.names,b.slot);
                if(index<0) throw new Exception("Protected slot could not be restored: "+b.slot);
                var materials=renderer.sharedMaterials; materials[index]=b.material; renderer.sharedMaterials=materials;
                PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);
            }
        }
        public static void RegisterSlots(GameObject visual)
        {
            foreach(var renderer in visual.GetComponentsInChildren<Renderer>())
            {
                var slots=DevelopmentActions.Ensure<ProtectedSlots>(renderer.gameObject);
                slots.names=renderer.sharedMaterials.Select(m=>m?m.name:"").ToArray(); slots.generated=renderer.sharedMaterials;
            }
        }
        public static DevelopmentResult Review(string id, DevelopmentCommand c)
        {
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(NativeLocations.Get(id).Prefab);
            var snapshots=Capture(id,prefab); var conflicts=Conflicts(snapshots,c.slots??new string[0],c.object_names);
            return new DevelopmentResult{command="update_review",candidate_request_id=c.candidate_request_id,passed=conflicts.Length==0,conflicts=conflicts,
                bindings=snapshots.SelectMany(s=>s.bindings).Select(b=>new MaterialBinding{slot=b.slot,material_path=AssetDatabase.GetAssetPath(b.material)}).ToArray(),
                message="Checks protected material slots. Root components, interaction parameters and sibling attachment points survive reimport."};
        }
        public static DevelopmentResult Edit(string id, DevelopmentCommand c)
        {
            string path=NativeLocations.Get(id).Prefab;
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(path); if(!prefab) throw new Exception("Import this asset first");
            if(c.mode=="set" || c.mode=="clear")
            {
                var root=PrefabUtility.LoadPrefabContents(path);
                try
                {
                    var targets=new[]{root}.Concat(DevelopmentActions.Loaded<AssetIdentity>().Where(a=>a.assetId==id).Select(a=>a.gameObject)).ToArray();
                    var chosen=(c.bindings??new MaterialBinding[0]).Select(b=>
                    {
                        if(!b.material_path.StartsWith("Assets/")||b.material_path.Contains("..")) throw new Exception("Material must be inside Assets/");
                        var mat=AssetDatabase.LoadAssetAtPath<Material>(b.material_path); if(!mat) throw new Exception("Material is missing: "+b.material_path);
                        if(!root.GetComponentsInChildren<ProtectedSlots>().Any(s=>s.names.Contains(b.slot))) throw new Exception("Unknown material slot: "+b.slot);
                        return (b.slot,mat);
                    }).ToArray();
                    foreach(var target in targets)
                    {
                        foreach(var slots in target.GetComponentsInChildren<ProtectedSlots>(true))
                        {
                            if(slots.GetComponentInParent<AssetIdentity>().assetId!=id) continue;
                            var renderer=slots.GetComponent<Renderer>(); if(!renderer) continue;
                            var mats=renderer.sharedMaterials;
                            for(int i=0;i<slots.names.Length;i++)
                            {
                                if(c.mode=="clear") mats[i]=slots.generated[i];
                                else foreach(var pair in chosen) if(pair.slot==slots.names[i]) mats[i]=pair.mat;
                            }
                            renderer.sharedMaterials=mats; PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);
                        }
                        if(c.mode=="clear") foreach(var socket in target.GetComponentsInChildren<AttachmentPoint>()) UnityEngine.Object.DestroyImmediate(socket.gameObject);
                        foreach(var socket in c.sockets??new SocketSetting[0])
                        {
                            var node=target.GetComponentsInChildren<AttachmentPoint>().FirstOrDefault(s=>s.socketName==socket.name);
                            if(!node) {node=new GameObject("Socket_"+socket.name).AddComponent<AttachmentPoint>();node.socketName=socket.name;node.transform.SetParent(target.transform,false);}
                            node.transform.localPosition=DevelopmentActions.Vec(socket.position); node.transform.localRotation=Quaternion.Euler(DevelopmentActions.Vec(socket.rotation));
                        }
                    }
                    PrefabUtility.SaveAsPrefabAsset(root,path);
                }
                finally {PrefabUtility.UnloadPrefabContents(root);}
                AssetDatabase.SaveAssets(); EditorSceneManager.MarkSceneDirty(DevelopmentActions.Scene);
            }
            else if(c.mode!="inspect") throw new Exception("Unknown protection mode");
            var all=Capture(id,prefab);
            return new DevelopmentResult{command="protection",bindings=all.SelectMany(s=>s.bindings).Select(b=>new MaterialBinding{slot=b.slot,material_path=AssetDatabase.GetAssetPath(b.material)}).ToArray(),
                sockets=prefab.GetComponentsInChildren<AttachmentPoint>().Select(s=>new SocketSetting{name=s.socketName,position=DevelopmentActions.Vec(s.transform.localPosition),rotation=DevelopmentActions.Vec(s.transform.localEulerAngles)}).ToArray(),
                message="Custom material assignments are protected by canonical slot and renderer. Missing slots stop import. Generated material property edits remain managed."};
        }
    }
}
