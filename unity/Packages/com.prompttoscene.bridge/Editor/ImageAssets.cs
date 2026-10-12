using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace PromptToScene.Editor
{
    [Serializable] public class ImageAssetRequest
    {
        public int schema_version, width, height;
        public string asset_id, revision, expected_revision, file, sha256, kind;
        public int[] border;
        public bool transparent, pixel_art;
    }
    [Serializable] public class ImageAssetResult
    {
        public string asset_id, revision, kind, texture_path, texture_guid, sprite_path, request_id, engine;
        public int width, height;
        public int[] border;
    }

    public static class ImageAssets
    {
        static string Root => AssetBridge.StateRoot;
        static bool Id(string value) => value != null && Regex.IsMatch(value, "^[a-f0-9]{32}$");
        static string Hash(byte[] bytes)
        { using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(); }
        static int ReadInt(byte[] bytes, int offset) =>
            (bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3];
        static void SafePath(string path)
        {
            var info = new FileInfo(Path.GetFullPath(path)) as FileSystemInfo;
            while (info != null)
            {
                if (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) != 0)
                    throw new Exception("Image paths cannot pass through symbolic links");
                info = info is FileInfo file ? file.Directory : ((DirectoryInfo)info).Parent;
            }
        }

        public static SceneResult Execute(SceneAction action)
        {
            var data = JsonUtility.FromJson<ImageAssetRequest>(action.image_json ?? "{}");
            if (data.schema_version != 1 || data.asset_id != action.asset_id || !Id(data.revision)
                || data.file != "images/" + action.asset_id + "/" + data.revision + "/image.png")
                throw new Exception("Invalid retained image identity");
            if (!new[] { "icon", "button", "panel", "portrait", "background", "texture" }.Contains(data.kind))
                throw new Exception("Unsupported image kind");
            if (data.width < 16 || data.width > 4096 || data.height < 16 || data.height > 4096
                || data.border == null || data.border.Length != 4 || data.border.Any(v => v < 0)
                || data.border[0] + (long)data.border[2] >= data.width || data.border[1] + (long)data.border[3] >= data.height
                || (data.kind != "button" && data.kind != "panel" && data.border.Any(v => v > 0)))
                throw new Exception("Invalid image dimensions or nine-slice margins");
            if (!string.IsNullOrEmpty(data.expected_revision) && !Id(data.expected_revision))
                throw new Exception("Invalid expected image revision");
            string source = Path.Combine(Root, data.file);
            SafePath(source);
            if (!File.Exists(source) || new FileInfo(source).Length > 20 * 1024 * 1024)
                throw new Exception("Prepared image missing or larger than 20 MiB");
            byte[] bytes = File.ReadAllBytes(source);
            if (bytes.Length < 33 || !bytes.Take(8).SequenceEqual(new byte[] {137,80,78,71,13,10,26,10})
                || Hash(bytes) != data.sha256 || ReadInt(bytes, 16) != data.width || ReadInt(bytes, 20) != data.height)
                throw new Exception("Prepared image was changed or has mismatched dimensions");
            string recordPath = Path.Combine(Root, "image-receipts", data.asset_id + ".json");
            var current = File.Exists(recordPath) ? JsonUtility.FromJson<ImageAssetResult>(File.ReadAllText(recordPath)) : null;
            string existingRevision = current?.revision ?? "";
            if (existingRevision != (data.expected_revision ?? "") && existingRevision != data.revision)
                throw new Exception("Image changed after this import was queued; publish again to update it");
            bool ui = data.kind != "texture";
            if (current != null && (current.kind != "texture") != ui)
                throw new Exception("Choose a new asset ID when changing between UI and surface texture");
            string path = current != null ? AssetDatabase.GUIDToAssetPath(current.texture_guid)
                : "Assets/PromptToScene/Images/" + data.asset_id + "/" + data.asset_id + ".png";
            if (current != null && (string.IsNullOrEmpty(path) || !path.StartsWith("Assets/")))
                throw new Exception("Managed image was removed; restore it before updating");
            string destination = Path.Combine(AssetBridge.ProjectRoot, path);
            SafePath(destination);
            string owner = "PromptToScene.Image:" + data.asset_id;
            var existing = AssetImporter.GetAtPath(path) as TextureImporter;
            if (File.Exists(destination) && (existing == null || existing.userData != owner))
                throw new Exception("Image destination contains an unowned asset");
            byte[] old = File.Exists(destination) ? File.ReadAllBytes(destination) : null;
            byte[] meta = File.Exists(destination + ".meta") ? File.ReadAllBytes(destination + ".meta") : null;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(destination));
                File.WriteAllBytes(destination, bytes);
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer == null) throw new Exception("Native image import did not produce a TextureImporter");
                importer.textureType = ui ? TextureImporterType.Sprite : TextureImporterType.Default;
                importer.spriteImportMode = SpriteImportMode.Single;
                var textureSettings = new TextureImporterSettings();
                importer.ReadTextureSettings(textureSettings);
                textureSettings.spriteMeshType = SpriteMeshType.FullRect;
                textureSettings.spriteAlignment = (int)SpriteAlignment.Center;
                importer.SetTextureSettings(textureSettings);
                importer.spritePixelsPerUnit = 100;
                importer.spriteBorder = new Vector4(data.border[0], data.border[3], data.border[2], data.border[1]);
                importer.alphaSource = TextureImporterAlphaSource.FromInput;
                importer.alphaIsTransparency = data.transparent;
                importer.sRGBTexture = true;
                importer.mipmapEnabled = !ui;
                importer.npotScale = TextureImporterNPOTScale.None;
                importer.wrapMode = ui ? TextureWrapMode.Clamp : TextureWrapMode.Repeat;
                importer.filterMode = data.pixel_art ? FilterMode.Point : FilterMode.Bilinear;
                importer.textureCompression = ui ? TextureImporterCompression.Uncompressed : TextureImporterCompression.Compressed;
                importer.maxTextureSize = Mathf.NextPowerOfTwo(Mathf.Max(data.width, data.height));
                importer.isReadable = false;
                importer.userData = owner;
                importer.SaveAndReimport();
                var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                if (texture == null || texture.width != data.width || texture.height != data.height)
                    throw new Exception("Native image dimensions differ from the prepared file");
                if (ui && AssetDatabase.LoadAssetAtPath<Sprite>(path) == null)
                    throw new Exception("Native image import did not produce a Sprite");
                AssetDatabase.SetLabels(texture, AssetDatabase.GetLabels(texture).Union(new[] {"PTS.Image", data.kind}).ToArray());
                AssetDatabase.SaveAssets();
                var result = new ImageAssetResult { asset_id = data.asset_id, revision = data.revision,
                    kind = data.kind, texture_path = path, sprite_path = ui ? path : "",
                    texture_guid = AssetDatabase.AssetPathToGUID(path), width = texture.width,
                    height = texture.height, border = data.border, engine = "unity", request_id = action.request_id };
                AssetBridge.WriteJson(recordPath, result);
                return new SceneResult { image = result };
            }
            catch
            {
                if (old != null)
                {
                    File.WriteAllBytes(destination, old);
                    if (meta != null) File.WriteAllBytes(destination + ".meta", meta);
                    AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
                }
                else AssetDatabase.DeleteAsset(path);
                throw;
            }
        }
    }
}
