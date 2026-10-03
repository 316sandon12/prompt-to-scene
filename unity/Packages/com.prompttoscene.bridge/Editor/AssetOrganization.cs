using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace PromptToScene.Editor
{
    [Serializable] public class OrganizationEntry
    {
        public string path, name, kind, extension, id, fingerprint, reason, texture_role;
        public string source, destination, action, current;
    }
    [Serializable] public class OrganizationScan
    {
        public int schema_version = 1, total;
        public string engine = "unity", scan_id, scope;
        public bool truncated;
        public string[] occupied;
        public OrganizationEntry[] entries;
    }
    [Serializable] public class OrganizationPlan
    {
        public int schema_version;
        public string engine, plan_id, scan_id, scope;
        public OrganizationEntry[] entries;
    }
    [Serializable] public class OrganizationEvent { public string source, destination; }
    [Serializable] public class OrganizationJournal
    {
        public string engine = "unity", plan_id, status, error;
        public OrganizationEntry[] entries;
        public List<OrganizationEvent> events = new List<OrganizationEvent>();
    }

    [InitializeOnLoad]
    public static class AssetOrganization
    {
        static readonly HashSet<string> Reserved = new HashSet<string>(new[] {
            "resources","streamingassets","editor","editor default resources","gizmos","plugins",
            "standard assets","prompttoscene","__externalactors__","__externalobjects__",
            "developers","collections","addressableassetsdata"
        }, StringComparer.OrdinalIgnoreCase);
        static readonly HashSet<string> Movable = new HashSet<string>(new[] {
            "model","prefab","material","texture","sprite","audio","animation","controller","vfx","font"
        });
        static string Root => AssetBridge.StateRoot;
        static string Project => Path.GetDirectoryName(Application.dataPath);
        static OrganizationJournal pending;
        static SceneAction pendingAction;
        static bool undo, ticking;
        static int index, changed;
        public static bool Busy => pending != null;
        static AssetOrganization() { EditorApplication.update += Tick; }

        static string Record(string folder, string id)
        {
            if(id == null || !Regex.IsMatch(id,"^[a-f0-9]{32}$")) throw new Exception("Invalid organization ID");
            var path = Path.Combine(Root,"organization",folder,id+".json");
            for(var p=Path.GetDirectoryName(path);p!=Project;p=Path.GetDirectoryName(p))
                if(Directory.Exists(p) && (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)
                    throw new Exception("Organization state traverses a symlink");
            if(File.Exists(path) && ((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0 || new FileInfo(path).Length>32*1024*1024))
                throw new Exception("Invalid organization record");
            return path;
        }
        static void PathGuard(string path)
        {
            if(path == null || !(path=="Assets" || path.StartsWith("Assets/",StringComparison.Ordinal)) || path.Length>240 ||
                path.Contains("\\") || path.Split('/').Any(p=>string.IsNullOrEmpty(p)||p=="."||p==".."||p.EndsWith(".")||p.EndsWith(" ")) ||
                path.Any(c=>c<32 || ":*?\"<>|".Contains(c))) throw new Exception("Invalid Assets path");
            var full=Path.Combine(Project,path);
            for(var p=full;p!=Project;p=Path.GetDirectoryName(p))
                if((File.Exists(p)||Directory.Exists(p)) && (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)
                    throw new Exception("Asset path traverses a symlink: "+path);
        }
        static bool Protected(string path) => path.Split('/').Any(p=>Reserved.Contains(p)||p.StartsWith("."));
        static string Kind(string path)
        {
            string ext=Path.GetExtension(path).ToLowerInvariant();
            if(new[]{".fbx",".obj",".blend",".dae",".gltf",".glb"}.Contains(ext))return "model";
            if(ext==".prefab")return "prefab";
            if(ext==".unity")return "scene";
            if(new[]{".cs",".dll",".asmdef",".asmref"}.Contains(ext))return "script";
            if(new[]{".shader",".shadergraph",".shadersubgraph",".compute",".hlsl",".cginc"}.Contains(ext))return "shader";
            if(ext==".vfx")return "vfx";
            var type=AssetDatabase.GetMainAssetTypeAtPath(path);
            if(type==null)return "other";
            if(typeof(Material).IsAssignableFrom(type))return "material";
            if(typeof(Texture).IsAssignableFrom(type))return "texture";
            if(typeof(Sprite).IsAssignableFrom(type))return "sprite";
            if(typeof(AudioClip).IsAssignableFrom(type))return "audio";
            if(typeof(AnimationClip).IsAssignableFrom(type))return "animation";
            if(typeof(RuntimeAnimatorController).IsAssignableFrom(type))return "controller";
            if(typeof(Mesh).IsAssignableFrom(type))return "model";
            if(typeof(Font).IsAssignableFrom(type))return "font";
            if(typeof(ScriptableObject).IsAssignableFrom(type))return "data";
            return "other";
        }
        static bool Addressable(string guid)
        {
            var type=AppDomain.CurrentDomain.GetAssemblies().Select(a=>a.GetType("UnityEditor.AddressableAssets.AddressableAssetSettingsDefaultObject")).FirstOrDefault(t=>t!=null);
            if(type==null)return false;
            var settings=type.GetProperty("Settings",BindingFlags.Public|BindingFlags.Static)?.GetValue(null);
            if(settings==null)return false;
            var method=settings.GetType().GetMethods().FirstOrDefault(m=>m.Name=="FindAssetEntry" && m.GetParameters().Length==2);
            if(method==null)throw new Exception("Addressables metadata is unavailable; keep this asset in place");
            return method.Invoke(settings,new object[]{guid,true})!=null;
        }
        static string Reason(string path,string kind,string guid)
        {
            PathGuard(path);
            if(Protected(path))return "Protected engine/plugin folder";
            if(!Movable.Contains(kind))return "Classified for review; this type stays in its original location";
            if((File.GetAttributes(Path.Combine(Project,path))&FileAttributes.ReadOnly)!=0)return "Read-only asset";
            var importer=AssetImporter.GetAtPath(path);
            if(importer && !string.IsNullOrEmpty(importer.assetBundleName))return "AssetBundle address stays stable";
            if(Addressable(guid))return "Addressable address stays stable";
            if(new[]{".obj",".gltf",".blend",".dae"}.Contains(Path.GetExtension(path).ToLowerInvariant()) ||
                Directory.Exists(Path.Combine(Project,Path.ChangeExtension(path,".fbm"))))
                return "External source dependencies require their original relative paths";
            return "";
        }
        static void Folder(string path)
        {
            if(AssetDatabase.IsValidFolder(path))return;
            var parent=path.Substring(0,path.LastIndexOf('/'));Folder(parent);
            if(string.IsNullOrEmpty(AssetDatabase.CreateFolder(parent,path.Substring(path.LastIndexOf('/')+1))))
                throw new Exception("Cannot create destination folder: "+path);
        }
        static DevelopmentResult Result(string mode,string id,int count=0,string status=null) => new DevelopmentResult {
            command="organize",mode=mode,plan_id=id,changed=count,organization_status=status,
            message=mode=="scan"?"Project inventory saved; build a naming plan before applying.":"Native GUID references retained; inspect the persistent organization record."
        };
        public static SceneResult Execute(SceneAction action,DevelopmentCommand c)
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode)throw new Exception("Leave Play mode before organizing assets");
            if(Busy)throw new Exception("An organization is already running");
            var response=new SceneResult{request_id=action.request_id};
            if(c.mode=="scan")
            {
                PathGuard(c.scope_path);
                if(!AssetDatabase.IsValidFolder(c.scope_path))throw new Exception("Choose an existing project folder");
                var all=AssetDatabase.GetAllAssetPaths().Where(p=>p.StartsWith("Assets/")).OrderBy(p=>p,StringComparer.Ordinal).ToArray();
                var paths=all.Where(p=>p.StartsWith(c.scope_path+"/",StringComparison.Ordinal) && !AssetDatabase.IsValidFolder(p)).ToArray();
                var rows=new List<OrganizationEntry>();
                foreach(var path in paths.Take(20000))
                {
                    var row=new OrganizationEntry{path=path,name=Path.GetFileNameWithoutExtension(path),extension=Path.GetExtension(path),id=AssetDatabase.AssetPathToGUID(path),kind="other",reason=""};
                    try {
                        PathGuard(path);row.kind=Kind(path);row.reason=Reason(path,row.kind,row.id);
                        row.fingerprint=AssetDatabase.GetAssetDependencyHash(path).ToString();
                        var tex=AssetImporter.GetAtPath(path) as TextureImporter;
                        if(tex && tex.textureType==TextureImporterType.NormalMap)row.texture_role="Normal";
                        if(tex && tex.textureType==TextureImporterType.Sprite)row.kind="sprite";
                    } catch(Exception error){row.reason=error.Message;}
                    rows.Add(row);
                }
                var scan=new OrganizationScan{scan_id=action.request_id,scope=c.scope_path,total=paths.Length,truncated=paths.Length>20000,occupied=all,entries=rows.ToArray()};
                AssetBridge.WriteJson(Record("scans",action.request_id),scan);
                response.development=Result("scan",null,rows.Count);response.development.scan_id=action.request_id;response.development.truncated=scan.truncated;
                return response;
            }
            if(c.mode!="apply" && c.mode!="undo")throw new Exception("Unknown organization operation");
            var planPath=Record("plans",c.plan_id);
            var bytes=File.ReadAllBytes(planPath);
            using(var hash=SHA256.Create())
                if(BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-","").ToLowerInvariant()!=c.plan_sha256)
                    throw new Exception("Naming plan changed; preview it again");
            var plan=JsonUtility.FromJson<OrganizationPlan>(System.Text.Encoding.UTF8.GetString(bytes));
            if(plan.schema_version!=1||plan.engine!="unity"||plan.plan_id!=c.plan_id||plan.entries==null||plan.entries.Length>20000)
                throw new Exception("Invalid organization plan");
            var journalPath=Record("journals",c.plan_id);
            var journal=File.Exists(journalPath)?JsonUtility.FromJson<OrganizationJournal>(File.ReadAllText(journalPath)):null;
            if(journal!=null && ((c.mode=="apply"&&journal.status=="applied")||(c.mode=="undo"&&journal.status=="undone")))
            {response.development=Result(c.mode,c.plan_id,0,journal.status);return response;}
            if(c.mode=="apply"&&journal!=null)throw new Exception("This plan already ran; undo or create a fresh plan");
            if(c.mode=="undo"&&journal==null)throw new Exception("Apply this plan before undoing it");
            var entries=c.mode=="apply"?plan.entries.Where(e=>e.action=="move").ToArray():journal.entries;
            var destinations=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach(var row in entries)
            {
                PathGuard(row.source);PathGuard(row.destination);
                if(Protected(row.source)||Protected(row.destination)||row.source==row.destination ||
                    Path.GetExtension(row.source)!=Path.GetExtension(row.destination)||!destinations.Add(row.destination))
                    throw new Exception("Invalid or duplicate organization path");
                var current=AssetDatabase.GUIDToAssetPath(row.id);
                if(c.mode=="apply")
                {
                    if(current!=row.source || AssetDatabase.GetAssetDependencyHash(current).ToString()!=row.fingerprint)
                        throw new Exception("Asset changed since preview: "+row.source);
                    var reason=Reason(current,Kind(current),row.id);if(reason!="")throw new Exception(reason+": "+current);
                    if(Kind(current)!=row.kind)throw new Exception("Asset type changed since preview");
                    if(EditorUtility.IsDirty(AssetDatabase.LoadMainAssetAtPath(current)))throw new Exception("Save this asset before organizing: "+current);
                }
                else if(current!=row.source && current!=row.destination)throw new Exception("Asset moved outside this plan: "+row.source);
                var to=c.mode=="apply"?row.destination:row.source;
                if(current!=to && (File.Exists(Path.Combine(Project,to))||Directory.Exists(Path.Combine(Project,to))||!string.IsNullOrEmpty(AssetDatabase.AssetPathToGUID(to,AssetPathToGUIDOptions.OnlyExistingAssets))))
                    throw new Exception("Destination is occupied: "+to);
                var parent=Path.GetDirectoryName(to).Replace('\\','/');
                for(var p=parent;p!="Assets";p=Path.GetDirectoryName(p).Replace('\\','/'))
                    if(File.Exists(Path.Combine(Project,p)))throw new Exception("Destination folder is occupied by a file: "+p);
            }
            if(journal==null)journal=new OrganizationJournal{plan_id=c.plan_id,entries=entries};
            if(journal.events==null)journal.events=new List<OrganizationEvent>();
            foreach(var row in entries)
            {
                var actual=AssetDatabase.GUIDToAssetPath(row.id);
                if(!string.IsNullOrEmpty(row.current)&&actual!=row.current)
                    journal.events.Add(new OrganizationEvent{source=row.current,destination=actual});
                row.current=actual;
            }
            undo=c.mode=="undo";journal.status=undo?"undoing":"applying";journal.error=null;
            AssetBridge.WriteJson(journalPath,journal);
            pending=journal;pendingAction=action;index=changed=0;
            response.status="queued";response.development=Result(c.mode,c.plan_id,0,journal.status);
            return response;
        }
        static void Move(OrganizationEntry row,string target)
        {
            var current=AssetDatabase.GUIDToAssetPath(row.id);
            if(current==target)return;
            if(current!=row.source && current!=row.destination)throw new Exception("Asset identity moved outside the plan");
            PathGuard(current);PathGuard(target);
            if(File.Exists(Path.Combine(Project,target))||Directory.Exists(Path.Combine(Project,target)))throw new Exception("Destination became occupied: "+target);
            Folder(Path.GetDirectoryName(target).Replace('\\','/'));
            var error=AssetDatabase.MoveAsset(current,target);
            if(!string.IsNullOrEmpty(error))throw new Exception(error);
            if(AssetDatabase.GUIDToAssetPath(row.id)!=target)throw new Exception("Native move did not retain the expected GUID");
            row.current=target;pending.events.Add(new OrganizationEvent{source=current,destination=target});
            AssetBridge.WriteJson(Record("journals",pending.plan_id),pending);
        }
        static void Finish(string status,string error=null)
        {
            pending.status=status;pending.error=error;
            AssetBridge.WriteJson(Record("journals",pending.plan_id),pending);
            var result=new SceneResult{request_id=pendingAction.request_id,error=error,status=error==null?"completed":status=="cancelled"?"cancelled":"error",development=Result(undo?"undo":"apply",pending.plan_id,changed,status)};
            AssetBridge.WriteJson(Path.Combine(Root,"action-receipts",pendingAction.request_id+".json"),result);
            pending=null;pendingAction=null;
        }
        static void Tick()
        {
            if(!Busy || ticking || EditorApplication.isCompiling || EditorApplication.isUpdating)return;
            ticking=true;
            try
            {
                if(EditorApplication.isPlayingOrWillChangePlaymode)throw new Exception("Organization interrupted by Play mode");
                if(File.Exists(Path.Combine(Root,"cancel",pendingAction.request_id)))throw new OperationCanceledException("Organization cancelled");
                for(int n=0;n<4 && index<pending.entries.Length;n++,index++)
                {
                    var row=pending.entries[undo?pending.entries.Length-1-index:index];
                    var target=undo?row.source:row.destination;
                    if(AssetDatabase.GUIDToAssetPath(row.id)!=target){Move(row,target);changed++;}
                }
                if(index==pending.entries.Length)Finish(undo?"undone":"applied");
            }
            catch(Exception error)
            {
                string status="recovery_required",detail=error.Message;
                if(!undo)
                {
                    try {foreach(var row in pending.entries.Reverse())Move(row,row.source);changed=0;status=error is OperationCanceledException?"cancelled":"rolled_back";}
                    catch(Exception rollback){detail+="; rollback needs attention: "+rollback.Message;}
                }
                Finish(status,detail);
            }
            finally {ticking=false;}
        }
    }
}
