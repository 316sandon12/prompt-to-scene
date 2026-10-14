using System.Collections.Generic;
using PromptToScene;
using UnityEngine;

// Test-only existing-game state. Never installed by the bridge.
public sealed class FixtureProjectAdapter : MonoBehaviour, IGameProjectAdapter
{
    public readonly Dictionary<string, int> inventory = new Dictionary<string, int>();
    public float Health { get; private set; } = 50;
    public float MaxHealth => 100;
    public bool reject;
    public int GetQuantity(string itemId) => inventory.TryGetValue(itemId, out var value) ? value : 0;
    public bool TryCommit(ItemQuantity[] costs, ItemQuantity[] rewards, float heal)
    {
        if (reject) return false;
        foreach(var row in costs)if(GetQuantity(row.item_id)<row.quantity)return false;
        foreach(var row in costs)inventory[row.item_id]=GetQuantity(row.item_id)-row.quantity;
        foreach(var row in rewards)inventory[row.item_id]=GetQuantity(row.item_id)+row.quantity;
        Health=Mathf.Min(MaxHealth,Health+heal);return true;
    }
}
