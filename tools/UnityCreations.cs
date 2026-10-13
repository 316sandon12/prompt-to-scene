using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object=UnityEngine.Object;

[InitializeOnLoad]
public static class UnityCreations
{
    [Serializable] class Command{public string operation;}
    static string Root=>AssetBridge.StateRoot;
    static double next,playReady;
    static UnityCreations(){EditorApplication.update+=Tick;}
    public static void Run(){EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects,NewSceneMode.Single);SessionState.SetBool("PTS.CreationsSmoke",true);Directory.CreateDirectory(Root);File.WriteAllText(Path.Combine(Root,"creation-ready"),"ready");}
    static void Need(bool condition,string message){if(!condition)throw new Exception(message);}
    static T Read<T>(string path)=>JsonUtility.FromJson<T>(File.ReadAllText(Path.Combine(Root,path)));
    static void Tick()
    {
        if(!SessionState.GetBool("PTS.CreationsSmoke",false)||EditorApplication.timeSinceStartup<next)return;next=EditorApplication.timeSinceStartup+.2;
        try
        {
            if(SessionState.GetBool("PTS.CreationsPlay",false))
            {
                if(!EditorApplication.isPlaying)return;
                if(playReady==0){playReady=EditorApplication.timeSinceStartup+2;return;}
                if(EditorApplication.timeSinceStartup<playReady)return;
                Play();SessionState.SetBool("PTS.CreationsPlay",false);EditorApplication.isPlaying=false;File.WriteAllText(Path.Combine(Root,"creation-command-done"),"done");return;
            }
            if(EditorApplication.isPlayingOrWillChangePlaymode)return;
            AssetBridge.ImportPending();var path=Path.Combine(Root,"creation-command.json");if(!File.Exists(path))return;
            var command=JsonUtility.FromJson<Command>(File.ReadAllText(path));File.Delete(path);
            if(command.operation=="stop"){SessionState.SetBool("PTS.CreationsSmoke",false);EditorApplication.Exit(0);return;}
            var row=Read<ItemSpec>("game-items/forest_potion.json");var item=AssetDatabase.LoadAssetAtPath<GameItem>(row.item_path);Need(item&&item.icon&&item.model&&item.pickup,"Item links missing");
            var screen=Read<ScreenSpec>("game-screens/inventory.json");
            if(command.operation=="retain")
            {
                SessionState.SetString("PTS.ItemGUID",AssetDatabase.AssetPathToGUID(row.item_path));
                item.displayName="Forest remedy";item.description="Restores health on a long journey.";item.maxStack=7;EditorUtility.SetDirty(item);
                var root=PrefabUtility.LoadPrefabContents(screen.prefab_path);var ui=root.GetComponent<GameUIScreen>();ui.panel.GetComponent<RectTransform>().anchorMin=new Vector2(.1f,.1f);if(ui.onResume.GetPersistentEventCount()==0)UnityEventTools.AddPersistentListener(ui.onResume,ui.Settings);SessionState.SetInt("PTS.HookCount",ui.onResume.GetPersistentEventCount());PrefabUtility.SaveAsPrefabAsset(root,screen.prefab_path);PrefabUtility.UnloadPrefabContents(root);AssetDatabase.SaveAssets();
            }
            else if(command.operation=="verify")
            {
                Need(AssetDatabase.AssetPathToGUID(row.item_path)==SessionState.GetString("PTS.ItemGUID", ""),"Item identity changed");Need(item.displayName=="Forest remedy"&&item.description=="Restores health on a long journey."&&item.maxStack==7,"Manual item edits lost");
                var ui=AssetDatabase.LoadAssetAtPath<GameObject>(screen.prefab_path).GetComponent<GameUIScreen>();Need(ui.items[0]==item,"UI item reference lost");Need(ui.onResume.GetPersistentEventCount()==SessionState.GetInt("PTS.HookCount",0),"Custom UI event lost");Need(ui.panel.GetComponent<RectTransform>().anchorMin==new Vector2(.1f,.1f),"Manual layout lost");
                Need(Object.FindObjectsOfType<GameItemPickup>().Count(x=>x.item==item)==1,"Duplicate pickup");Need(Object.FindObjectsOfType<GameUIScreen>().Count(x=>x.screenId=="inventory")==1,"Duplicate UI host");
                EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),"Assets/Creations.unity");
            }
            else if(command.operation=="play"){SessionState.SetBool("PTS.CreationsPlay",true);EditorApplication.isPlaying=true;return;}
            File.WriteAllText(Path.Combine(Root,"creation-command-done"),"done");
        }
        catch(Exception e){File.WriteAllText(Path.Combine(Root,"creation-error.txt"),e.ToString());Debug.LogException(e);EditorApplication.Exit(1);}
    }
    static void Play()
    {
        var screens=Object.FindObjectsOfType<GameUIScreen>();var inventory=screens.Single(s=>s.kind=="inventory");var hud=screens.Single(s=>s.kind=="hud");var pause=screens.Single(s=>s.kind=="pause");
        inventory.ShowPanel(true);string selected="";inventory.onItemSelected.AddListener(id=>selected=id);inventory.slots[0].onClick.Invoke();Need(selected=="forest_potion"&&inventory.detailName.text=="Forest remedy"&&inventory.detailIcon.sprite==inventory.items[0].icon,"Inventory click/details failed");
        var pickup=Object.FindObjectsOfType<GameItemPickup>().First(x=>x.item==inventory.items[0]);pickup.GetComponent<Interaction>().TryInteract(pickup.transform.position);Need(inventory.counts[0].text=="1","Pickup did not update inventory count");
        hud.SetHealth(.4f);Need(Mathf.Abs(hud.healthFill.fillAmount-.4f)<.001f&&hud.healthFill.sprite,"HUD health fill invalid");hud.SetSkillIcon(0,inventory.items[0].icon);Need(hud.icons[0].sprite==inventory.items[0].icon,"HUD icon hook failed");
        pause.ShowPanel(true);Need(Time.timeScale==0,"Pause did not stop time");pause.Resume();Need(Time.timeScale==1&&!pause.panel.activeSelf,"Resume did not restore time");
        bool settings=false;pause.onSettings.AddListener(()=>settings=true);pause.Settings();Need(settings,"Settings hook failed");
        Capture(inventory);File.WriteAllText(Path.Combine(Root,"creation-play-passed"),"inventory selection, pickup count, HUD, pause, settings");
    }
    static void Capture(GameUIScreen screen)
    {
        var camera=new GameObject("UI capture camera",typeof(Camera)).GetComponent<Camera>();camera.clearFlags=CameraClearFlags.SolidColor;camera.backgroundColor=new Color(.045f,.055f,.05f);camera.orthographic=true;camera.nearClipPlane=.1f;camera.farClipPlane=20;camera.cullingMask=1<<5;
        foreach(var other in Object.FindObjectsOfType<GameUIScreen>())other.panel.SetActive(other==screen);screen.ShowPanel(true);
        foreach(var transform in screen.GetComponentsInChildren<Transform>(true))transform.gameObject.layer=5;
        var canvas=screen.GetComponent<Canvas>();canvas.renderMode=RenderMode.ScreenSpaceCamera;canvas.worldCamera=camera;canvas.planeDistance=2;var rt=new RenderTexture(1280,720,24);camera.targetTexture=rt;Canvas.ForceUpdateCanvases();camera.Render();var previous=RenderTexture.active;RenderTexture.active=rt;var image=new Texture2D(1280,720,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,1280,720),0,0);image.Apply();File.WriteAllBytes(Path.Combine(Root,"inventory.png"),image.EncodeToPNG());RenderTexture.active=previous;camera.targetTexture=null;Object.Destroy(rt);Object.Destroy(image);Object.Destroy(camera.gameObject);
    }
}
