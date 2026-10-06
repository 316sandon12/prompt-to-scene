using System;
using System.IO;
using System.Linq;
using System.Diagnostics;
using UnityEngine;
using UnityEditor;
using Debug = UnityEngine.Debug;

namespace PromptToScene.Editor
{
    [Serializable] class PanelLauncher { public string command, project, home; public string[] args; }
    [Serializable] class PanelPreview {public string path,before,after,request_id;}
    [Serializable] class PanelResult { public string status,error,message,stage,request_id,plan_id,kind; public DevelopmentResult development; public OrganizationPlan plan; public PanelPreview[] previews,results; public AdaptRow[] entries; }
    [Serializable] class PanelPrefs { public string organization,adaptation; }
    [Serializable] class ProfilePreparation { public int triangle_budget=50000,texture_size=1024; public string collision="convex"; }
    [Serializable] class ProfileOrganization { public string destination="Assets/GameAssets"; }
    [Serializable] class ProfileIntake { public string folder="AssetInbox"; public bool enabled; public int settle_seconds=5; }
    [Serializable] class PanelProfile { public ProfilePreparation preparation=new ProfilePreparation(); public ProfileOrganization organization=new ProfileOrganization(); public ProfileIntake intake=new ProfileIntake(); }

    public class WorkshopWindow : EditorWindow
    {
        string pending, task, message="选择 Project 中的资源，即可检查、整理或生成外观预览。", reference="", raw="", purpose="";
        Vector2 scroll;
        PanelPrefs prefs=new PanelPrefs();PanelProfile profile=new PanelProfile();bool details;
        string plannedMoves="";AdaptRow[] materialRows=Array.Empty<AdaptRow>();System.Collections.Generic.HashSet<string> selectedRows=new System.Collections.Generic.HashSet<string>();
        Texture2D beforeImage,afterImage;double nextPoll;
        static double nextService;
        [MenuItem("Tools/Prompt-to-Scene/Workshop")]
        public static void Open() => GetWindow<WorkshopWindow>("Prompt-to-Scene");
        [MenuItem("Assets/Prompt-to-Scene/Organize selection")]
        static void OrganizeSelection(){Open();GetWindow<WorkshopWindow>().Organize();}
        [MenuItem("Assets/Prompt-to-Scene/Inspect selection")]
        static void InspectSelection(){Open();GetWindow<WorkshopWindow>().Send("inspect_selected",SelectedValues());}
        public static string Quote(string value) => "\""+(value??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r","\\r").Replace("\n","\\n")+"\"";
        static string[] Paths()=>Selection.objects.Select(AssetDatabase.GetAssetPath).Where(p=>p.StartsWith("Assets/")).Distinct().ToArray();
        static string SelectedValues()=>"{\"paths\":["+string.Join(",",Paths().Select(Quote))+"]}";
        static string FirstText(params string[] values)=>values.FirstOrDefault(v=>!string.IsNullOrEmpty(v));
        static string Argument(string s)=>"\""+System.Text.RegularExpressions.Regex.Replace(s,@"(\\*)\""", "$1$1\\\"").TrimEnd('\\')+new string('\\',s.Reverse().TakeWhile(c=>c=='\\').Count()*2)+"\"";
        public static void EnsureService()
        {
            if(EditorApplication.timeSinceStartup<nextService||Application.isBatchMode)return;
            nextService=EditorApplication.timeSinceStartup+15;
            string stamp=Path.Combine(AssetBridge.StateRoot,"panel-service","heartbeat.json");
            if(File.Exists(stamp)&&(DateTime.UtcNow-File.GetLastWriteTimeUtc(stamp)).TotalSeconds<30)return;
            string file=Path.Combine(AssetBridge.StateRoot,"launcher.json");if(!File.Exists(file))return;
            try
            {
                var config=JsonUtility.FromJson<PanelLauncher>(File.ReadAllText(file));
                var args=config.args.Concat(new[]{"--editor-service",config.project});
                var start=new ProcessStartInfo(config.command,string.Join(" ",args.Select(Argument))){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=AssetBridge.ProjectRoot};
                start.EnvironmentVariables["PTS_HOME"]=config.home;start.EnvironmentVariables["PYINSTALLER_RESET_ENVIRONMENT"]="1";
                Process.Start(start);
            }
            catch(Exception error){Debug.LogWarning("Prompt-to-Scene: "+error.Message);}
        }
        void OnEnable()
        {
            pending=null;task=null;nextPoll=0;
            EditorApplication.update+=Poll;
            string path=Path.Combine(AssetBridge.StateRoot,"panel-prefs.json");if(File.Exists(path))prefs=JsonUtility.FromJson<PanelPrefs>(File.ReadAllText(path));
            path=Path.Combine(AssetBridge.ProjectRoot,"prompt-to-scene.json");if(File.Exists(path))profile=JsonUtility.FromJson<PanelProfile>(File.ReadAllText(path));
            string jobs=Path.Combine(AssetBridge.StateRoot,"jobs");
            if(Directory.Exists(jobs))foreach(var file in Directory.GetFiles(jobs,"state.json",SearchOption.AllDirectories).OrderByDescending(File.GetLastWriteTimeUtc).Take(40))
            {
                var saved=JsonUtility.FromJson<PanelResult>(File.ReadAllText(file));
                if(saved.kind=="adaptation"||saved.kind=="semantic"){task=saved.request_id;purpose=saved.kind;break;}
            }
        }
        void OnDisable(){EditorApplication.update-=Poll;if(beforeImage)DestroyImmediate(beforeImage);if(afterImage)DestroyImmediate(afterImage);}
        void OnSelectionChange()=>Repaint();
        void Send(string action,string values="{}")
        {
            if(!File.Exists(Path.Combine(AssetBridge.StateRoot,"launcher.json"))){message="请先在 Prompt-to-Scene 应用中连接此项目。";return;}
            if(pending!=null||task!=null){message="当前任务完成后再继续；可先取消。";return;}
            EnsureService();pending=Guid.NewGuid().ToString("N");purpose=action;
            string folder=Path.Combine(AssetBridge.StateRoot,"panel-requests");Directory.CreateDirectory(folder);
            string path=Path.Combine(folder,pending+".json");File.WriteAllText(path+".tmp","{\"action\":"+Quote(action)+",\"values\":"+values+"}");File.Move(path+".tmp",path);
            message="处理中…";
        }
        void Poll()
        {
            if(EditorApplication.timeSinceStartup<nextPoll)return;nextPoll=EditorApplication.timeSinceStartup+.3;
            if(pending==null&&task==null)return;
            string path=pending!=null?Path.Combine(AssetBridge.StateRoot,"panel-results",pending+".json"):Path.Combine(AssetBridge.StateRoot,"jobs",task,"state.json");
            if(!File.Exists(path)&&task!=null)path=Path.Combine(AssetBridge.StateRoot,"action-receipts",task+".json");
            if(!File.Exists(path))return;
            try
            {
                raw=File.ReadAllText(path);var value=JsonUtility.FromJson<PanelResult>(raw);
                message=FirstText(value.error,value.message,value.stage,value.status)??"已完成";
                string plan=FirstText(value.plan_id,value.development?.plan_id);
                if(!string.IsNullOrEmpty(plan)){if(purpose=="organize_selected"||purpose=="organize")prefs.organization=plan;else if(purpose=="adaptation")prefs.adaptation=plan;AssetBridge.WriteJson(Path.Combine(AssetBridge.StateRoot,"panel-prefs.json"),prefs);}
                if(pending!=null){pending=null;task=value.request_id;}
                if(value.status=="completed")
                {
                    if(value.plan!=null&&value.plan.entries!=null)plannedMoves=string.Join("\n",value.plan.entries.Where(r=>r.action=="move").Take(40).Select(r=>r.source+" → "+r.destination));
                    if(value.kind=="adaptation"&&value.entries!=null){materialRows=value.entries;selectedRows=new System.Collections.Generic.HashSet<string>(materialRows.Select(r=>r.id));}
                    var images=value.previews?.FirstOrDefault();
                    string left=images?.before??value.results?.FirstOrDefault()?.request_id;
                    if(!string.IsNullOrEmpty(left)){LoadImage(ref beforeImage,left);if(images!=null)LoadImage(ref afterImage,images.after);}
                }
                if(value.status=="completed"||value.status=="imported"||value.status=="error"||value.status=="cancelled"||string.IsNullOrEmpty(value.request_id))task=null;
                Repaint();
            }
            catch(IOException){}
        }
        void LoadImage(ref Texture2D image,string revision)
        {
            if(!System.Text.RegularExpressions.Regex.IsMatch(revision??"","^[a-f0-9]{32}$"))return;
            string file=Path.Combine(AssetBridge.StateRoot,"previews",revision+".png");if(!File.Exists(file))return;
            if(image)DestroyImmediate(image);image=new Texture2D(2,2);image.LoadImage(File.ReadAllBytes(file));
        }
        void Organize()=>Send("organize_selected",SelectedValues());
        void OnGUI()
        {
            scroll=EditorGUILayout.BeginScrollView(scroll);
            GUILayout.Label("项目资产工作台",EditorStyles.boldLabel);
            EditorGUILayout.HelpBox("已选择 "+Paths().Length+" 项 · 当前项目 "+new DirectoryInfo(AssetBridge.ProjectRoot).Name,MessageType.Info);
            EditorGUILayout.HelpBox(message,MessageType.None);
            if(beforeImage){GUILayout.Label(afterImage?"原始 / 适配预览（第一项）":"素材实拍",EditorStyles.boldLabel);EditorGUILayout.BeginHorizontal();DrawPreview(beforeImage);if(afterImage)DrawPreview(afterImage);EditorGUILayout.EndHorizontal();}
            using(new EditorGUI.DisabledScope(pending!=null||task!=null))
            {
                EditorGUILayout.BeginHorizontal();if(GUILayout.Button("检查选中"))Send("inspect_selected",SelectedValues());if(GUILayout.Button("整理选中"))Organize();EditorGUILayout.EndHorizontal();
                if(!string.IsNullOrEmpty(plannedMoves))EditorGUILayout.HelpBox(plannedMoves,MessageType.None);
                using(new EditorGUI.DisabledScope(string.IsNullOrEmpty(prefs.organization)))
                {EditorGUILayout.BeginHorizontal();if(GUILayout.Button("应用整理方案"))Send("organize","{\"mode\":\"apply\",\"plan_id\":"+Quote(prefs.organization)+"}");if(GUILayout.Button("撤销整理"))Send("organize","{\"mode\":\"undo\",\"plan_id\":"+Quote(prefs.organization)+"}");EditorGUILayout.EndHorizontal();}
                GUILayout.Space(12);GUILayout.Label("内容识别与外观",EditorStyles.boldLabel);
                if(GUILayout.Button("捕获选中素材 · 交给 AI 识别"))Send("semantic",SelectedValues());
                if(GUILayout.Button("以当前第一项为外观参考"))reference=Paths().FirstOrDefault()??"";
                EditorGUILayout.LabelField("参考",reference);
                if(GUILayout.Button("预览选中预制体的材质适配"))Send("adaptation","{\"paths\":["+string.Join(",",Paths().Where(p=>p!=reference).Select(Quote))+"],\"reference\":"+Quote(reference)+"}");
                foreach(var row in materialRows){bool chosen=EditorGUILayout.ToggleLeft(row.id+" · "+Path.GetFileName(row.path)+" · 槽 "+row.slot+" · "+string.Join(", ",row.fields),selectedRows.Contains(row.id));if(chosen)selectedRows.Add(row.id);else selectedRows.Remove(row.id);}
                using(new EditorGUI.DisabledScope(string.IsNullOrEmpty(prefs.adaptation)))
                {EditorGUILayout.BeginHorizontal();if(GUILayout.Button("应用勾选预览")){if(selectedRows.Count==0)message="先生成预览并勾选材质槽。";else Send("adaptation","{\"mode\":\"apply\",\"plan_id\":"+Quote(prefs.adaptation)+",\"selected\":["+string.Join(",",selectedRows.Select(Quote))+"]}");}if(GUILayout.Button("撤销外观"))Send("adaptation","{\"mode\":\"undo\",\"plan_id\":"+Quote(prefs.adaptation)+"}");EditorGUILayout.EndHorizontal();}
                GUILayout.Space(12);GUILayout.Label("项目规范与自动入库",EditorStyles.boldLabel);
                profile.organization.destination=EditorGUILayout.TextField("资源目录",profile.organization.destination);
                profile.preparation.triangle_budget=EditorGUILayout.IntField("三角面预算",profile.preparation.triangle_budget);
                profile.preparation.texture_size=EditorGUILayout.IntPopup("贴图尺寸",profile.preparation.texture_size,new[]{"256","512","1024","2048"},new[]{256,512,1024,2048});
                profile.intake.folder=EditorGUILayout.TextField("源文件收件箱",profile.intake.folder);
                profile.intake.enabled=EditorGUILayout.Toggle("自动入库",profile.intake.enabled);
                if(GUILayout.Button("保存为项目默认规范"))Send("profile","{\"mode\":\"save\",\"settings\":"+JsonUtility.ToJson(profile)+"}");
                EditorGUILayout.BeginHorizontal();if(GUILayout.Button("打开收件箱")){string folder=Path.GetFullPath(Path.Combine(AssetBridge.ProjectRoot,profile.intake.folder));if(folder.StartsWith(AssetBridge.ProjectRoot+Path.DirectorySeparatorChar)){Directory.CreateDirectory(folder);EditorUtility.RevealInFinder(folder);}}if(GUILayout.Button("立即入库"))Send("intake","{\"mode\":\"scan\"}");EditorGUILayout.EndHorizontal();
            }
            if(task!=null&&GUILayout.Button("取消当前任务")){string old=task;task=null;Send("cancel","{\"request_id\":"+Quote(old)+"}");}
            details=EditorGUILayout.Foldout(details,"方案与结果详情");if(details)EditorGUILayout.TextArea(raw,GUILayout.MinHeight(200));
            EditorGUILayout.EndScrollView();
        }
        void DrawPreview(Texture2D image)
        {
            var rect=GUILayoutUtility.GetRect(position.width/2-12,150);
            GUI.DrawTexture(rect,image,ScaleMode.ScaleToFit);
        }
    }
}
