using System;
using UnityEngine;
using UnityEngine.Events;
using System.Linq;
using System.Collections.Generic;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace PromptToScene
{
    public sealed class GameUIScreen : MonoBehaviour
    {
        public string screenId, kind, flowId;
        public Button useButton, nextPageButton, previousPageButton;
        public Text pageLabel, feedbackLabel, emptyLabel;
        public RectTransform craftList;
        public Button craftButtonTemplate;
        public Button craftToggle;
        public GameObject craftPanel, itemGrid;
        GameSession session;
        int page, selectedIndex = -1;
        readonly List<int> visibleItems = new List<int>();
        readonly List<Button> craftButtons = new List<Button>();
        float nextRefresh;
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
            for (int i=0;i<slots.Length;i++)
            {
                int index=i; slots[i].onClick.AddListener(()=>SelectItem(index));
                var focus=slots[i].gameObject.GetComponent<GameItemFocus>() ?? slots[i].gameObject.AddComponent<GameItemFocus>();
                focus.screen=this; focus.slot=index;
            }
            if(useButton)useButton.onClick.AddListener(UseSelected);
            if(nextPageButton)nextPageButton.onClick.AddListener(()=>ChangePage(1));
            if(previousPageButton)previousPageButton.onClick.AddListener(()=>ChangePage(-1));
            if(craftToggle)craftToggle.onClick.AddListener(()=>{if(craftPanel){craftPanel.SetActive(!craftPanel.activeSelf);if(itemGrid)itemGrid.SetActive(!craftPanel.activeSelf);craftToggle.GetComponentInChildren<Text>().text=craftPanel.activeSelf?"Items":"Craft";}});
            if(panel) panel.SetActive(kind=="hud");
            Refresh();
        }
        void OnEnable()
        {
            GameItemPickup.Collected += AddItem;
            session=string.IsNullOrEmpty(flowId)?null:GameSession.Find(flowId);
            if(session){session.Changed+=Refresh;session.onFeedback.AddListener(Feedback);BuildCrafting();}
            Refresh();
        }
        void OnDisable()
        {
            GameItemPickup.Collected -= AddItem;
            if(session){session.Changed-=Refresh;session.onFeedback.RemoveListener(Feedback);}
            ReleasePause(); ReleaseCursor();
        }
        void Feedback(string text){if(feedbackLabel)feedbackLabel.text=text;}
        void BuildCrafting()
        {
            foreach(var old in craftButtons)if(old)Destroy(old.gameObject);craftButtons.Clear();
            if(!craftList || !craftButtonTemplate || !session)return;
            craftButtonTemplate.gameObject.SetActive(false);
            foreach(var rule in session.CraftRules)
            {
                var button=Instantiate(craftButtonTemplate,craftList);button.gameObject.SetActive(true);
                button.GetComponentInChildren<Text>(true).text=rule.label;string id=rule.rule_id;
                button.onClick.RemoveAllListeners();button.onClick.AddListener(()=>session.TryRule(id));craftButtons.Add(button);
            }
            if(craftToggle)craftToggle.gameObject.SetActive(craftButtons.Count>0);
        }
        public void SetItems(GameItem[] value) { items=value ?? new GameItem[0]; selectedIndex=-1; page=0; Refresh(); }
        public void AddItem(GameItem item, int amount)
        {
            if(session)return;
            int index=Array.IndexOf(items,item);
            if(index<0)return;
            if(quantities.Length<items.Length)Array.Resize(ref quantities,items.Length);
            quantities[index]=Mathf.Clamp(quantities[index]+amount,0,Mathf.Max(1,item.maxStack));Refresh();
        }
        int Quantity(int index)=>session?session.GetQuantity(items[index].itemId):(index<quantities.Length?quantities[index]:0);
        public void Refresh()
        {
            visibleItems.Clear();
            for(int i=0;i<items.Length;i++)if(items[i] && (kind!="inventory" || !session || Quantity(i)>0))visibleItems.Add(i);
            int capacity=Mathf.Max(1,icons.Length), pages=Mathf.Max(1,Mathf.CeilToInt(visibleItems.Count/(float)capacity));
            page=Mathf.Clamp(page,0,pages-1);
            for(int i=0;i<icons.Length;i++)
            {
                int position=page*capacity+i,index=position<visibleItems.Count?visibleItems[position]:-1;
                var item=index>=0?items[index]:null;
                if(icons[i]){icons[i].sprite=item?item.icon:null;icons[i].enabled=item && item.icon;}
                if(i<slots.Length && slots[i])slots[i].interactable=item;
                if(i<counts.Length && counts[i])counts[i].text=item && Quantity(index)>0?Quantity(index).ToString():"";
            }
            if(pageLabel)pageLabel.text=(page+1)+" / "+pages;
            if(previousPageButton)previousPageButton.interactable=page>0;
            if(nextPageButton)nextPageButton.interactable=page+1<pages;
            if(emptyLabel)emptyLabel.gameObject.SetActive(kind=="inventory" && visibleItems.Count==0);
            if(selectedIndex<0 || selectedIndex>=items.Length || !items[selectedIndex] || session && Quantity(selectedIndex)<=0)
            {
                selectedIndex=-1;if(detailName)detailName.text="Select an item";if(detailDescription)detailDescription.text="";if(detailIcon)detailIcon.enabled=false;
            }
            UpdateUse();
            if(selectedIndex>=0 && detailDescription)detailDescription.text=items[selectedIndex].description+(session?"\nOwned: "+Quantity(selectedIndex):"");
            if(session)
            {
                SetHealth(session.MaxHealth>0?session.Health/session.MaxHealth:0);
                var rules=session.CraftRules.ToArray();
                for(int i=0;i<craftButtons.Count && i<rules.Length;i++)craftButtons[i].interactable=session.CanApply(rules[i].rule_id,out _);
                if(session.SaveError.Length>0)Feedback(session.SaveError);
            }
        }
        void UpdateUse()
        {
            if(!useButton)return;
            var rule=session && selectedIndex>=0?session.UseRule(items[selectedIndex].itemId):null;
            useButton.interactable=rule!=null && session.CanApply(rule.rule_id,out _);
            var text=useButton.GetComponentInChildren<Text>();if(text)text.text=rule?.label ?? "Use";
        }
        public void SelectItem(int index)
        {
            int position=page*Mathf.Max(1,icons.Length)+index;
            if(position<0 || position>=visibleItems.Count)return;
            selectedIndex=visibleItems[position];var item=items[selectedIndex];
            if(detailName)detailName.text=item.displayName;
            if(detailDescription)detailDescription.text=item.description+(session?"\nOwned: "+Quantity(selectedIndex):"");
            if(detailIcon){detailIcon.sprite=item.icon;detailIcon.enabled=item.icon;}
            UpdateUse();onItemSelected.Invoke(item.itemId);
        }
        public void UseSelected(){if(session && selectedIndex>=0)session.UseItem(items[selectedIndex].itemId);}
        public void ChangePage(int delta){page+=delta;selectedIndex=-1;Refresh();FocusFirst();}
        void FocusFirst()
        {
            if(!EventSystem.current)return;
            var first=slots.FirstOrDefault(b=>b && b.interactable) ?? craftButtons.FirstOrDefault(b=>b && b.interactable);
            if(first)EventSystem.current.SetSelectedGameObject(first.gameObject);
        }
        public void SetHealth(float normalized) { if(healthFill)healthFill.fillAmount=Mathf.Clamp01(normalized); }
        public void SetSkillIcon(int index, Sprite icon) { if(index>=0 && index<icons.Length){icons[index].sprite=icon;icons[index].enabled=icon;} }
        public void ShowPanel(bool visible)
        {
            if(!panel)return;
            panel.SetActive(visible);
            if(visible){Refresh();FocusFirst();}
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
            if(session && Time.unscaledTime>=nextRefresh){nextRefresh=Time.unscaledTime+.2f;Refresh();}
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
