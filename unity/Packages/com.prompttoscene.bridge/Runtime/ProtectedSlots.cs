using UnityEngine;
namespace PromptToScene
{
    // Canonical slots allow material assignments to survive generated hierarchy replacement.
    [AddComponentMenu("")]
    public sealed class ProtectedSlots : MonoBehaviour
    {
        [HideInInspector] public string[] names;
        [HideInInspector] public Material[] generated;
    }
}
