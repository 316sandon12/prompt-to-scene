Shader "Hidden/PromptToScene/SceneLook"
{
    Properties { _MainTex ("Source", 2D) = "white" {} _Exposure ("Exposure", Float) = 1 _Saturation ("Saturation", Float) = 1 _Tint ("Tint", Color) = (1,1,1,1) }
    SubShader { Cull Off ZWrite Off ZTest Always
        Pass { CGPROGRAM
            #pragma vertex vert_img
            #pragma fragment frag
            #include "UnityCG.cginc"
            sampler2D _MainTex;
            float _Exposure, _Saturation;
            float4 _Tint;
            float4 frag(v2f_img i) : SV_Target
            {
                float4 source = tex2D(_MainTex, i.uv);
                float3 c = source.rgb * _Exposure * _Tint.rgb;
                float luminance = dot(c, float3(.2126,.7152,.0722));
                c = lerp(luminance.xxx,c,_Saturation);
                return float4(max(c,0),source.a);
            }
        ENDCG }
    }
}
