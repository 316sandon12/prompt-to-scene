using UnityEngine;
using UnityEngine.Rendering;
namespace PromptToScene
{
    public sealed class SceneLook : MonoBehaviour
    {
        public string preset;
        public Light[] previousLights;
        public bool[] previousEnabled;
        public Material previousSky;
        public Color previousAmbient, previousFog;
        public AmbientMode previousAmbientMode;
        public bool previousFogEnabled;
        public float previousFogDensity;
        public Camera presentationCamera;
        public Light previousSun;
        public Camera[] previousCameras;
        public bool[] previousPost;
        public Material gradeMaterial;
    }
}
