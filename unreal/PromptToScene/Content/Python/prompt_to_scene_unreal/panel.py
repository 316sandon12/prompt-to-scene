"""Native Editor Utility Widget and Content Browser actions; no third-party UI runtime."""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import unreal

from .protocol import write_json

_widget = None
_pending = None
_task = None
_purpose = None
_reference = ""
_next = 0
_last_service = 0
_handle = None
_process = None
_textures = []
_last_status = None


def root():
    return Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"


def prefs():
    path = root() / "panel-prefs.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def text(value):
    global _last_status
    if value == _last_status:
        return
    _last_status = value
    unreal.log("[Prompt-to-Scene] " + value)
    if _widget:
        _widget.get_editor_property("Status").set_text(value)


def ensure_service():
    global _last_service, _process
    if time.monotonic() - _last_service < 15:
        return
    _last_service = time.monotonic()
    launcher = root() / "launcher.json"
    stamp = root() / "panel-service/heartbeat.json"
    if not launcher.is_file() or (stamp.is_file() and time.time() - stamp.stat().st_mtime < 30):
        return
    if _process is not None and _process.poll() is None:
        return
    config = json.loads(launcher.read_text())
    environment = dict(os.environ, PTS_HOME=config["home"], PYINSTALLER_RESET_ENVIRONMENT="1")
    command = [config["command"], *config["args"], "--editor-service", config["project"]]
    with (root() / "panel-service.log").open("a") as log:
        _process = subprocess.Popen(
            command,
            cwd=str(root().parent),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            **(
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            ),
        )


def selected():
    return list(
        dict.fromkeys(
            str(a.get_path_name()).split(".")[0]
            for a in unreal.EditorUtilityLibrary.get_selected_assets()
        )
    )


def send(action, values=None):
    global _pending, _purpose
    if _pending or _task:
        text("A task is running. Wait or cancel it first.")
        return
    if not (root() / "launcher.json").is_file():
        text("Connect this project in the Prompt-to-Scene app first.")
        return
    ensure_service()
    _purpose = action
    _pending = uuid.uuid4().hex
    write_json(
        root() / "panel-requests" / (_pending + ".json"), dict(action=action, values=values or {})
    )
    text("Working…")


def button(action):
    global _reference, _task
    try:
        paths = selected()
        saved = prefs()
        if action == "reference":
            if not paths:
                raise ValueError("Select a material or static mesh first")
            _reference = paths[0]
            text("Reference: " + _reference)
        elif action == "adapt_preview":
            send(
                "adaptation",
                dict(paths=[p for p in paths if p != _reference], reference=_reference),
            )
        elif action in {"adapt_apply", "adapt_undo"}:
            selected_slots = (
                str(_widget.get_editor_property("SelectedSlots").get_text()).strip()
                if _widget
                else ""
            )
            send(
                "adaptation",
                dict(
                    mode=action.removeprefix("adapt_"),
                    plan_id=saved.get("adaptation"),
                    selected=[s.strip() for s in selected_slots.split(",") if s.strip()] or None,
                ),
            )
        elif action in {"organize_apply", "organize_undo"}:
            send(
                "organize",
                dict(mode=action.removeprefix("organize_"), plan_id=saved.get("organization")),
            )
        elif action in {"organize_selected", "inspect_selected", "semantic"}:
            send(action, {"paths": paths})
        elif action == "intake":
            send("intake", {"mode": "scan"})
        elif action == "cancel":
            value = _task
            _task = None
            if value:
                send("cancel", {"request_id": value})
        elif action == "defaults":
            path = root().parent / "prompt-to-scene.json"
            data = json.loads(path.read_text()) if path.is_file() else {}
            enabled = not data.get("intake", {}).get("enabled", False)
            send("profile", {"mode": "save", "settings": {"intake": {"enabled": enabled}}})
        elif action == "inbox":
            path = root().parent / "prompt-to-scene.json"
            data = json.loads(path.read_text()) if path.is_file() else {}
            folder = (root().parent / data.get("intake", {}).get("folder", "AssetInbox")).resolve()
            if not folder.is_relative_to(root().parent):
                raise ValueError("Inbox must stay inside this project")
            folder.mkdir(parents=True, exist_ok=True)
            unreal.SystemLibrary.launch_url(folder.as_uri())
        elif action == "preview_assets":
            plan_id = saved.get("adaptation")
            if plan_id:
                plan = json.loads((root() / "adaptation" / (plan_id + ".json")).read_text())
                unreal.EditorAssetLibrary.sync_browser_to_objects(
                    [a["variant"] for a in plan["assets"]]
                )
                for row in plan["assets"][:1]:
                    unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_asset(
                        unreal.load_asset(row["variant"])
                    )
        else:
            raise ValueError("Unknown panel button")
    except Exception as error:
        text(str(error))


