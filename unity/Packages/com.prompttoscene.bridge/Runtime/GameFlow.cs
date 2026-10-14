using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.Events;

namespace PromptToScene
{
    [Serializable] public class ItemQuantity { public string item_id; public int quantity; }
    [Serializable] public class GameRule
    {
        public string rule_id, label, trigger, item_id, asset_id, pickup_id;
        public ItemQuantity[] costs = new ItemQuantity[0], rewards = new ItemQuantity[0];
        public string[] requires = new string[0];
        public float heal;
        public bool once;
    }
    [Serializable] public class GameFlowSpec
    {
        public int schema_version;
        public string flow_id, revision, expected_revision, title, slot, save_key, definition_path;
        public string[] item_ids, screen_ids;
        public ItemQuantity[] initial_inventory = new ItemQuantity[0];
        public GameRule[] rules = new GameRule[0];
        public float max_health = 100, initial_health = 100;
        public bool autosave = true;
    }

    // Existing games implement this on one component. TryCommit must be all-or-nothing.
    // The game remains responsible for persisting its own inventory and health.
    public interface IGameProjectAdapter
    {
        int GetQuantity(string itemId);
        float Health { get; }
        float MaxHealth { get; }
        bool TryCommit(ItemQuantity[] costs, ItemQuantity[] rewards, float heal);
    }

    [CreateAssetMenu(menuName = "Prompt-to-Scene/Gameplay Flow")]
    public sealed class GameFlow : ScriptableObject
    {
        public GameFlowSpec settings;
        public GameItem[] items = new GameItem[0];
    }

}
