using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PromptToScene.Editor
{
    public static class GameplayFlows
    {
        [Serializable] class AdapterRequest { public string flow_id, target; }
        [Serializable] class AdapterRow { public string target, name, component; }
        [Serializable] class AdapterList { public string flow_id, bound_target; public AdapterRow[] adapters; }
        static void Id(string value) { if (value == null || !Regex.IsMatch(value, "^[a-z][a-z0-9_-]{0,63}$")) throw new Exception("Invalid gameplay identifier"); }
        static T Read<T>(string path) where T : class => File.Exists(path) ? JsonUtility.FromJson<T>(File.ReadAllText(path)) : null;
        static void Save(string path, object value) { Directory.CreateDirectory(Path.GetDirectoryName(path)); File.WriteAllText(path + ".tmp", JsonUtility.ToJson(value, true)); if (File.Exists(path)) File.Delete(path); File.Move(path + ".tmp", path); }
        static string Record(string id) => Path.Combine(AssetBridge.StateRoot, "gameplay", id + ".json");
        static string Target(MonoBehaviour component) => component.GetInstanceID().ToString();
        static DevelopmentResult Result(object value, string message) => new DevelopmentResult { command = "gameplay", passed = true, message = message, plan_json = JsonUtility.ToJson(value) };
        public static DevelopmentResult Execute(DevelopmentCommand command)
        {
            if (command.mode == "configure") return Configure(JsonUtility.FromJson<GameFlowSpec>(command.content_json));
            var query = JsonUtility.FromJson<AdapterRequest>(command.content_json); Id(query.flow_id);
            var session = DevelopmentActions.Loaded<GameSession>().SingleOrDefault(s => s.definition && s.definition.settings.flow_id == query.flow_id);
            var candidates = DevelopmentActions.Loaded<MonoBehaviour>().Where(c => c is IGameProjectAdapter).ToArray();
            if (command.mode == "bind" || command.mode == "unbind")
            {
                if (!session) throw new Exception("Place this gameplay flow in the active scene first");
                MonoBehaviour target = null;
                if (command.mode == "bind") { target = candidates.SingleOrDefault(c => Target(c) == query.target); if (!target) throw new Exception("Adapter changed; inspect the current scene again"); }
                Undo.RecordObject(session, "Bind project gameplay adapter"); session.projectAdapter = target; EditorUtility.SetDirty(session); EditorSceneManager.MarkSceneDirty(session.gameObject.scene);
            }
            else if (command.mode != "inspect") throw new Exception("Unknown gameplay adapter operation");
            return Result(new AdapterList { flow_id = query.flow_id, bound_target = session && session.projectAdapter ? Target(session.projectAdapter) : "", adapters = candidates.Select(c => new AdapterRow { target = Target(c), name = c.gameObject.name, component = c.GetType().FullName }).ToArray() }, "Compatible project adapters inspected");
        }
        static DevelopmentResult Configure(GameFlowSpec s)
        {
            Id(s.flow_id);
            if (s.schema_version != 1 || !Regex.IsMatch(s.revision ?? "", "^[a-f0-9]{32}$") || !Regex.IsMatch(s.save_key ?? "", "^pts_[a-f0-9]{32}$")
                || s.item_ids == null || s.item_ids.Length < 1 || s.item_ids.Length > 128 || s.rules == null || s.rules.Length < 1 || s.rules.Length > 128
                || s.initial_inventory == null || s.screen_ids == null || s.max_health < 1 || float.IsNaN(s.max_health) || float.IsInfinity(s.max_health)
                || s.initial_health < 0 || s.initial_health > s.max_health) throw new Exception("Invalid gameplay definition");
            var old = Read<GameFlowSpec>(Record(s.flow_id));
            if (old?.revision == s.revision) return Result(old, "Gameplay already configured");
            if ((old?.revision ?? "") != (s.expected_revision ?? "")) throw new Exception("Gameplay changed since this request was prepared");
            var itemSet = new HashSet<string>(s.item_ids);
            if (itemSet.Count != s.item_ids.Length || s.rules.Select(r => r.rule_id).Distinct().Count() != s.rules.Length) throw new Exception("Repeated gameplay identifiers");
            var items = s.item_ids.Select(id => { Id(id); var row = Read<ItemSpec>(Path.Combine(AssetBridge.StateRoot, "game-items", id + ".json")); var item = row == null ? null : AssetDatabase.LoadAssetAtPath<GameItem>(row.item_path); if (!item) throw new Exception("Missing game item " + id); return item; }).ToArray();
            var bindings = new List<KeyValuePair<Interaction, GameRule>>();
            foreach (var rule in s.rules)
            {
                Id(rule.rule_id);
                if (!new[] { "interact", "craft", "use" }.Contains(rule.trigger) || rule.costs == null || rule.rewards == null || rule.requires == null
                    || rule.costs.Length > 16 || rule.rewards.Length > 16 || rule.heal < 0 || float.IsNaN(rule.heal) || float.IsInfinity(rule.heal)
                    || rule.requires.Any(r => !s.rules.Any(x => x.rule_id == r))) throw new Exception("Invalid gameplay rule");
                foreach (var rows in new[] { rule.costs, rule.rewards }) if (rows.Any(c => !itemSet.Contains(c.item_id) || c.quantity < 1 || c.quantity > 9999) || rows.Select(c => c.item_id).Distinct().Count() != rows.Length) throw new Exception("Invalid item quantities");
                if (rule.trigger == "use" && (!itemSet.Contains(rule.item_id) || !rule.costs.Any(c => c.item_id == rule.item_id))) throw new Exception("Use rules must consume their item");
                Interaction[] targets = new Interaction[0];
                if (!string.IsNullOrEmpty(rule.asset_id)) targets = DevelopmentActions.Assets(rule.asset_id).Select(a => a.GetComponent<Interaction>()).ToArray();
                if (!string.IsNullOrEmpty(rule.pickup_id)) targets = DevelopmentActions.Loaded<GameItemPickup>().Where(p => p.item && p.item.itemId == rule.pickup_id).Select(p => p.GetComponent<Interaction>()).ToArray();
                if ((!string.IsNullOrEmpty(rule.asset_id) || !string.IsNullOrEmpty(rule.pickup_id)) && (targets.Length == 0 || targets.Any(t => !t))) throw new Exception("Place the referenced interactive object before configuring the flow");
                foreach (var interaction in targets)
                {
                    var bound = interaction.GetComponent<GameplayTrigger>();
                    if (bound && bound.flowId != s.flow_id) throw new Exception("Interaction belongs to another gameplay flow");
                    bindings.Add(new KeyValuePair<Interaction, GameRule>(interaction, rule));
                }
            }
            if (bindings.Select(b => b.Key).Distinct().Count() != bindings.Count) throw new Exception("An object cannot trigger two rules");
            if (s.initial_inventory.Any(c => !itemSet.Contains(c.item_id) || c.quantity < 1 || c.quantity > items.First(i => i.itemId == c.item_id).maxStack)) throw new Exception("Invalid initial inventory");
            var screens = s.screen_ids.SelectMany(id => DevelopmentActions.Loaded<GameUIScreen>().Where(x => x.screenId == id)).ToArray();
            if (s.screen_ids.Any(id => !screens.Any(x => x.screenId == id))) throw new Exception("Place every referenced UI in the active scene first");
            if (screens.Any(x => !string.IsNullOrEmpty(x.flowId) && x.flowId != s.flow_id)) throw new Exception("UI belongs to another gameplay flow");
            string folder = "Assets/PromptToScene/Gameplay/" + s.flow_id;
            s.definition_path = old?.definition_path ?? folder + "/Flow.asset";
            var definition = AssetDatabase.LoadAssetAtPath<GameFlow>(s.definition_path);
            if (old != null && !definition || definition && definition.settings.flow_id != s.flow_id || old == null && AssetDatabase.LoadMainAssetAtPath(s.definition_path)) throw new Exception("Gameplay asset ownership mismatch");
            Directory.CreateDirectory(folder); AssetDatabase.Refresh();
            if (!definition) { definition = ScriptableObject.CreateInstance<GameFlow>(); AssetDatabase.CreateAsset(definition, s.definition_path); }
            Undo.RecordObject(definition, "Configure gameplay rules"); definition.settings = s; definition.items = items; EditorUtility.SetDirty(definition);
            var session = DevelopmentActions.Loaded<GameSession>().SingleOrDefault(x => x.definition == definition);
            if (!session) { var obj = new GameObject(s.title + " · Gameplay"); session = obj.AddComponent<GameSession>(); session.definition = definition; Undo.RegisterCreatedObjectUndo(obj, "Create gameplay flow"); }
            foreach (var stale in DevelopmentActions.Loaded<GameplayTrigger>().Where(x => x.flowId == s.flow_id && !bindings.Any(b => b.Key.gameObject == x.gameObject))) Undo.DestroyObjectImmediate(stale);
            foreach (var pair in bindings) { var trigger = pair.Key.GetComponent<GameplayTrigger>() ?? Undo.AddComponent<GameplayTrigger>(pair.Key.gameObject); Undo.RecordObject(trigger, "Bind gameplay rule"); trigger.flowId = s.flow_id; trigger.ruleId = pair.Value.rule_id; EditorUtility.SetDirty(trigger); }
            foreach (var stale in DevelopmentActions.Loaded<GameUIScreen>().Where(x => x.flowId == s.flow_id && !screens.Contains(x))) { Undo.RecordObject(stale, "Unbind gameplay UI"); stale.flowId = ""; EditorUtility.SetDirty(stale); }
            foreach (var screen in screens) { Undo.RecordObject(screen, "Bind gameplay UI"); screen.flowId = s.flow_id; EditorUtility.SetDirty(screen); }
            AssetDatabase.SaveAssets(); EditorSceneManager.MarkSceneDirty(DevelopmentActions.Scene);
            Save(Record(s.flow_id), s); Save(Path.Combine(AssetBridge.StateRoot, "gameplay-history", s.flow_id, s.revision + ".json"), s);
            return Result(s, "Gameplay rules and native project bindings ready");
        }
    }
}
