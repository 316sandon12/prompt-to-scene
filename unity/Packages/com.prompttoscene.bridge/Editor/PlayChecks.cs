using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
using Object = UnityEngine.Object;

namespace PromptToScene.Editor
{
    [InitializeOnLoad]
    public static class PlayChecks
    {
        const string Key="PromptToScene.PlayCheck";
        [Serializable] sealed class Pending {public SceneAction action;public DevelopmentCommand command;public SceneResult result;public long started;public bool finished;}
        static Pending pending;
        static FrameSampler sampler;
        static double playStart;
        static readonly List<string> errors=new List<string>();
        static readonly List<PlayAssertion> checks=new List<PlayAssertion>();
        static readonly List<Tuple<Interaction,Quaternion>> opened=new List<Tuple<Interaction,Quaternion>>();
        static Camera captureCamera;
        static bool exercised;

        static PlayChecks()
        {
            EditorApplication.playModeStateChanged+=Changed;EditorApplication.update+=Tick;
            Application.logMessageReceived+=Log;
            string saved=SessionState.GetString(Key,""); if(saved!="")pending=JsonUtility.FromJson<Pending>(saved);
        }
        static void Log(string message,string trace,LogType type)
        {if(pending!=null && EditorApplication.isPlaying && (type==LogType.Error||type==LogType.Exception||type==LogType.Assert))errors.Add(message);}
        public static SceneResult Start(SceneAction a,DevelopmentCommand c)
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode || pending!=null)throw new Exception("Finish the current Play session/check first");
            if(c.duration<1||c.duration>20||(c.asset_ids??new string[0]).Length>16)throw new Exception("Invalid play check");
            foreach(var id in c.asset_ids??new string[0])if(DevelopmentActions.Assets(id).Length==0)throw new Exception("Interactive asset not loaded: "+id);
            pending=new Pending{action=a,command=c,started=DateTimeOffset.UtcNow.ToUnixTimeSeconds()};
            SessionState.SetString(Key,JsonUtility.ToJson(pending));
            EditorApplication.delayCall+=()=>EditorApplication.EnterPlaymode();
            return new SceneResult{request_id=a.request_id,status="queued",development=new DevelopmentResult{command="playcheck",message="Entering Play mode; poll this request. The editor will return to Edit mode."}};
        }
        static void Changed(PlayModeStateChange state)
        {
            if(pending==null)return;
            if(state==PlayModeStateChange.EnteredPlayMode)
            {
                playStart=EditorApplication.timeSinceStartup;exercised=false;errors.Clear();checks.Clear();opened.Clear();
                sampler=new GameObject("PTS frame sampler").AddComponent<FrameSampler>();
            }
            if(state==PlayModeStateChange.EnteredEditMode)
            {
                var result=pending.finished?pending.result:new SceneResult{request_id=pending.action.request_id,status="error",error="Play ended before the check completed"};
                AssetBridge.WriteJson(Path.Combine(AssetBridge.StateRoot,"action-receipts",pending.action.request_id+".json"),result);
                SessionState.EraseString(Key);pending=null;
            }
        }
        static void Assert(string id,string name,bool passed,string detail="")=>checks.Add(new PlayAssertion{asset_id=id,check=name,passed=passed,detail=detail});
        static void Exercise()
        {
            var all=Object.FindObjectsOfType<AssetIdentity>().Where(a=>!a.nestedPart).ToArray();
            var candidates=all.Where(a=>(pending.command.asset_ids??new string[0]).Contains(a.assetId)).ToArray();
            var rs=candidates.SelectMany(a=>a.GetComponentsInChildren<Renderer>()).ToArray();
            if(pending.command.capture && rs.Length>0)
            {
                Bounds bounds=rs[0].bounds;foreach(var r in rs.Skip(1))bounds.Encapsulate(r.bounds);
                captureCamera=new GameObject("PTS play check camera").AddComponent<Camera>();captureCamera.enabled=false;
                captureCamera.transform.position=bounds.center+new Vector3(1.7f,1,2)*Mathf.Max(bounds.extents.magnitude,.5f);captureCamera.transform.LookAt(bounds.center);
                captureCamera.nearClipPlane=.05f;captureCamera.farClipPlane=1000;
                ScenePresentation.Capture(captureCamera,Path.Combine(AssetBridge.StateRoot,"previews",pending.action.request_id+"_before.png"));
            }
            foreach(var a in candidates)
            {
                var item=a.GetComponent<Interaction>();Assert(a.assetId,"runtime_component",item!=null);if(!item)continue;
                Assert(a.assetId,"range_rejection",!item.TryInteract(item.transform.position+Vector3.one*item.interactionRange*2));
                int count=item.InteractionCount;var initial=item.movingPivot?item.movingPivot.localRotation:Quaternion.identity;
                var moving=item.movingPivot?item.movingPivot.GetComponentInChildren<Renderer>():null;
                var center=moving?moving.bounds.center:Vector3.zero;
                bool accepted=item.TryInteract(item.transform.position);
                Assert(a.assetId,"interaction_event",accepted && item.InteractionCount==count+1);
                if(item.template=="pickup")Assert(a.assetId,"pickup_hidden",item.Collected&&!item.gameObject.activeSelf);
                else {Assert(a.assetId,"opens_geometry",item.IsOpen&&item.movingPivot&&Quaternion.Angle(initial,item.movingPivot.localRotation)>1&&moving&&Vector3.Distance(center,moving.bounds.center)>.001f);opened.Add(Tuple.Create(item,initial));}
            }
            if(!string.IsNullOrEmpty(pending.command.level_id))
            {
                var level=Object.FindObjectsOfType<LevelMarker>().FirstOrDefault(l=>l.levelId==pending.command.level_id);
                Assert(pending.command.level_id,"level_loaded",level!=null);
                if(level){var blockers=DevelopmentActions.Clearance(level);Assert(level.levelId,"walk_clearance",blockers.Length==0,string.Join(", ",blockers));}
            }
            if(captureCamera)ScenePresentation.Capture(captureCamera,Path.Combine(AssetBridge.StateRoot,"previews",pending.action.request_id+".png"));
            sampler.frameMilliseconds.Clear();
        }
        static void Tick()
        {
            if(pending==null||pending.finished)return;
            if(File.Exists(Path.Combine(AssetBridge.StateRoot,"cancel",pending.action.request_id))) {Finish("cancelled","Play check cancelled");return;}
            if(DateTimeOffset.UtcNow.ToUnixTimeSeconds()-pending.started>90){Finish("error","Play check timed out");return;}
            if(!EditorApplication.isPlaying||!sampler)return;
            try
            {
                if(!exercised && EditorApplication.timeSinceStartup-playStart>.75){Exercise();exercised=true;playStart=EditorApplication.timeSinceStartup;}
                if(exercised && EditorApplication.timeSinceStartup-playStart>=pending.command.duration)
                {
                    foreach(var saved in opened){var item=saved.Item1;bool accepted=item.TryInteract(item.transform.position);Assert(item.GetComponent<AssetIdentity>().assetId,"closes_again",accepted&&!item.IsOpen&&Quaternion.Angle(item.movingPivot.localRotation,saved.Item2)<.1f);}
                    Finish("completed",null);
                }
            }
            catch(Exception error){Finish("error",error.ToString());}
        }
        static void Finish(string status,string error)
        {
            var samples=sampler?sampler.frameMilliseconds.Where(v=>v>0 && !float.IsNaN(v)).OrderBy(v=>v).ToArray():new float[0];
            if(status=="completed")
            {Assert("scene","runtime_errors",errors.Count==0,string.Join("\n",errors.Take(20)));Assert("scene","runtime_frames",samples.Length>=2);}
            pending.result=new SceneResult{request_id=pending.action.request_id,status=status,error=error,
                development=new DevelopmentResult{command="playcheck",passed=status=="completed"&&checks.All(c=>c.passed),checks=checks.ToArray(),
                frames=samples.Length,mean_frame_ms=samples.Length>0?samples.Average():0,p95_frame_ms=samples.Length>0?samples[(int)((samples.Length-1)*.95)]:0,
                screenshots=captureCamera?new[]{"previews/"+pending.action.request_id+"_before.png","previews/"+pending.action.request_id+".png"}:new string[0],
                message="Actual Play-mode frame deltas on this editor/machine, not a target-platform benchmark."}};
            pending.finished=true;
            SessionState.SetString(Key,JsonUtility.ToJson(pending));
            if(EditorApplication.isPlayingOrWillChangePlaymode)EditorApplication.ExitPlaymode();else Changed(PlayModeStateChange.EnteredEditMode);
        }
    }
}
