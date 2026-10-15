using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using Object=UnityEngine.Object;

namespace PromptToScene.Editor
{
    [Serializable] public class ItemSpec
    {
        public int schema_version;
        public string item_id,revision,expected_revision,model_asset_id,model_revision,icon_asset_id,icon_revision,name,description;
        public string[] update_fields;
        public string item_path,pickup_path;
        public bool place_pickup=true;
    }
    [Serializable] public class UITheme
    { public string version,background,surface,accent,text,muted; public int font_size=22,spacing=12; }
    [Serializable] public class ScreenSpec
    {
        public int schema_version;
        public string screen_id,kind,revision,expected_revision,title,prefab_path;
        public string[] item_ids;
        public UITheme theme;
        public bool place,update_theme;
    }
    public static class GameCreations
    {
        static string Root=>AssetBridge.StateRoot;
        static void Id(string id){if(id==null || !Regex.IsMatch(id,"^[a-z][a-z0-9_-]{0,63}$"))throw new Exception("Invalid creation ID");}
        static void Revision(string id){if(id==null || !Regex.IsMatch(id,"^[a-f0-9]{32}$"))throw new Exception("Invalid creation revision");}
        static T Read<T>(string path) where T:class => File.Exists(path)?JsonUtility.FromJson<T>(File.ReadAllText(path)):null;
        static void Save(string path,object value){Directory.CreateDirectory(Path.GetDirectoryName(path));string tmp=path+".tmp";File.WriteAllText(tmp,JsonUtility.ToJson(value,true));if(File.Exists(path))File.Delete(path);File.Move(tmp,path);}
        static Color ColorOf(string value){if(!ColorUtility.TryParseHtmlString(value,out var c))throw new Exception("Invalid theme color");return c;}
        static void Folder(string path){Directory.CreateDirectory(Path.Combine(AssetBridge.ProjectRoot,path));AssetDatabase.Refresh();}
        static void Ownership(string path,bool owned){if(!owned && AssetDatabase.LoadMainAssetAtPath(path))throw new Exception("Creation destination contains an unowned asset: "+path);}
        public static DevelopmentResult Execute(DevelopmentCommand command)
        {
            if(command.command=="game_item")return Item(JsonUtility.FromJson<ItemSpec>(command.content_json));
            return Screen(JsonUtility.FromJson<ScreenSpec>(command.content_json));
        }
        static DevelopmentResult Item(ItemSpec s)
        {
            Id(s.item_id);Id(s.model_asset_id);Id(s.icon_asset_id);Revision(s.revision);
            if(s.schema_version!=1 || (s.update_fields??new string[0]).Any(x=>x!="name"&&x!="description"))throw new Exception("Invalid item spec");
            string record=Path.Combine(Root,"game-items",s.item_id+".json");var previous=Read<ItemSpec>(record);
            if(previous?.revision==s.revision)return Result("game_item",previous);
            if((previous?.revision??"")!=(s.expected_revision??""))throw new Exception("Item changed after submission");
            var modelReceipt=Read<AssetReceipt>(Path.Combine(Root,"receipts",s.model_asset_id+".json"));
            if(modelReceipt==null || modelReceipt.request_id!=s.model_revision || modelReceipt.status!="imported")throw new Exception("Model revision changed");
            var imageReceipt=Read<ImageAssetResult>(Path.Combine(Root,"image-receipts",s.icon_asset_id+".json"));
            if(imageReceipt==null || imageReceipt.revision!=s.icon_revision)throw new Exception("Icon revision changed");
            var model=AssetDatabase.LoadAssetAtPath<GameObject>(NativeLocations.Get(s.model_asset_id).Prefab);
            var icon=AssetDatabase.LoadAssetAtPath<Sprite>(imageReceipt.sprite_path);
            if(!model || !icon)throw new Exception("Native model or UI icon is unavailable");
            string folder="Assets/PromptToScene/Items/"+s.item_id;
            s.item_path=previous?.item_path??folder+"/Item.asset";s.pickup_path=previous?.pickup_path??folder+"/Pickup.prefab";
            Ownership(s.item_path,previous!=null);Ownership(s.pickup_path,previous!=null);Folder(folder);
            var item=AssetDatabase.LoadAssetAtPath<GameItem>(s.item_path);
            if(previous!=null && (!item || item.itemId!=s.item_id))throw new Exception("Restore the missing item asset before updating");
            bool fresh=!item;
            if(fresh){item=ScriptableObject.CreateInstance<GameItem>();item.itemId=s.item_id;AssetDatabase.CreateAsset(item,s.item_path);}
            Undo.RecordObject(item,"Update game item");
            if(fresh || (s.update_fields??new string[0]).Contains("name"))item.displayName=s.name;
            if(fresh || (s.update_fields??new string[0]).Contains("description"))item.description=s.description;
            item.icon=icon;item.model=model;
            var pickup=AssetDatabase.LoadAssetAtPath<GameObject>(s.pickup_path);
            var root=pickup?PrefabUtility.LoadPrefabContents(s.pickup_path):new GameObject(s.item_id+" pickup");
            try
            {
                var interaction=DevelopmentActions.Ensure<Interaction>(root);
                if(!pickup){interaction.template="pickup";interaction.interactionLabel=item.displayName;interaction.eventId=s.item_id;}
                var component=DevelopmentActions.Ensure<GameItemPickup>(root);component.item=item;
                var old=root.transform.Find("Model");
                if(!old || PrefabUtility.GetCorrespondingObjectFromSource(old.gameObject)!=model)
                {
                    if(old)Object.DestroyImmediate(old.gameObject);
                    var child=(GameObject)PrefabUtility.InstantiatePrefab(model,root.scene);child.name="Model";child.transform.SetParent(root.transform,false);
                    foreach(var other in child.GetComponentsInChildren<Interaction>(true))Object.DestroyImmediate(other);
                    foreach(var identity in child.GetComponentsInChildren<AssetIdentity>(true))identity.nestedPart=true;
                }
                foreach(var mesh in root.GetComponentsInChildren<MeshFilter>())if(mesh.sharedMesh && !mesh.GetComponent<Collider>())mesh.gameObject.AddComponent<BoxCollider>();
                item.pickup=PrefabUtility.SaveAsPrefabAsset(root,s.pickup_path);
            }
            finally{if(pickup)PrefabUtility.UnloadPrefabContents(root);else Object.DestroyImmediate(root);}
            if(s.place_pickup && !DevelopmentActions.Loaded<GameItemPickup>().Any(x=>x.item==item))
            {
                var instance=(GameObject)PrefabUtility.InstantiatePrefab(item.pickup);
                var source=DevelopmentActions.Loaded<AssetIdentity>().FirstOrDefault(x=>x.assetId==s.model_asset_id && !x.nestedPart);
                instance.transform.position=(source?source.transform.position:Vector3.zero)+Vector3.right*1.5f;
                Undo.RegisterCreatedObjectUndo(instance,"Place item pickup");EditorSceneManager.MarkSceneDirty(DevelopmentActions.Scene);
            }
            s.name=item.displayName;s.description=item.description;
            EditorUtility.SetDirty(item);AssetDatabase.SaveAssets();Save(record,s);
            Save(Path.Combine(Root,"game-item-history",s.item_id,s.revision+".json"),s);
            return Result("game_item",s);
        }
        static DevelopmentResult Result(string command,object value)=>new DevelopmentResult{command=command,passed=true,plan_json=JsonUtility.ToJson(value),message="Editable native creation ready"};
        static DevelopmentResult Screen(ScreenSpec s)
        {
            Id(s.screen_id);Revision(s.revision);
            if(s.schema_version!=1 || !new[]{"inventory","hud","pause"}.Contains(s.kind) || s.item_ids==null || s.item_ids.Length>(s.kind=="hud"?4:128))throw new Exception("Invalid UI spec");
            var colors=new[]{s.theme.background,s.theme.surface,s.theme.accent,s.theme.text,s.theme.muted}.Select(ColorOf).ToArray();
            if(s.theme.font_size<14 || s.theme.font_size>40 || s.theme.spacing<4 || s.theme.spacing>32)throw new Exception("Invalid theme metrics");
            string record=Path.Combine(Root,"game-screens",s.screen_id+".json");var previous=Read<ScreenSpec>(record);
            if(previous?.revision==s.revision)return Result("game_ui",previous);
            if((previous?.revision??"")!=(s.expected_revision??"") || (previous!=null && previous.kind!=s.kind))throw new Exception("UI changed after submission");
            var items=s.item_ids.Select(id=>{Id(id);var entry=Read<ItemSpec>(Path.Combine(Root,"game-items",id+".json"));var item=entry!=null?AssetDatabase.LoadAssetAtPath<GameItem>(entry.item_path):null;if(!item)throw new Exception("Missing linked game item: "+id);return item;}).ToArray();
            string folder="Assets/PromptToScene/UI/"+s.screen_id;s.prefab_path=previous?.prefab_path??folder+"/Screen.prefab";
            Ownership(s.prefab_path,previous!=null);Folder(folder);
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(s.prefab_path);
            if(previous!=null && !prefab)throw new Exception("Restore the missing UI before updating");
            var root=prefab?PrefabUtility.LoadPrefabContents(s.prefab_path):Build(s);
            try
            {
                var screen=root.GetComponent<GameUIScreen>();
                if(!screen || screen.screenId!=s.screen_id)throw new Exception("UI ownership mismatch");
                EnsureGameplayControls(root,s.theme);
                screen.items=items;screen.Refresh();
                if(s.update_theme && prefab)ApplyTheme(root,s.theme);
                var title=screen.panel.transform.Find("Title");if(title && title.GetComponent<Text>())s.title=title.GetComponent<Text>().text;
                PrefabUtility.SaveAsPrefabAsset(root,s.prefab_path);
            }
            finally{if(prefab)PrefabUtility.UnloadPrefabContents(root);else Object.DestroyImmediate(root);}
            if(s.place)
            {
                if(!DevelopmentActions.Loaded<GameUIScreen>().Any(x=>x.screenId==s.screen_id))
                {var instance=(GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(s.prefab_path));Undo.RegisterCreatedObjectUndo(instance,"Place game UI");}
                if(!DevelopmentActions.Loaded<EventSystem>().Any())
                {
                    var events=new GameObject("Prompt-to-Scene UI Input",typeof(EventSystem));
#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
                    var module=Type.GetType("UnityEngine.InputSystem.UI.InputSystemUIInputModule, Unity.InputSystem");
                    if(module!=null){var component=events.AddComponent(module);module.GetMethod("AssignDefaultActions")?.Invoke(component,null);}
#else
                    events.AddComponent<StandaloneInputModule>();
#endif
                    Undo.RegisterCreatedObjectUndo(events,"Create UI input");
                }
                EditorSceneManager.MarkSceneDirty(DevelopmentActions.Scene);
            }
            AssetDatabase.SaveAssets();Save(record,s);Save(Path.Combine(Root,"game-screen-history",s.screen_id,s.revision+".json"),s);
            return Result("game_ui",s);
        }
        static RectTransform Rect(string name,Transform parent,Vector2 min,Vector2 max,Vector2 inset)
        {
            var obj=new GameObject(name,typeof(RectTransform));obj.layer=5;var r=obj.GetComponent<RectTransform>();r.SetParent(parent,false);
            r.anchorMin=min;r.anchorMax=max;r.offsetMin=inset;r.offsetMax=-inset;return r;
        }
        static Text Label(string name,string text,Transform parent,Vector2 min,Vector2 max,int size,Color color)
        {
            var label=Rect(name,parent,min,max,Vector2.zero).gameObject.AddComponent<Text>();
            label.font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");label.fontSize=size;label.text=text;label.color=color;
            label.alignment=TextAnchor.MiddleLeft;label.horizontalOverflow=HorizontalWrapMode.Wrap;label.raycastTarget=false;return label;
        }
        static Image Picture(string name,Transform parent,Vector2 min,Vector2 max,Color color)
        {var image=Rect(name,parent,min,max,Vector2.zero).gameObject.AddComponent<Image>();image.color=color;return image;}
        static Button Button(string name,string text,Transform parent,Vector2 min,Vector2 max,UITheme theme)
        {
            var image=Picture(name,parent,min,max,ColorOf(theme.surface));var button=image.gameObject.AddComponent<Button>();
            button.targetGraphic=image;var colors=button.colors;colors.highlightedColor=ColorOf(theme.accent);colors.pressedColor=ColorOf(theme.accent)*.75f;button.colors=colors;
            var label=Label("Label",text,image.transform,Vector2.zero,Vector2.one,theme.font_size,ColorOf(theme.text));label.alignment=TextAnchor.MiddleCenter;return button;
        }
        public static GameObject Build(ScreenSpec s)
        {
            var root=new GameObject(s.screen_id,typeof(RectTransform),typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster),typeof(GameUIScreen));
            root.layer=5;root.GetComponent<Canvas>().renderMode=RenderMode.ScreenSpaceOverlay;
            var scaler=root.GetComponent<CanvasScaler>();scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;scaler.referenceResolution=new Vector2(1600,900);scaler.matchWidthOrHeight=.5f;
            var screen=root.GetComponent<GameUIScreen>();screen.screenId=s.screen_id;screen.kind=s.kind;
            var safe=Rect("SafeArea",root.transform,Vector2.zero,Vector2.one,Vector2.zero);
            var responsive=root.AddComponent<GameUIResponsive>();responsive.safeArea=safe;responsive.screen=screen;
            var background=Picture("Panel",safe,new Vector2(.08f,.08f),new Vector2(.92f,.92f),ColorOf(s.theme.background));screen.panel=background.gameObject;
            var p=background.transform;var theme=s.theme;
            Picture("Accent",p,new Vector2(0,.993f),Vector2.one,ColorOf(theme.accent));
            Label("Title",string.IsNullOrEmpty(s.title)?(s.kind=="inventory"?"SATCHEL":s.kind=="pause"?"PAUSED":"ADVENTURER"):s.title,p,new Vector2(.04f,.86f),new Vector2(.87f,.96f),theme.font_size+10,ColorOf(theme.text));
            var close=Button("Close","×",p,new Vector2(.91f,.88f),new Vector2(.97f,.97f),theme);UnityEventTools.AddPersistentListener(close.onClick,screen.Resume);
            if(s.kind=="inventory")
            {
                var grid=Rect("ItemGrid",p,new Vector2(.04f,.09f),new Vector2(.59f,.83f),Vector2.zero);
                responsive.grid=grid;
                var layout=grid.gameObject.AddComponent<GridLayoutGroup>();layout.constraint=GridLayoutGroup.Constraint.FixedColumnCount;layout.constraintCount=4;layout.cellSize=new Vector2(145,104);layout.spacing=Vector2.one*theme.spacing;grid.gameObject.AddComponent<ResponsiveItemGrid>();
                var slots=new List<Button>();var icons=new List<Image>();var counts=new List<Text>();
                for(int i=0;i<16;i++)
                {
                    var button=Button("Slot"+i,"",grid,Vector2.zero,Vector2.one,theme);slots.Add(button);
                    var icon=Picture("Icon",button.transform,new Vector2(.14f,.12f),new Vector2(.86f,.9f),Color.white);icon.preserveAspect=true;icon.raycastTarget=false;icons.Add(icon);
                    var count=Label("Count","",button.transform,new Vector2(.65f,0),new Vector2(.95f,.27f),18,ColorOf(theme.text));count.alignment=TextAnchor.MiddleRight;counts.Add(count);
                }
                screen.slots=slots.ToArray();screen.icons=icons.ToArray();screen.counts=counts.ToArray();
                screen.detailIcon=Picture("DetailIcon",p,new Vector2(.67f,.5f),new Vector2(.91f,.81f),Color.white);screen.detailIcon.preserveAspect=true;screen.detailIcon.enabled=false;
                screen.detailName=Label("DetailName","Select an item",p,new Vector2(.65f,.38f),new Vector2(.95f,.49f),theme.font_size+4,ColorOf(theme.accent));
                screen.detailDescription=Label("DetailDescription","A place for every discovery.",p,new Vector2(.65f,.13f),new Vector2(.95f,.37f),theme.font_size,ColorOf(theme.muted));screen.detailDescription.alignment=TextAnchor.UpperLeft;
            }
            else if(s.kind=="hud")
            {
                var r=background.rectTransform;r.anchorMin=new Vector2(.03f,.03f);r.anchorMax=new Vector2(.44f,.23f);
                close.gameObject.SetActive(false);
                Picture("HealthTrack",p,new Vector2(.05f,.55f),new Vector2(.95f,.68f),ColorOf(theme.surface));
                screen.healthFill=Picture("HealthFill",p,new Vector2(.05f,.55f),new Vector2(.95f,.68f),ColorOf(theme.accent));screen.healthFill.sprite=AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");screen.healthFill.type=Image.Type.Filled;screen.healthFill.fillMethod=Image.FillMethod.Horizontal;
                screen.icons=new Image[4];for(int i=0;i<4;i++){var icon=Picture("Skill"+i,p,new Vector2(.06f+i*.22f,.08f),new Vector2(.2f+i*.22f,.46f),Color.white);icon.preserveAspect=true;screen.icons[i]=icon;}
            }
            else
            {
                Label("PauseHint","Take a breath. Your journey will wait.",p,new Vector2(.12f,.59f),new Vector2(.88f,.76f),theme.font_size,ColorOf(theme.muted));
                var resume=Button("Resume","Resume",p,new Vector2(.25f,.37f),new Vector2(.75f,.51f),theme);UnityEventTools.AddPersistentListener(resume.onClick,screen.Resume);
                var settings=Button("Settings","Settings",p,new Vector2(.25f,.18f),new Vector2(.75f,.32f),theme);UnityEventTools.AddPersistentListener(settings.onClick,screen.Settings);
            }
            EnsureGameplayControls(root,theme);
            return root;
        }
        static void EnsureGameplayControls(GameObject root,UITheme theme)
        {
            var screen=root.GetComponent<GameUIScreen>();var p=screen.panel.transform;
            if(!screen.feedbackLabel)screen.feedbackLabel=Label("GameplayFeedback","",p,new Vector2(.04f,.005f),new Vector2(.96f,.06f),Mathf.Max(14,theme.font_size-4),ColorOf(theme.accent));
            if(screen.kind!="inventory" || screen.useButton)return;
            screen.useButton=Button("UseItem","Use",p,new Vector2(.65f,.08f),new Vector2(.95f,.17f),theme);
            screen.previousPageButton=Button("PreviousPage","‹",p,new Vector2(.04f,.06f),new Vector2(.12f,.13f),theme);
            screen.nextPageButton=Button("NextPage","›",p,new Vector2(.51f,.06f),new Vector2(.59f,.13f),theme);
            screen.pageLabel=Label("PageCount","1 / 1",p,new Vector2(.14f,.06f),new Vector2(.49f,.13f),theme.font_size,ColorOf(theme.muted));screen.pageLabel.alignment=TextAnchor.MiddleCenter;
            screen.emptyLabel=Label("EmptyInventory","Your satchel is empty. Collect materials to begin.",p,new Vector2(.09f,.4f),new Vector2(.55f,.65f),theme.font_size,ColorOf(theme.muted));screen.emptyLabel.alignment=TextAnchor.MiddleCenter;
            screen.craftToggle=Button("CraftTab","Craft",p,new Vector2(.72f,.87f),new Vector2(.89f,.96f),theme);
            screen.itemGrid=p.Find("ItemGrid")?.gameObject;
            var panel=Rect("CraftPanel",p,new Vector2(.04f,.14f),new Vector2(.59f,.83f),Vector2.zero);screen.craftPanel=panel.gameObject;
            var viewport=Rect("Viewport",panel,Vector2.zero,Vector2.one,Vector2.zero);viewport.gameObject.AddComponent<RectMask2D>();
            var scroll=panel.gameObject.AddComponent<ScrollRect>();scroll.viewport=viewport;scroll.horizontal=false;
            var content=Rect("Recipes",viewport,new Vector2(0,1),Vector2.one,Vector2.zero);content.pivot=new Vector2(.5f,1);screen.craftList=content;scroll.content=content;
            var layout=content.gameObject.AddComponent<VerticalLayoutGroup>();layout.spacing=8;layout.childControlHeight=true;layout.childForceExpandHeight=false;
            var fitter=content.gameObject.AddComponent<ContentSizeFitter>();fitter.verticalFit=ContentSizeFitter.FitMode.PreferredSize;
            var template=Button("RecipeTemplate","Craft",content,Vector2.zero,Vector2.one,theme);template.gameObject.AddComponent<LayoutElement>().preferredHeight=64;template.gameObject.SetActive(false);screen.craftButtonTemplate=template;
            panel.gameObject.SetActive(false);
        }
        static void ApplyTheme(GameObject root,UITheme theme)
        {
            foreach(var label in root.GetComponentsInChildren<Text>(true)){label.color=ColorOf(theme.text);label.fontSize=theme.font_size;}
            var screen=root.GetComponent<GameUIScreen>();screen.panel.GetComponent<Image>().color=ColorOf(theme.background);
            foreach(var button in root.GetComponentsInChildren<Button>(true))button.GetComponent<Image>().color=ColorOf(theme.surface);
            if(screen.healthFill)screen.healthFill.color=ColorOf(theme.accent);
        }
        [Serializable] class AssetReceipt { public string request_id,status; }
    }
}
