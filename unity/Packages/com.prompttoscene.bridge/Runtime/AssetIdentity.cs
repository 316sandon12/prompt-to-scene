using UnityEngine;

namespace PromptToScene
{
    /// <summary>Stable link between a Blender asset, its prefab, and scene instances.</summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("")]
    public sealed class AssetIdentity : MonoBehaviour
    {
        [HideInInspector] public string assetId;
        [HideInInspector] public string revision;
    }
}
