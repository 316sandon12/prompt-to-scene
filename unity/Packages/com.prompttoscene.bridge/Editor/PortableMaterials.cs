using System;
using System.Linq;
using UnityEngine;
using UnityEngine.Rendering;

namespace PromptToScene.Editor
{
    internal static class PortableMaterials
    {
        public static void Validate(MaterialData data)
        {
            if (!new[] { "opaque", "mask", "blend" }.Contains(data.surface ?? "opaque") ||
                !Finite(data.alpha_cutoff, 1) || !Finite(data.emission_strength, 1000) ||
                data.emission == null || data.emission.Length != 3 || data.emission.Any(v => !Finite(v, 1000)))
                throw new Exception("Invalid portable surface or emission parameters");
        }

        static bool Finite(float v, float max) => !float.IsNaN(v) && v >= 0 && v <= max;
        static void Keyword(Material material, string name, bool enabled)
        { if (enabled) material.EnableKeyword(name); else material.DisableKeyword(name); }

        public static void Apply(Material material, MaterialData data, bool urp, Texture emission)
        {
            bool blend = data.surface == "blend", mask = data.surface == "mask";
            material.SetOverrideTag("RenderType", blend ? "Transparent" : mask ? "TransparentCutout" : "Opaque");
            material.SetFloat("_SrcBlend", (float)(blend ? BlendMode.SrcAlpha : BlendMode.One));
            material.SetFloat("_DstBlend", (float)(blend ? BlendMode.OneMinusSrcAlpha : BlendMode.Zero));
            material.SetFloat("_ZWrite", blend ? 0 : 1);
            material.SetFloat("_Cutoff", data.alpha_cutoff);
            if (material.HasProperty("_Cull")) material.SetFloat("_Cull", data.two_sided ? 0 : 2);
            material.doubleSidedGI = data.two_sided;
            Keyword(material, "_ALPHATEST_ON", mask);
            Keyword(material, "_ALPHABLEND_ON", !urp && blend);
            Keyword(material, "_ALPHAPREMULTIPLY_ON", false);
            if (urp)
            {
                material.SetFloat("_Surface", blend ? 1 : 0);
                material.SetFloat("_Blend", 0);
                material.SetFloat("_AlphaClip", mask ? 1 : 0);
                Keyword(material, "_SURFACE_TYPE_TRANSPARENT", blend);
                material.SetShaderPassEnabled("ShadowCaster", !blend);
                material.SetShaderPassEnabled("DepthOnly", !blend);
            }
            else material.SetFloat("_Mode", blend ? 2 : mask ? 1 : 0);
            material.renderQueue = blend ? (int)RenderQueue.Transparent : mask ? (int)RenderQueue.AlphaTest : -1;
            var color = new Color(data.emission[0], data.emission[1], data.emission[2]) * data.emission_strength;
            material.SetColor("_EmissionColor", color);
            material.SetTexture("_EmissionMap", emission);
            bool emits = color.maxColorComponent > 0;
            Keyword(material, "_EMISSION", emits);
            material.globalIlluminationFlags = emits ? MaterialGlobalIlluminationFlags.BakedEmissive : MaterialGlobalIlluminationFlags.EmissiveIsBlack;
        }
    }
}
