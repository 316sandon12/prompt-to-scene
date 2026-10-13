using UnityEngine;

namespace PromptToScene
{
    [CreateAssetMenu(menuName = "Prompt-to-Scene/Game Item")]
    public sealed class GameItem : ScriptableObject
    {
        public string itemId;
        public string displayName;
        [TextArea] public string description;
        public Sprite icon;
        public GameObject model;
        public GameObject pickup;
        public int maxStack = 99;
    }
}