def tick(_delta):
    global _next, _pending, _task
    if time.monotonic() < _next:
        return
    _next = time.monotonic() + 0.5
    if not (_pending or _task):
        return
    path = (
        root() / "panel-results" / (_pending + ".json")
        if _pending
        else root() / "jobs" / _task / "state.json"
    )
    if not path.is_file() and _task:
        path = root() / "action-receipts" / (_task + ".json")
    if not path.is_file():
        return
    value = json.loads(path.read_text())
    text(
        value.get("error")
        or value.get("message")
        or value.get("stage")
        or value.get("status")
        or "Done"
    )
    plan = value.get("plan_id") or value.get("development", {}).get("plan_id")
    if plan:
        saved = prefs()
        saved["organization" if _purpose in {"organize_selected", "organize"} else "adaptation"] = (
            plan
        )
        write_json(root() / "panel-prefs.json", saved)
    if _widget and value.get("status") == "completed":
        details = []
        if value.get("plan"):
            details = [
                row["source"] + " → " + row["destination"]
                for row in value["plan"]["entries"]
                if row["action"] == "move"
            ]
        elif value.get("kind") == "adaptation":
            details = [
                row["id"]
                + ": "
                + row["path"]
                + " / slot "
                + str(row["slot"])
                + " · "
                + ", ".join(row["fields"])
                for row in value.get("entries", [])
            ]
        elif value.get("entries"):
            details = [
                row["path"] + " · " + str(row.get("triangles", "?")) + " triangles"
                for row in value["entries"]
            ]
        elif value.get("results"):
            details = [row["path"] + " · evidence " + row["request_id"] for row in value["results"]]
        if details:
            _widget.get_editor_property("Details").set_text("\n".join(details[:40]))
        preview = value.get("previews", [])
        pictures = (
            [preview[0]["before"], preview[0]["after"]]
            if preview
            else [row["request_id"] for row in value.get("results", [])[:2]]
        )
        if pictures:
            _textures.clear()
            for widget_name, revision in zip(("BeforeImage", "AfterImage"), pictures):
                world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
                texture = unreal.RenderingLibrary.import_file_as_texture2d(
                    world, str(root() / "previews" / (revision + ".png"))
                )
                _textures.append(texture)
                _widget.get_editor_property(widget_name).set_brush_from_texture(texture, True)
                _widget.get_editor_property(widget_name).set_visibility(
                    unreal.SlateVisibility.VISIBLE
                )
                _widget.get_editor_property(widget_name.replace("Image", "Frame")).set_visibility(
                    unreal.SlateVisibility.VISIBLE
                )
    if _pending:
        _pending = None
        _task = value.get("request_id")
    if value.get("status") in {"completed", "imported", "error", "cancelled"} or not value.get(
        "request_id"
    ):
        _task = None


def open_panel():
    global _widget, _handle, _task, _purpose
    widget = unreal.load_asset("/PromptToScene/Templates/EUW_PTSWorkshop")
    if not widget:
        raise RuntimeError("Native workshop widget missing. Reinstall the bridge for UE 5.7.2.")
    _widget = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem).spawn_and_register_tab(
        widget
    )
    if _handle is None:
        _handle = unreal.register_slate_post_tick_callback(tick)
    text("Select assets in the Content Browser. Inspect, organize or preview a reference look.")
    if not _pending and not _task:
        for path in sorted(
            (root() / "jobs").glob("*/state.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:40]:
            state = json.loads(path.read_text())
            if state.get("kind") in {"adaptation", "semantic"}:
                _task, _purpose = state["request_id"], state["kind"]
                break


def register():
    menus = unreal.ToolMenus.get()
    for menu_name in ("LevelEditor.MainMenu.Tools", "ContentBrowser.AssetContextMenu"):
        menu = menus.extend_menu(menu_name)
        entry = unreal.ToolMenuEntry(
            name="PromptToSceneWorkshop", type=unreal.MultiBlockType.MENU_ENTRY
        )
        entry.set_label("Prompt-to-Scene Workshop")
        entry.set_tool_tip("Open the native project asset workshop")
        entry.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from prompt_to_scene_unreal import panel; panel.open_panel()",
        )
        menu.add_menu_entry("PromptToScene", entry)
    menus.refresh_all_widgets()
