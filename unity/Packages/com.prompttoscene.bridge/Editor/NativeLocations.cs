using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEngine;

namespace PromptToScene.Editor
{
    [Serializable] public class NativeLayout
    {
        public string folder, model, prefab, blueprint, materials, textures, material_prefix, texture_prefix;
        public string File(string name) => folder + "/" + (name == "model.fbx" ? model + ".fbx" :
            name.StartsWith("lod_") ? (model == "model" ? name : model + "_" + name) :
            textures + texture_prefix + name.Substring(4));
        public string Prefab => folder + "/" + prefab + ".prefab";
    }
    public static class NativeLocations
    {
        public static NativeLayout Get(string id)
        {
            var path=Path.Combine(AssetBridge.StateRoot,"locations",id+".json");
            var layout=File.Exists(path)?JsonUtility.FromJson<NativeLayout>(File.ReadAllText(path)):
                new NativeLayout{folder="Assets/PromptToScene/"+id,model="model",prefab=id,materials="",textures="",material_prefix="mat_",texture_prefix="tex_"};
            Validate(layout); return layout;
        }
        public static void Validate(NativeLayout v)
        {
            if(v==null || !v.folder.StartsWith("Assets/") || !v.folder.Contains("/PromptToScene/") ||
                !Regex.IsMatch(v.folder,@"^Assets/[A-Za-z0-9_/ -]+$") || v.folder.Contains("//"))
                throw new Exception("Invalid managed asset folder");
            foreach(var s in new[]{v.model,v.prefab,v.materials,v.textures,v.material_prefix,v.texture_prefix})
                if(s==null || !Regex.IsMatch(s,@"^[A-Za-z0-9_/]*$") || s.Contains("//") || s.StartsWith("/"))
                    throw new Exception("Invalid managed asset convention");
        }
    }
}
