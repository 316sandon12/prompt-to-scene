using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;

namespace PromptToScene.Editor
{
    [Serializable] public class AdaptRow
    {
        public string id, path, renderer, before, after, before_guid, after_guid, before_hash, after_hash, status;
        public int slot;
        public long before_local_id,after_local_id;
        public string[] fields;
    }
    [Serializable] public class AdaptAsset { public string path, variant; }
    [Serializable] public class AdaptPlan
    {
        public string plan_id, reference, status;
        public AdaptRow[] entries;
        public AdaptAsset[] assets;
        public string[] warnings;
    }
    public static class MaterialAdaptation
    {
        static string FilePath(string id)
        {
            if(!System.Text.RegularExpressions.Regex.IsMatch(id??"", "^[a-f0-9]{32}$")) throw new Exception("Invalid adaptation ID");
            return Path.Combine(AssetBridge.StateRoot,"adaptation",id+".json");
        }
        static void Save(AdaptPlan plan) => AssetBridge.WriteJson(FilePath(plan.plan_id),plan);
        static string Property(Material m, params string[] names) => names.FirstOrDefault(n=>m.HasProperty(n));
        static string Hash(Material m) => AssetDatabase.GetAssetDependencyHash(AssetDatabase.GetAssetPath(m)).ToString();
        static Material Resolve(string guid,long localId)
        {
            string path=AssetDatabase.GUIDToAssetPath(guid);
            return AssetDatabase.LoadAllAssetsAtPath(path).OfType<Material>().FirstOrDefault(m=>AssetDatabase.TryGetGUIDAndLocalFileIdentifier(m,out string g,out long id)&&id==localId&&g==guid);
        }
        static Material Reference(string path)
        {
            var m=AssetDatabase.LoadAssetAtPath<Material>(path); if(m)return m;
            var obj=AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if(!obj)throw new Exception("Select a material or model as reference");
            m=obj.GetComponentsInChildren<Renderer>(true).SelectMany(r=>r.sharedMaterials).FirstOrDefault(v=>v);
            if(!m)throw new Exception("Reference has no material");return m;
        }
        static List<string> CopyValues(Material source, Material target, string[] fields)
        {
            var applied=new List<string>();
            foreach(string field in fields)
            {
                string a=null,b=null;
                if(field=="color")
                { a=Property(source,"_BaseColor","_Color");b=Property(target,"_BaseColor","_Color");if(a!=null&&b!=null)target.SetColor(b,source.GetColor(a)); }
                else if(field=="roughness")
                {
                    a=Property(source,"_Smoothness","_Glossiness","_Roughness"); b=Property(target,"_Smoothness","_Glossiness","_Roughness");
                    // A packed gloss map controls smoothness directly; changing a scalar would misrepresent the preview.
                    if(source.HasProperty("_MetallicGlossMap")&&source.GetTexture("_MetallicGlossMap"))a=null;
                    if(target.HasProperty("_MetallicGlossMap")&&target.GetTexture("_MetallicGlossMap"))b=null;
                    if(a!=null&&b!=null){float rough=a=="_Roughness"?source.GetFloat(a):1-source.GetFloat(a);target.SetFloat(b,b=="_Roughness"?rough:1-rough);}
                }
                else if(field=="texture_scale")
                {
                    a=Property(source,"_BaseMap","_MainTex");b=Property(target,"_BaseMap","_MainTex");
                    if(a!=null&&b!=null) foreach(var p in new[]{"_BaseMap","_MainTex","_BumpMap","_MetallicGlossMap","_OcclusionMap","_EmissionMap"}.Where(target.HasProperty))target.SetTextureScale(p,source.GetTextureScale(a));
                }
                if(a!=null&&b!=null)applied.Add(field);
            }
            return applied;
        }
        static Renderer RendererAt(GameObject root,string path) => (path==""?root.transform:root.transform.Find(path))?.GetComponent<Renderer>();
        public static SceneResult Execute(SceneAction action,DevelopmentCommand c)
        {
            AdaptPlan plan;
            if(c.mode=="preview")
            {
                if(c.paths==null||c.paths.Length<1||c.paths.Length>20)throw new Exception("Choose 1–20 prefabs");
                var reference=Reference(c.path);var fields=c.slots??new[]{"color","roughness","texture_scale"};
                if(fields.Any(f=>!new[]{"color","roughness","texture_scale"}.Contains(f)))throw new Exception("Unsupported material field");
                string id=action.request_id; var rows=new List<AdaptRow>();var assets=new List<AdaptAsset>();var warnings=new List<string>();
                string folder="Assets/PromptToScene/Adaptation/"+id;
                Directory.CreateDirectory(Path.Combine(AssetBridge.ProjectRoot,folder));AssetDatabase.Refresh();
                foreach(string path in c.paths.Distinct())
                {
                    if(!path.StartsWith("Assets/")||!path.EndsWith(".prefab")||path.Contains(".."))throw new Exception("Material adaptation targets must be Unity prefabs; use the generated prefab for imported models");
                    var source=AssetDatabase.LoadAssetAtPath<GameObject>(path);if(!source)throw new Exception("Prefab missing: "+path);
                    var clone=UnityEngine.Object.Instantiate(source);clone.name=source.name;
                    try
                    {
                        foreach(var r in clone.GetComponentsInChildren<Renderer>(true))
                        {
                            string relative=AnimationUtility.CalculateTransformPath(r.transform,clone.transform);var materials=r.sharedMaterials;
                            for(int i=0;i<materials.Length;i++)
                            {
                                var before=materials[i];if(!before)continue;
                                if(rows.Count>=200)throw new Exception("At most 200 material slots per adaptation");
                                var after=new Material(before);var copied=CopyValues(reference,after,fields);
                                if(copied.Count==0){UnityEngine.Object.DestroyImmediate(after);warnings.Add(path+" / "+relative+": shader properties unsupported");continue;}
                                if(copied.Count!=fields.Length)warnings.Add(path+" / "+relative+": applied "+string.Join(", ",copied)+"; unsupported properties skipped");
                                string native=folder+"/M_"+rows.Count+".mat";AssetDatabase.CreateAsset(after,native);
                                string original=AssetDatabase.GetAssetPath(before);
                                if(!AssetDatabase.TryGetGUIDAndLocalFileIdentifier(before,out string beforeGuid,out long beforeLocal)||!AssetDatabase.TryGetGUIDAndLocalFileIdentifier(after,out string afterGuid,out long afterLocal))throw new Exception("Material has no persistent identity");
                                rows.Add(new AdaptRow{id=rows.Count.ToString(),path=path,renderer=relative,slot=i,before=original,after=native,
                                    before_guid=beforeGuid,after_guid=afterGuid,before_local_id=beforeLocal,after_local_id=afterLocal,before_hash=Hash(before),status="planned",fields=copied.ToArray()});
                                materials[i]=after;
                            }
                            r.sharedMaterials=materials;
                        }
                        string variant=folder+"/PF_"+assets.Count+".prefab";PrefabUtility.SaveAsPrefabAsset(clone,variant);assets.Add(new AdaptAsset{path=path,variant=variant});
                    }
                    finally {UnityEngine.Object.DestroyImmediate(clone);}
                }
                AssetDatabase.SaveAssets();
                foreach(var row in rows)row.after_hash=Hash(AssetDatabase.LoadAssetAtPath<Material>(row.after));
                plan=new AdaptPlan{plan_id=id,reference=c.path,status="preview",entries=rows.ToArray(),assets=assets.ToArray(),warnings=warnings.ToArray()};Save(plan);
            }
            else
            {
                if(c.mode!="apply"&&c.mode!="undo")throw new Exception("Choose preview, apply or undo");
                plan=JsonUtility.FromJson<AdaptPlan>(File.ReadAllText(FilePath(c.plan_id)));
                var chosen=plan.entries.Where(r=>(c.slots==null||c.slots.Length==0||c.slots.Contains(r.id))&&(c.mode=="undo"?r.status=="applied":r.status!="applied")).ToArray();
                // Validate every target before changing any prefab. Later manual edits are conflicts, never overwritten.
                foreach(var row in chosen)
                {
                    var obj=AssetDatabase.LoadAssetAtPath<GameObject>(row.path);var r=obj?RendererAt(obj,row.renderer):null;
                    var expected=c.mode=="undo"?Resolve(row.after_guid,row.after_local_id):Resolve(row.before_guid,row.before_local_id);
                    if(!expected||!Resolve(row.before_guid,row.before_local_id)||!Resolve(row.after_guid,row.after_local_id)||!r||r.sharedMaterials.Length<=row.slot||r.sharedMaterials[row.slot]!=expected)
                        throw new Exception("Material assignment changed since preview: "+row.path+" / "+row.renderer);
                    if(c.mode=="apply"&&(Hash(r.sharedMaterials[row.slot])!=row.before_hash||Hash(AssetDatabase.LoadAssetAtPath<Material>(row.after))!=row.after_hash))
                        throw new Exception("Material content changed; create a new preview");
                }
                foreach(var group in chosen.GroupBy(r=>r.path))
                {
                    var obj=PrefabUtility.LoadPrefabContents(group.Key);
                    try
                    {
                        foreach(var row in group){var r=RendererAt(obj,row.renderer);var mats=r.sharedMaterials;mats[row.slot]=c.mode=="undo"?Resolve(row.before_guid,row.before_local_id):Resolve(row.after_guid,row.after_local_id);r.sharedMaterials=mats;PrefabUtility.RecordPrefabInstancePropertyModifications(r);}
                        PrefabUtility.SaveAsPrefabAsset(obj,group.Key);
                        foreach(var row in group)row.status=c.mode=="undo"?"undone":"applied";
                        Save(plan);
                    }
                    finally{PrefabUtility.UnloadPrefabContents(obj);}
                }
                AssetDatabase.SaveAssets();plan.status=c.mode=="undo"?"undone":"applied";Save(plan);
            }
            return new SceneResult{request_id=action.request_id,development=new DevelopmentResult{command="adapt",plan_id=plan.plan_id,changed=plan.entries.Count(r=>r.status=="applied"),warnings=plan.warnings,message="Reference material adaptation: "+plan.status}};
        }
    }
}
