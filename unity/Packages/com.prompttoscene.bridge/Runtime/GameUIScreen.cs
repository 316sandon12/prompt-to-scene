using System;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

namespace PromptToScene
{
    public sealed class GameUIScreen : MonoBehaviour
    {
        public string screenId, kind;
        public bool demoShortcuts = true;
        public GameObject panel;
        public GameItem[] items = new GameItem[0];
        public Button[] slots = new Button[0];
        public Image[] icons = new Image[0];
        public Text[] counts = new Text[0];
        public Text detailName, detailDescription;
        public Image detailIcon, healthFill;
        public UnityEvent<string> onItemSelected = new UnityEvent<string>();
        public UnityEvent onSettings = new UnityEvent();
        public UnityEvent onResume = new UnityEvent();
        int[] quantities = new int[16];
        bool ownsPause,ownsCursor;
        bool previousCursor;
        CursorLockMode previousLock;
        float previousTimeScale = 1;

        void Awake()
        {
            for(int i=0;i<slots.Length;i++){int index=i;slots[i].onClick.AddListener(()=>SelectItem(index));}
            Refresh();
            if(panel) panel.SetActive(kind=="hud");
        }
        void OnEnable() { GameItemPickup.Collected += AddItem; }
        void OnDisable() { GameItemPickup.Collected -= AddItem; ReleasePause(); ReleaseCursor(); }
        public void SetItems(GameItem[] value) { items=value ?? new GameItem[0]; Refresh(); }
        public void AddItem(GameItem item, int amount)
        {
            int index=Array.IndexOf(items,item);
            if(index<0 || index>=quantities.Length)return;
            quantities[index]=Mathf.Clamp(quantities[index]+amount,0,Mathf.Max(1,item.maxStack));Refresh();
        }
        public void Refresh()
        {
            for(int i=0;i<icons.Length;i++)
            {
                var item=i<items.Length?items[i]:null;
                icons[i].sprite=item?item.icon:null;icons[i].enabled=item && item.icon;
                if(i<slots.Length)slots[i].interactable=item;
                if(i<counts.Length)counts[i].text=item?(quantities[i]>0?quantities[i].ToString():""):"";
            }
        }
        public void SelectItem(int index)
        {
            if(index<0 || index>=items.Length || !items[index])return;
            var item=items[index];
            if(detailName)detailName.text=item.displayName;
            if(detailDescription)detailDescription.text=item.description;
            if(detailIcon){detailIcon.sprite=item.icon;detailIcon.enabled=item.icon;}
            onItemSelected.Invoke(item.itemId);
        }
        public void SetHealth(float normalized) { if(healthFill)healthFill.fillAmount=Mathf.Clamp01(normalized); }
        public void SetSkillIcon(int index, Sprite icon) { if(index>=0 && index<icons.Length){icons[index].sprite=icon;icons[index].enabled=icon;} }
        public void ShowPanel(bool visible)
        {
            if(!panel)return;
            panel.SetActive(visible);
            if(demoShortcuts && kind!="hud")
            {
                if(visible && !ownsCursor){previousCursor=Cursor.visible;previousLock=Cursor.lockState;Cursor.lockState=CursorLockMode.None;Cursor.visible=true;ownsCursor=true;}
                else if(!visible)ReleaseCursor();
            }
            if(kind=="pause")
            {
                if(visible && !ownsPause){previousTimeScale=Time.timeScale;Time.timeScale=0;ownsPause=true;}
                else if(!visible)ReleasePause();
            }
        }
        void ReleaseCursor(){if(ownsCursor){Cursor.visible=previousCursor;Cursor.lockState=previousLock;ownsCursor=false;}}
        void ReleasePause(){if(ownsPause){Time.timeScale=previousTimeScale;ownsPause=false;}}
        public void Resume(){ShowPanel(false);onResume.Invoke();}
        public void Settings(){onSettings.Invoke();}
        void Update()
        {
            if(!demoShortcuts || kind=="hud" || !panel)return;
            if(Pressed(kind=="pause"?"escapeKey":"iKey",kind=="pause"?KeyCode.Escape:KeyCode.I))ShowPanel(!panel.activeSelf);
        }
        static bool Pressed(string property, KeyCode code)
        {
#if ENABLE_LEGACY_INPUT_MANAGER
            return Input.GetKeyDown(code);
#elif ENABLE_INPUT_SYSTEM
            var type=Type.GetType("UnityEngine.InputSystem.Keyboard, Unity.InputSystem");
            var keyboard=type?.GetProperty("current")?.GetValue(null);
            var key=type?.GetProperty(property)?.GetValue(keyboard);
            return key!=null && (bool)key.GetType().GetProperty("wasPressedThisFrame").GetValue(key);
#else
            return false;
#endif
        }
    }
}
