using System.Collections.Generic;
using PromptToScene;
using UnityEngine;

// Test-only public game API, deliberately not implementing the bridge interface.
public sealed class FixtureInventory : MonoBehaviour
{
    readonly Dictionary<string,int> items=new Dictionary<string,int>();
    public float CurrentHealth=50, MaximumHealth=100;
    public bool reject;
    public int Count(string id) => items.TryGetValue(id,out var n)?n:0;
    public bool Commit(ItemQuantity[] costs,ItemQuantity[] rewards,float heal)
    {
        if(reject) return false;
        foreach(var c in costs)if(Count(c.item_id)<c.quantity)return false;
        foreach(var c in costs)items[c.item_id]=Count(c.item_id)-c.quantity;
        foreach(var r in rewards)items[r.item_id]=Count(r.item_id)+r.quantity;
        CurrentHealth=Mathf.Min(MaximumHealth,CurrentHealth+heal);return true;
    }
}
