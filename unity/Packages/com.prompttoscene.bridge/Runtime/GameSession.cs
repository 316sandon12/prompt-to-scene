using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.Events;

namespace PromptToScene
{
    [DefaultExecutionOrder(-100)]
    public sealed class GameSession : MonoBehaviour
    {
        public GameFlow definition;
        [Tooltip("Optional component implementing IGameProjectAdapter. Bind once per project.")]
        public MonoBehaviour projectAdapter;
        public UnityEvent<string> onRuleCompleted = new UnityEvent<string>();
        public UnityEvent<string> onFeedback = new UnityEvent<string>();
        public event Action Changed;
        public event Action Restored;
        public string LastMessage { get; private set; } = "";
        public string SaveError { get; private set; } = "";
        public bool LastSuccess { get; private set; }
        readonly Dictionary<string, int> quantities = new Dictionary<string, int>();
        readonly HashSet<string> completed = new HashSet<string>();
        float health;
        bool initialized, busy, ownsSave, loadBlocked;
        string savePath;
        IGameProjectAdapter Adapter => projectAdapter as IGameProjectAdapter;
        public float Health => Adapter != null ? Adapter.Health : health;
        public float MaxHealth => Adapter != null ? Adapter.MaxHealth : definition.settings.max_health;
        public IEnumerable<GameRule> CraftRules => definition.settings.rules.Where(r => r.trigger == "craft");

        [Serializable] class Progress
        {
            public int schema = 1;
            public string flow_id, save_key;
            public float health;
            public ItemQuantity[] inventory;
            public string[] completed;
        }

        void Awake() { if (definition) Initialize(); }
        public void Initialize()
        {
            if (initialized) return;
            if (!definition || definition.settings == null) throw new InvalidOperationException("Missing gameplay definition");
            var s = definition.settings;
            if (string.IsNullOrEmpty(s.save_key) || !System.Text.RegularExpressions.Regex.IsMatch(s.save_key, "^pts_[a-f0-9]{32}$"))
                throw new InvalidOperationException("Invalid gameplay save namespace");
            if (projectAdapter && Adapter == null) throw new InvalidOperationException("The bound component must implement IGameProjectAdapter");
            foreach (var row in s.initial_inventory) quantities[row.item_id] = row.quantity;
            health = s.initial_health;
            savePath = Path.Combine(Application.persistentDataPath, "PromptToScene", s.save_key + ".json");
            initialized = true;
            if (File.Exists(savePath)) LoadProgress();
        }

        public static GameSession Find(string flowId)
        {
            return FindObjectsOfType<GameSession>(true).FirstOrDefault(s => s.definition && s.definition.settings.flow_id == flowId);
        }
        public int GetQuantity(string itemId)
        {
            Initialize();
            return Adapter != null ? Adapter.GetQuantity(itemId) : quantities.TryGetValue(itemId, out var count) ? count : 0;
        }
        public bool IsComplete(string ruleId) { Initialize(); return completed.Contains(ruleId); }
        public GameRule Rule(string id) => definition.settings.rules.FirstOrDefault(r => r.rule_id == id);
        public GameRule UseRule(string itemId) => definition.settings.rules.FirstOrDefault(r => r.trigger == "use" && r.item_id == itemId);
        public bool CanApply(string ruleId, out string reason)
        {
            Initialize();
            var rule = Rule(ruleId);
            reason = "";
            if (rule == null) reason = "Unknown action";
            else if (rule.once && completed.Contains(ruleId)) reason = "Already completed";
            else if (rule.requires.Any(id => !completed.Contains(id))) reason = "Complete the prerequisite first";
            else if (rule.heal > 0 && Health >= MaxHealth) reason = "Health is already full";
            else if (rule.costs.Any(c => GetQuantity(c.item_id) < c.quantity)) reason = "Not enough materials";
            else
            {
                foreach (var item in definition.items)
                {
                    int count = GetQuantity(item.itemId)
                        - rule.costs.Where(c => c.item_id == item.itemId).Sum(c => c.quantity)
                        + rule.rewards.Where(c => c.item_id == item.itemId).Sum(c => c.quantity);
                    if (count > Mathf.Max(1, item.maxStack)) { reason = "Item stack is full"; break; }
                }
            }
            return reason.Length == 0;
        }

