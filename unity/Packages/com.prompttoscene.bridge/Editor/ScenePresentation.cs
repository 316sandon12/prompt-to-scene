using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEditor;
using UnityEditor.SceneManagement;
using Object = UnityEngine.Object;

namespace PromptToScene.Editor
{
    public static class ScenePresentation
    {
        static readonly string Folder="Assets/PromptToScene/Presentation";
        public static SceneResult Execute(SceneAction a,DevelopmentCommand c)
        {
            var rig=DevelopmentActions.Loaded<SceneLook>().FirstOrDefault();
            var result=new SceneResult{request_id=a.request_id,scene=DevelopmentActions.Scene.path,
                development=new DevelopmentResult{command="look",preset=rig?rig.preset:"none"}};
            if(c.mode=="inspect") return result;
            if(c.mode=="capture")
            {
                if(!rig || !rig.presentationCamera) throw new Exception("Apply a scene look first");
                result.preview="previews/"+a.request_id+".png";
                Capture(rig.presentationCamera,Path.Combine(AssetBridge.StateRoot,result.preview)); return result;
            }
            if(c.mode=="restore")
            {
                if(rig)
                {
                    for(int i=0;i<rig.previousLights.Length;i++) if(rig.previousLights[i]) rig.previousLights[i].enabled=rig.previousEnabled[i];
                    RenderSettings.skybox=rig.previousSky; RenderSettings.ambientMode=rig.previousAmbientMode;
                    RenderSettings.ambientLight=rig.previousAmbient; RenderSettings.fog=rig.previousFogEnabled;
                    RenderSettings.fogColor=rig.previousFog; RenderSettings.fogDensity=rig.previousFogDensity; RenderSettings.sun=rig.previousSun;
                    for(int i=0;i<rig.previousCameras.Length;i++)
                    {var camera=rig.previousCameras[i];if(!camera)continue;var data=camera.GetComponent("UniversalAdditionalCameraData");if(data) data.GetType().GetProperty("renderPostProcessing")?.SetValue(data,rig.previousPost[i]);}
                    foreach(var effect in DevelopmentActions.Loaded<BuiltinLook>().Where(e=>e.colorGrade==rig.gradeMaterial)) Object.DestroyImmediate(effect);
                    Undo.DestroyObjectImmediate(rig.gameObject); DynamicGI.UpdateEnvironment(); EditorSceneManager.MarkSceneDirty(DevelopmentActions.Scene);
                }
                result.development.message="Previous lighting and camera post processing restored"; return result;
            }
            if(c.mode!="apply" || !new[]{"warm_cartoon","cool_scifi","moonlit","neutral"}.Contains(c.preset)) throw new Exception("Unknown look preset");
            Directory.CreateDirectory(Folder); AssetDatabase.Refresh();
            if(!rig)
            {
                rig=new GameObject("PTS Scene Look").AddComponent<SceneLook>();
                rig.previousLights=DevelopmentActions.Loaded<Light>(); rig.previousEnabled=rig.previousLights.Select(l=>l.enabled).ToArray();
                rig.previousSky=RenderSettings.skybox; rig.previousAmbient=RenderSettings.ambientLight; rig.previousSun=RenderSettings.sun;
                rig.previousAmbientMode=RenderSettings.ambientMode; rig.previousFogEnabled=RenderSettings.fog;
                rig.previousFog=RenderSettings.fogColor; rig.previousFogDensity=RenderSettings.fogDensity;
                rig.previousCameras=DevelopmentActions.Loaded<Camera>();
                rig.previousPost=rig.previousCameras.Select(cam=>{var data=cam.GetComponent("UniversalAdditionalCameraData");return data && (bool)data.GetType().GetProperty("renderPostProcessing").GetValue(data);}).ToArray();
                foreach(var light in rig.previousLights) light.enabled=false;
                var camera=new GameObject("Presentation Camera").AddComponent<Camera>(); camera.transform.SetParent(rig.transform,false);
                camera.transform.position=DevelopmentActions.Vec(c.position)+new Vector3(4,3,5);
                camera.transform.LookAt(DevelopmentActions.Vec(c.position)+Vector3.up);
                camera.enabled=!rig.previousCameras.Any(cam=>cam.enabled);
                if(camera.enabled) camera.tag="MainCamera";
                camera.fieldOfView=45;camera.nearClipPlane=.05f;camera.farClipPlane=500;camera.allowHDR=true;
                rig.presentationCamera=camera; Undo.RegisterCreatedObjectUndo(rig.gameObject,"Apply scene look");
            }
            rig.preset=c.preset;
            bool night=c.preset=="moonlit",cool=c.preset=="cool_scifi";
            Color key=night?new Color(.47f,.60f,1):cool?new Color(.64f,.85f,1):c.preset=="neutral"?Color.white:new Color(1,.82f,.61f);
            SetLight(rig,"Key",new Vector3(night?25:45,-35,0),key,night?.65f:1.5f);
            SetLight(rig,"Fill",new Vector3(30,145,0),night?new Color(.22f,.35f,.65f):new Color(.60f,.78f,1),night?.16f:.35f);
            RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=night?new Color(.06f,.08f,.15f):new Color(.30f,.33f,.40f);
            var sky=AssetDatabase.LoadAssetAtPath<Material>(Folder+"/Sky.mat");
            if(!sky){sky=new Material(Shader.Find("Skybox/Procedural"));AssetDatabase.CreateAsset(sky,Folder+"/Sky.mat");}
            sky.SetColor("_SkyTint",night?new Color(.08f,.12f,.25f):cool?new Color(.35f,.55f,.67f):new Color(.6f,.65f,.72f));
            sky.SetFloat("_Exposure",night?.25f:1); sky.SetFloat("_AtmosphereThickness",.65f);
            RenderSettings.skybox=sky;RenderSettings.fog=false;
            var warnings=new System.Collections.Generic.List<string>();
            if(GraphicsSettings.currentRenderPipeline!=null)
            {
                if(!ConfigureURP(rig,night,cool)) warnings.Add("URP volume API unavailable; lighting/sky/camera applied without color grading");
            }
            else
            {
                var grade=AssetDatabase.LoadAssetAtPath<Material>(Folder+"/Grade.mat");
                if(!grade){grade=new Material(Shader.Find("Hidden/PromptToScene/SceneLook"));AssetDatabase.CreateAsset(grade,Folder+"/Grade.mat");}
                grade.SetFloat("_Exposure",night?.85f:1.04f);grade.SetFloat("_Saturation",cool?.8f:1.06f);
                grade.SetColor("_Tint",night?new Color(.84f,.90f,1):cool?new Color(.9f,.99f,1):new Color(1,.98f,.94f));
                rig.gradeMaterial=grade;
                foreach(var cam in rig.previousCameras.Concat(new[]{rig.presentationCamera}))
                {if(!cam)continue;var effect=cam.GetComponents<BuiltinLook>().FirstOrDefault(e=>e.colorGrade==rig.gradeMaterial);if(!effect)effect=cam.gameObject.AddComponent<BuiltinLook>();effect.colorGrade=grade;}
                EditorUtility.SetDirty(grade);
            }
            EditorUtility.SetDirty(sky);EditorUtility.SetDirty(rig);AssetDatabase.SaveAssets();DynamicGI.UpdateEnvironment();
            EditorSceneManager.MarkSceneDirty(DevelopmentActions.Scene);
            result.development.preset=c.preset;result.development.changed=1;result.development.warnings=warnings.ToArray();return result;
        }
        static void SetLight(SceneLook rig,string name,Vector3 rotation,Color color,float intensity)
        {
            var node=rig.transform.Find(name); if(!node){node=new GameObject(name).transform;node.SetParent(rig.transform,false);node.gameObject.AddComponent<Light>();}
            var light=node.GetComponent<Light>(); light.type=LightType.Directional;light.color=color;light.intensity=intensity;
            light.shadows=name=="Key"?LightShadows.Soft:LightShadows.None;light.shadowStrength=.7f;
            node.rotation=Quaternion.Euler(rotation);if(name=="Key")RenderSettings.sun=light;
        }
        static bool ConfigureURP(SceneLook rig,bool night,bool cool)
        {
            var volumeType=Type.GetType("UnityEngine.Rendering.Volume, Unity.RenderPipelines.Core.Runtime");
            var profileType=Type.GetType("UnityEngine.Rendering.VolumeProfile, Unity.RenderPipelines.Core.Runtime");
            var colorType=Type.GetType("UnityEngine.Rendering.Universal.ColorAdjustments, Unity.RenderPipelines.Universal.Runtime");
            if(volumeType==null||profileType==null||colorType==null)return false;
            var volume=rig.GetComponent(volumeType);if(!volume)volume=rig.gameObject.AddComponent(volumeType);
            volumeType.GetProperty("isGlobal")?.SetValue(volume,true); volumeType.GetField("priority")?.SetValue(volume,1000f);
            var profile=AssetDatabase.LoadAssetAtPath(Folder+"/Profile.asset",profileType) as ScriptableObject;
            if(!profile){profile=ScriptableObject.CreateInstance(profileType);AssetDatabase.CreateAsset(profile,Folder+"/Profile.asset");}
            var components=(System.Collections.IList)profileType.GetField("components").GetValue(profile);
            var component=components.Cast<object>().FirstOrDefault(o=>o.GetType()==colorType)??profileType.GetMethod("Add",new[]{typeof(Type),typeof(bool)}).Invoke(profile,new object[]{colorType,true});
            foreach(var pair in new[]{("postExposure",night?-.3f:0f),("contrast",night?5f:8f),("saturation",cool?-12f:5f)})
            {var parameter=colorType.GetField(pair.Item1).GetValue(component);parameter.GetType().GetProperty("overrideState").SetValue(parameter,true);parameter.GetType().GetProperty("value").SetValue(parameter,pair.Item2);}
            volumeType.GetField("sharedProfile").SetValue(volume,profile);
            foreach(var cam in rig.previousCameras.Concat(new[]{rig.presentationCamera}))
            {
                if(!cam)continue;
                var dataType=Type.GetType("UnityEngine.Rendering.Universal.UniversalAdditionalCameraData, Unity.RenderPipelines.Universal.Runtime");
                var data=cam.GetComponent(dataType);if(!data)data=cam.gameObject.AddComponent(dataType);dataType.GetProperty("renderPostProcessing").SetValue(data,true);
            }
            EditorUtility.SetDirty(profile); return true;
        }
        public static void Capture(Camera camera,string path)
        {
            var old=camera.targetTexture;var active=RenderTexture.active;var rt=new RenderTexture(960,640,24);Texture2D pixels=null;
            try{camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;pixels=new Texture2D(960,640,TextureFormat.RGB24,false);pixels.ReadPixels(new Rect(0,0,960,640),0,0);pixels.Apply();Directory.CreateDirectory(Path.GetDirectoryName(path));File.WriteAllBytes(path,pixels.EncodeToPNG());}
            finally{camera.targetTexture=old;RenderTexture.active=active;rt.Release();Object.DestroyImmediate(rt);if(pixels)Object.DestroyImmediate(pixels);}
        }
        public static void PreviewAsset(GameObject source,string path)
        {
            var preview=new PreviewRenderUtility();var clone=Object.Instantiate(source);
            try
            {
                // Preview scene owns the clone; no project scripts run in Play mode.
                foreach(var script in clone.GetComponentsInChildren<MonoBehaviour>()) script.enabled=false;
                preview.AddSingleGO(clone);var rs=clone.GetComponentsInChildren<Renderer>();if(rs.Length==0)throw new Exception("No renderable mesh");
                Bounds b=rs[0].bounds;foreach(var r in rs.Skip(1))b.Encapsulate(r.bounds);
                float radius=Mathf.Max(b.extents.magnitude,.02f);preview.camera.fieldOfView=40;
                float distance=radius/Mathf.Sin(preview.camera.fieldOfView*Mathf.Deg2Rad*.5f)*1.15f;
                preview.camera.transform.position=b.center+new Vector3(1.7f,1.1f,2.0f).normalized*distance;preview.camera.transform.LookAt(b.center);
                preview.camera.nearClipPlane=Mathf.Max(.001f,radius*.01f);preview.camera.farClipPlane=distance+radius*10;preview.lights[0].intensity=1.5f;preview.lights[0].transform.rotation=Quaternion.Euler(40,30,0);preview.lights[1].intensity=.5f;
                Capture(preview.camera,path);
            }
            finally{preview.Cleanup();if(clone)Object.DestroyImmediate(clone);}
        }
    }
}
