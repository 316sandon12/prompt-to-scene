using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PromptToScene.Editor
{
    public static class GameDelivery
    {
        [Serializable] class Request { public string request_id, output; public string[] scenes; public bool development_build; }
        [Serializable] class Receipt { public string engine="unity", version, platform, output, build_guid; public string[] scenes; public bool built; public int warnings; }
        public static DevelopmentResult Execute(DevelopmentCommand command)
        {
            var p=JsonUtility.FromJson<Request>(command.content_json);
            var target=Application.platform==RuntimePlatform.OSXEditor?BuildTarget.StandaloneOSX:Application.platform==RuntimePlatform.WindowsEditor?BuildTarget.StandaloneWindows64:BuildTarget.StandaloneLinux64;
            var scenes=p.scenes!=null&&p.scenes.Length>0?p.scenes:EditorBuildSettings.scenes.Where(s=>s.enabled).Select(s=>s.path).ToArray();
            if(scenes.Length==0&&!string.IsNullOrEmpty(DevelopmentActions.Scene.path)) scenes=new[]{DevelopmentActions.Scene.path};
            var r=new Receipt{version=Application.unityVersion,platform=target.ToString(),scenes=scenes};
            if(command.mode=="build") {
                if(EditorApplication.isCompiling||EditorUtility.scriptCompilationFailed) throw new Exception("Fix compilation errors before building the game");
                if(!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Standalone,target)) throw new Exception("Install this platform's build support in Unity Hub");
                if(scenes.Length==0||scenes.Any(s=>!s.StartsWith("Assets/")||s.Contains("..")||!s.EndsWith(".unity")||!AssetDatabase.LoadAssetAtPath<SceneAsset>(s))) throw new Exception("Choose saved project scenes");
                for(int i=0;i<UnityEngine.SceneManagement.SceneManager.sceneCount;i++) if(UnityEngine.SceneManagement.SceneManager.GetSceneAt(i).isDirty) throw new Exception("Save the edited scenes before creating a player build");
                if(!System.Text.RegularExpressions.Regex.IsMatch(p.request_id??"","^[a-f0-9]{32}$")) throw new Exception("Invalid delivery task");
                string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.local/pts-deliveries",p.request_id));
                if(Path.GetFullPath(p.output)!=root||!File.Exists(Path.Combine(root,"owner.json"))) throw new Exception("Choose the task-owned delivery directory");
                Directory.CreateDirectory(root);
                r.output=Path.Combine(root,target==BuildTarget.StandaloneOSX?"Player.app":target==BuildTarget.StandaloneWindows64?"Player.exe":"Player");
                var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=scenes,locationPathName=r.output,target=target,options=p.development_build?BuildOptions.Development:BuildOptions.None});
                if(report.summary.result!=BuildResult.Succeeded) throw new Exception("Player build failed: "+report.summary.result+" ("+report.summary.totalErrors+" errors)");
                r.built=true;r.build_guid=report.summary.guid.ToString();r.warnings=(int)report.summary.totalWarnings;
            } else if(command.mode!="inspect") throw new Exception("Unknown delivery action");
            return new DevelopmentResult{command="delivery",passed=true,message=r.built?"Native player built":"Actual engine and scenes inspected",plan_json=JsonUtility.ToJson(r)};
        }
    }
}
