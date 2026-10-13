using System;
using UnityEngine;
using UnityEngine.Events;

namespace PromptToScene
{
    [RequireComponent(typeof(Interaction))]
    public sealed class GameItemPickup : MonoBehaviour
    {
        public GameItem item;
        public int quantity = 1;
        public UnityEvent<GameItem> onCollected = new UnityEvent<GameItem>();
        public static event Action<GameItem, int> Collected;
        void Awake() { GetComponent<Interaction>().onInteracted.AddListener(Collect); }
        void OnDestroy() { var interaction=GetComponent<Interaction>();if(interaction)interaction.onInteracted.RemoveListener(Collect); }
        void Collect() { if(item) { onCollected.Invoke(item); Collected?.Invoke(item, quantity); } }
    }
}
