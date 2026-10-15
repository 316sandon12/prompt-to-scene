using System;
using System.IO;
using System.Linq;
using PromptToScene;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

[InitializeOnLoad]
public static class UnityGameplay
{
    [Serializable] class Command { public string operation; }
    static string Root => AssetBridge.StateRoot;
    static double next, playReady;
    static UnityGameplay() { EditorApplication.update += Tick; }
    public static void Run()
    {
        PlayerSettings.companyName = "PromptToSceneFixture";
        PlayerSettings.productName = "GameplayV14";
        if(File.Exists("Assets/Gameplay.unity"))EditorSceneManager.OpenScene("Assets/Gameplay.unity");
        else EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        SessionState.SetBool("PTS.GameplaySmoke", true);
        Directory.CreateDirectory(Root);
        File.WriteAllText(Path.Combine(Root, "gameplay-ready"), "ready");
    }
    static void Need(bool good, string message) { if (!good) throw new Exception(message); }
    static void Tick()
    {
        if (!SessionState.GetBool("PTS.GameplaySmoke", false) || EditorApplication.timeSinceStartup < next) return;
        next = EditorApplication.timeSinceStartup + .2;
        try
        {
            if (SessionState.GetBool("PTS.GameplayPlay", false))
            {
                if (!EditorApplication.isPlaying) return;
                if (playReady == 0) { playReady = EditorApplication.timeSinceStartup + 2; return; }
                if (EditorApplication.timeSinceStartup < playReady) return;
                Play(); SessionState.SetBool("PTS.GameplayPlay", false); EditorApplication.isPlaying = false;
                File.WriteAllText(Path.Combine(Root, "gameplay-command-done"), "done"); return;
            }
            if (EditorApplication.isPlayingOrWillChangePlaymode) return;
            AssetBridge.ImportPending();
            var path = Path.Combine(Root, "gameplay-command.json"); if (!File.Exists(path)) return;
            var command = JsonUtility.FromJson<Command>(File.ReadAllText(path)); File.Delete(path);
            if (command.operation == "stop") { SessionState.SetBool("PTS.GameplaySmoke", false); EditorApplication.Exit(0); return; }
            if (command.operation == "play")
            {
                var session = GameSession.Find("apothecary"); Need(session, "Missing native flow");
                session.definition.settings.autosave = true;
                var save = Path.Combine(Application.persistentDataPath, "PromptToScene", session.definition.settings.save_key + ".json");
                foreach (var suffix in new[] { "", ".bak", ".tmp" }) if (File.Exists(save + suffix)) File.Delete(save + suffix);
                EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(), "Assets/Gameplay.unity");
                SessionState.SetBool("PTS.GameplayPlay", true); playReady = 0; EditorApplication.isPlaying = true; return;
            }
            if (command.operation == "scene") { CaptureScene(); File.WriteAllText(Path.Combine(Root, "gameplay-command-done"), "done"); return; }
            throw new Exception("Unknown smoke command");
        }
        catch (Exception error)
        {
            File.WriteAllText(Path.Combine(Root, "gameplay-error.txt"), error.ToString());
            SessionState.SetBool("PTS.GameplaySmoke", false); EditorApplication.Exit(1);
        }
    }
    static void Play()
    {
        var session = GameSession.Find("apothecary"); session.Initialize();
        Need(!session.TryRule("craft_potion") && session.GetQuantity("apothecary_potion") == 0, "Craft spent absent materials");
        var herb = Object.FindObjectsOfType<GameplayTrigger>(true).Single(x => x.ruleId == "collect_herb");
        Need(herb.GetComponent<Interaction>().TryInteract(herb.transform.position), "Bound pickup failed");
        Need(session.GetQuantity("apothecary_herb") == 6, "Pickup reward missing");
        Need(!session.TryRule("collect_herb"), "Once-only rule repeated");
        Need(session.TryRule("collect_bottle"), "Collect bottle failed");
        Need(session.TryRule("craft_potion"), "Craft failed");
        Need(session.GetQuantity("apothecary_herb") == 4 && session.GetQuantity("apothecary_bottle") == 2 && session.GetQuantity("apothecary_potion") == 1, "Wrong transaction");
        var ui = Object.FindObjectsOfType<GameUIScreen>().Single(x => x.kind == "inventory");
        ui.ShowPanel(true); ui.SelectItem(2); Need(ui.useButton.interactable, "Use button not enabled");
        ui.useButton.onClick.Invoke(); Need(session.GetQuantity("apothecary_potion") == 0 && session.Health == 70, "UI use did not consume/heal");
        Need(session.TryRule("craft_potion") && session.UseItem("apothecary_potion") && session.Health == 100, "Second heal failed");
        Need(session.TryRule("craft_potion"), "Third craft failed");
        Need(!session.UseItem("apothecary_potion") && session.GetQuantity("apothecary_potion") == 1, "Full health consumed item");
        Need(session.SaveProgress() && session.LoadProgress() && session.IsComplete("collect_herb"), "Progress restore failed");
        var save = Path.Combine(Application.persistentDataPath, "PromptToScene", session.definition.settings.save_key + ".json");
        string valid = File.ReadAllText(save); File.WriteAllText(save, "broken fixture");
        Need(!session.LoadProgress() && !session.SaveProgress() && File.ReadAllText(save) == "broken fixture", "Corrupt save overwritten");
        File.WriteAllText(save, valid); Need(session.LoadProgress(), "Recovery failed");
        ui.SelectItem(0); Capture(ui, 1280, 720, "inventory.png"); Capture(ui, 720, 1280, "inventory-portrait.png");
        // Dynamic paging independent of a particular game's inventory adapter.
        ui.enabled = false; ui.flowId = ""; ui.enabled = true;
        var many = Enumerable.Range(0, 20).Select(i => { var item = ScriptableObject.CreateInstance<GameItem>(); item.itemId = "page_" + i; item.displayName = item.itemId; return item; }).ToArray();
        ui.SetItems(many); Need(ui.nextPageButton.interactable, "Dynamic paging missing"); ui.ChangePage(1); ui.SelectItem(3); Need(ui.detailName.text == "page_19", "Second page selection wrong");
        Need(UnityEngine.EventSystems.EventSystem.current.currentSelectedGameObject, "Keyboard navigation has no focus");
        foreach (var item in many) Object.Destroy(item);
        session.definition.settings.autosave = false;
        var adapter = session.gameObject.AddComponent<FixtureProjectAdapter>();
        adapter.inventory["apothecary_herb"] = 4; adapter.inventory["apothecary_bottle"] = 2;
        session.projectAdapter = adapter;
        Need(session.TryRule("craft_potion") && adapter.GetQuantity("apothecary_potion")==1, "External inventory was not updated");
        adapter.reject = true;
        Need(!session.TryRule("craft_potion") && adapter.GetQuantity("apothecary_herb")==2, "Rejected adapter transaction changed inventory");
        adapter.reject = false;
        Need(session.UseItem("apothecary_potion") && adapter.Health==80, "External health was not updated");
        session.projectAdapter = null; Object.Destroy(adapter);
        foreach (var suffix in new[] { "", ".bak", ".tmp" }) if (File.Exists(save + suffix)) File.Delete(save + suffix);
        File.WriteAllText(Path.Combine(Root, "gameplay-play-passed"), "Native pickup, atomic craft/use, full-health rejection, persistent progress, corrupt-save protection, dynamic paging and UI focus passed.");
    }
    static void Capture(GameUIScreen screen, int width, int height, string name)
    {
        var go = new GameObject("FixtureCapture"); var camera = go.AddComponent<Camera>(); camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = new Color(.025f, .045f, .038f); camera.cullingMask = 1 << 5;
        var canvas = screen.GetComponent<Canvas>(); canvas.renderMode = RenderMode.ScreenSpaceCamera; canvas.worldCamera = camera; canvas.planeDistance = 2;
        var rt = new RenderTexture(width, height, 24); camera.targetTexture = rt; Canvas.ForceUpdateCanvases();
        screen.GetComponent<GameUIResponsive>().SendMessage("LateUpdate"); Canvas.ForceUpdateCanvases(); camera.Render();
        var previous = RenderTexture.active; RenderTexture.active = rt; var image = new Texture2D(width, height, TextureFormat.RGB24, false); image.ReadPixels(new Rect(0, 0, width, height), 0, 0); image.Apply(); File.WriteAllBytes(Path.Combine(Root, name), image.EncodeToPNG());
        RenderTexture.active = previous; camera.targetTexture = null; Object.Destroy(rt); Object.Destroy(image); Object.Destroy(go);
    }
    static void CaptureScene()
    {
        var go = new GameObject("FixtureGameCamera"); var camera = go.AddComponent<Camera>();
        camera.transform.position = new Vector3(4, 3.5f, 6); camera.transform.LookAt(new Vector3(0, 1.1f, -.3f));
        camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = new Color(.055f,.085f,.072f); camera.fieldOfView = 38;
        camera.cullingMask = ~(1 << 5); var rt = new RenderTexture(1600, 1000, 24); camera.targetTexture = rt;
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat; RenderSettings.ambientLight = new Color(.65f,.68f,.60f);
        camera.Render(); var previous = RenderTexture.active; RenderTexture.active = rt; var image = new Texture2D(1600,1000,TextureFormat.RGB24,false); image.ReadPixels(new Rect(0,0,1600,1000),0,0); image.Apply(); File.WriteAllBytes(Path.Combine(Root,"apothecary-scene.png"),image.EncodeToPNG());
        RenderTexture.active=previous; camera.targetTexture=null; Object.DestroyImmediate(image); Object.DestroyImmediate(rt); Object.DestroyImmediate(go);
    }
}