        public bool TryRule(string ruleId)
        {
            if (busy) return false;
            busy = true;
            try
            {
                if (!CanApply(ruleId, out var reason)) return Feedback(false, reason);
                var rule = Rule(ruleId);
                if (Adapter != null)
                {
                    // External components own the atomic transaction and their persistence.
                    if (!Adapter.TryCommit(rule.costs, rule.rewards, rule.heal)) return Feedback(false, "Project adapter rejected the action");
                }
                else
                {
                    foreach (var cost in rule.costs) quantities[cost.item_id] = GetQuantity(cost.item_id) - cost.quantity;
                    foreach (var reward in rule.rewards) quantities[reward.item_id] = GetQuantity(reward.item_id) + reward.quantity;
                    health = Mathf.Min(MaxHealth, health + rule.heal);
                }
                completed.Add(ruleId);
                if (definition.settings.autosave) SaveProgress();
                Feedback(true, rule.label);
                Notify(() => onRuleCompleted.Invoke(ruleId));
                Notify(() => Changed?.Invoke());
                return true;
            }
            catch (Exception error) { return Feedback(false, "Project action failed: " + error.Message); }
            finally { busy = false; }
        }
        bool Feedback(bool success, string message)
        { LastSuccess = success; LastMessage = message; Notify(() => onFeedback.Invoke(message)); return success; }
        // A UI listener must not turn an already committed transaction into a failure.
        void Notify(Action action) { try { action(); } catch (Exception error) { Debug.LogException(error, this); } }
        public bool UseItem(string itemId) { Initialize(); var r = UseRule(itemId); return r != null && TryRule(r.rule_id); }
        public void RefreshFromProject() { Notify(() => Changed?.Invoke()); }

        public bool SaveProgress()
        {
            Initialize();
            if (loadBlocked) return false;
            try
            {
                var progress = new Progress {
                    flow_id = definition.settings.flow_id, save_key = definition.settings.save_key,
                    health = health, inventory = quantities.Select(p => new ItemQuantity { item_id = p.Key, quantity = p.Value }).ToArray(),
                    completed = completed.OrderBy(x => x).ToArray()
                };
                Directory.CreateDirectory(Path.GetDirectoryName(savePath));
                string temporary = savePath + ".tmp";
                File.WriteAllText(temporary, JsonUtility.ToJson(progress, true));
                if (File.Exists(savePath)) File.Replace(temporary, savePath, savePath + ".bak");
                else File.Move(temporary, savePath);
                SaveError = ""; ownsSave = true; return true;
            }
            catch (Exception error) { SaveError = "Progress was not saved: " + error.Message; Notify(() => onFeedback.Invoke(SaveError)); return false; }
        }
        public bool LoadProgress()
        {
            Initialize();
            try
            {
                var p = JsonUtility.FromJson<Progress>(File.ReadAllText(savePath));
                if (p == null || p.schema != 1 || p.save_key != definition.settings.save_key || p.flow_id != definition.settings.flow_id
                    || p.inventory == null || p.completed == null || float.IsNaN(p.health) || float.IsInfinity(p.health)
                    || p.inventory.Any(c => c == null || c.quantity < 0 || string.IsNullOrEmpty(c.item_id))
                    || p.inventory.Select(c => c.item_id).Distinct().Count() != p.inventory.Length)
                    throw new InvalidDataException("Invalid save contents; existing progress file retained");
                quantities.Clear(); foreach (var row in p.inventory) quantities[row.item_id] = row.quantity;
                completed.Clear(); foreach (var id in p.completed) completed.Add(id);
                health = Mathf.Clamp(p.health, 0, definition.settings.max_health);
                SaveError = ""; ownsSave = true; loadBlocked = false; Feedback(true, "Progress restored"); Notify(() => Changed?.Invoke()); Notify(() => Restored?.Invoke()); return true;
            }
            catch (Exception error) { loadBlocked = true; SaveError = error.Message; Notify(() => onFeedback.Invoke(SaveError)); return false; }
        }
        void OnApplicationPause(bool paused) { if (paused && initialized && definition.settings.autosave && SaveError.Length == 0) SaveProgress(); }
        void OnApplicationQuit() { if (initialized && definition.settings.autosave && (ownsSave || !File.Exists(savePath)) && SaveError.Length == 0) SaveProgress(); }
    }

}
