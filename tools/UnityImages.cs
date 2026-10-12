using System;
using System.IO;
using PromptToScene.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class UnityImages
{
    [Serializable] class Command { public string operation, asset_id; }
    static string Root => AssetBridge.StateRoot;
    static Sprite retained;
    static double next;
    static UnityImages() { EditorApplication.update += Tick; }
    public static void Run()
    {
        EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        SessionState.SetBool("PTS.ImageSmoke", true);
        Directory.CreateDirectory(Root);
        File.WriteAllText(Path.Combine(Root, "image-ready"), "ready");
    }
    static void Require(bool ok, string message) { if (!ok) throw new Exception(message); }
    static void Tick()
    {
        if (!SessionState.GetBool("PTS.ImageSmoke", false) || EditorApplication.timeSinceStartup < next) return;
        next = EditorApplication.timeSinceStartup + .2;
        try
        {
            AssetBridge.ImportPending();
            string path = Path.Combine(Root, "image-command.json");
            if (!File.Exists(path)) return;
            var command = JsonUtility.FromJson<Command>(File.ReadAllText(path)); File.Delete(path);
            if (command.operation == "stop") { SessionState.SetBool("PTS.ImageSmoke", false); EditorApplication.Exit(0); return; }
            var record = JsonUtility.FromJson<ImageAssetResult>(File.ReadAllText(Path.Combine(Root, "image-receipts", command.asset_id + ".json")));
            var importer = (TextureImporter)AssetImporter.GetAtPath(record.texture_path);
            Require(importer.sRGBTexture && importer.wrapMode == TextureWrapMode.Clamp && !importer.mipmapEnabled, "UI settings lost");
            Require(importer.DoesSourceTextureHaveAlpha(), "Source alpha lost");
            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(record.texture_path);
            Require(sprite != null && sprite.rect.width == 128 && sprite.rect.height == 64, "Wrong sprite dimensions");
            Require(sprite.border == new Vector4(8, 6, 12, 4), "Nine-slice border order lost");
            if (command.operation == "retain") retained = sprite;
            if (command.operation == "verify") Require(retained != null && retained == sprite, "Reimport broke the existing Sprite reference");
            File.WriteAllText(Path.Combine(Root, "image-command-done"), "done");
        }
        catch (Exception error)
        {
            File.WriteAllText(Path.Combine(Root, "image-error.txt"), error.ToString());
            EditorApplication.Exit(1);
        }
    }
}
