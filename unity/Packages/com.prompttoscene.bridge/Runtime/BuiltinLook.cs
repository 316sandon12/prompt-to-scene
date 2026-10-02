using UnityEngine;
using UnityEngine.Rendering;
namespace PromptToScene
{
    [ExecuteAlways]
    public sealed class BuiltinLook : MonoBehaviour
    {
        public Material colorGrade;
        void OnRenderImage(RenderTexture source,RenderTexture destination)
        {
            if(colorGrade && GraphicsSettings.currentRenderPipeline==null) Graphics.Blit(source,destination,colorGrade);
            else Graphics.Blit(source,destination);
        }
    }
}
