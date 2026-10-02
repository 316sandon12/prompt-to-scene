using System.Collections.Generic;
using UnityEngine;
namespace PromptToScene
{
    public sealed class FrameSampler : MonoBehaviour
    {
        public readonly List<float> frameMilliseconds = new List<float>();
        void Update() { if(frameMilliseconds.Count<20000) frameMilliseconds.Add(Time.unscaledDeltaTime*1000); }
    }
}
