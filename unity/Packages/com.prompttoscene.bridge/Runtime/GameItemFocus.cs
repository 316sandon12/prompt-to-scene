using UnityEngine;
using UnityEngine.EventSystems;

namespace PromptToScene
{
    public sealed class GameItemFocus : MonoBehaviour, IPointerEnterHandler, ISelectHandler
    {
        public GameUIScreen screen;
        public int slot;
        public void OnPointerEnter(PointerEventData data) { if (screen) screen.SelectItem(slot); }
        public void OnSelect(BaseEventData data) { if (screen) screen.SelectItem(slot); }
    }
}
