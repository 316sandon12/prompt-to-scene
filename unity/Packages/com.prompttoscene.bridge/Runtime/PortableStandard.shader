Shader "PromptToScene/Portable Standard"
{
    Properties
    {
        _Color ("Color", Color) = (1,1,1,1)
        _MainTex ("Albedo / Opacity", 2D) = "white" {}
        _Cutoff ("Alpha Cutoff", Range(0,1)) = 0.5
        _Glossiness ("Smoothness", Range(0,1)) = 0.5
        _GlossMapScale ("Smoothness Scale", Range(0,1)) = 1
        _SmoothnessTextureChannel ("Smoothness Channel", Float) = 0
        _Metallic ("Metallic", Range(0,1)) = 0
        _MetallicGlossMap ("Metallic / Smoothness", 2D) = "white" {}
        _BumpScale ("Normal Scale", Float) = 1
        _BumpMap ("Normal Map", 2D) = "bump" {}
        _EmissionColor ("Emission", Color) = (0,0,0,0)
        _EmissionMap ("Emission Map", 2D) = "white" {}
        _OcclusionStrength ("Occlusion", Range(0,1)) = 1
        _OcclusionMap ("Occlusion Map", 2D) = "white" {}
        _SpecularHighlights ("Specular", Float) = 1
        _GlossyReflections ("Reflections", Float) = 1
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Render Faces", Float) = 0
        [HideInInspector] _Mode ("Mode", Float) = 0
        [HideInInspector] _SrcBlend ("Source Blend", Float) = 1
        [HideInInspector] _DstBlend ("Destination Blend", Float) = 0
        [HideInInspector] _ZWrite ("Depth Write", Float) = 1
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" }
        Cull [_Cull]
        UsePass "Standard/FORWARD"
        UsePass "Standard/FORWARD_DELTA"
        UsePass "Standard/ShadowCaster"
        UsePass "Standard/DEFERRED"
        UsePass "Standard/META"
    }
    FallBack "Standard"
}
