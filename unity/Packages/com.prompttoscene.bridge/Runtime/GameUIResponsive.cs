using UnityEngine;

namespace PromptToScene
{
    // Disable adaptiveLayout to keep a custom layout exactly as authored.
    [ExecuteAlways]
    public sealed class GameUIResponsive : MonoBehaviour
    {
        public bool adaptiveLayout = true;
        public RectTransform safeArea, grid;
        public GameUIScreen screen;
        Rect lastSafe;
        Vector2 lastSize;
        void OnEnable() { lastSize = Vector2.zero; }
        void LateUpdate()
        {
            if (!adaptiveLayout || !safeArea || !screen || !screen.panel) return;
            Rect safe = Screen.safeArea;
            var canvas = GetComponent<Canvas>();
            var size = canvas ? canvas.pixelRect.size : new Vector2(Screen.width, Screen.height);
            if (size.x <= 0 || size.y <= 0 || (lastSafe == safe && lastSize == size)) return;
            lastSafe = safe; lastSize = size;
            bool textureTarget = canvas && canvas.worldCamera && canvas.worldCamera.targetTexture;
            safeArea.anchorMin = textureTarget ? Vector2.zero : new Vector2(safe.xMin / Screen.width, safe.yMin / Screen.height);
            safeArea.anchorMax = textureTarget ? Vector2.one : new Vector2(safe.xMax / Screen.width, safe.yMax / Screen.height);
            safeArea.offsetMin = safeArea.offsetMax = Vector2.zero;
            if (screen.kind != "inventory" || !grid) return;
            bool narrow = size.x / size.y < 1.15f;
            grid.anchorMin = narrow ? new Vector2(.04f,.42f) : new Vector2(.04f,.14f);
            grid.anchorMax = narrow ? new Vector2(.96f,.83f) : new Vector2(.59f,.83f);
            if(screen.craftPanel){var r=screen.craftPanel.GetComponent<RectTransform>();r.anchorMin=grid.anchorMin;r.anchorMax=grid.anchorMax;}
            if(screen.useButton){var r=screen.useButton.GetComponent<RectTransform>();r.anchorMin=narrow?new Vector2(.65f,.06f):new Vector2(.65f,.08f);r.anchorMax=narrow?new Vector2(.96f,.13f):new Vector2(.95f,.17f);}
            if(screen.detailIcon){var r=screen.detailIcon.rectTransform;r.anchorMin=narrow?new Vector2(.04f,.19f):new Vector2(.67f,.5f);r.anchorMax=narrow?new Vector2(.28f,.39f):new Vector2(.91f,.81f);}
            if(screen.detailName){var r=screen.detailName.rectTransform;r.anchorMin=narrow?new Vector2(.32f,.3f):new Vector2(.65f,.38f);r.anchorMax=narrow?new Vector2(.96f,.4f):new Vector2(.95f,.49f);}
            if(screen.detailDescription){var r=screen.detailDescription.rectTransform;r.anchorMin=narrow?new Vector2(.32f,.15f):new Vector2(.65f,.19f);r.anchorMax=narrow?new Vector2(.96f,.3f):new Vector2(.95f,.37f);}
        }
    }
}
