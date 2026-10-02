using UnityEngine;
namespace PromptToScene
{
    public sealed class LevelMarker : MonoBehaviour
    {
        public string levelId;
        public Vector3[] checkpoints;
        public float playerRadius = .3f, playerHeight = 1.8f;
        public float maxStep = .22f;
        public int moduleCount;
    }
}
