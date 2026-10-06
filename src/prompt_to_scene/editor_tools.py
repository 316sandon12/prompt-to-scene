"""Local file IPC for native editor panels. Core work never blocks the editor thread."""

import json
import os
import re
import time

from . import (
    art_adaptation,
    background,
    clients,
    core,
    intake,
    organization,
    project_library,
    project_profiles,
    registry,
    semantics,
    workflow,
)


def install(target):
    command = clients.runtime()[:-1]
    root = core.state_root(target.root)
    core.atomic_json(
        root / "launcher.json",
        {
            "command": command[0],
            "args": command[1:],
            "project": str(target.project_file or target.root),
            "home": str(registry.home()),
        },
    )


def dispatch(project, action, values=None):
    values = values or {}
    if action == "organize_selected":
        paths = values.get("paths")
        if not paths:
            raise ValueError("Select project assets or folders first")
        for path in paths:
            organization.path_check(path, registry.resolve(project).engine, True)
        return background.submit(project, "editor", {"paths": paths, "mode": "plan"})
    if action == "inspect_selected":
        paths = values.get("paths")
        if not paths:
            raise ValueError("Select project models first")
        return background.submit(project, "editor", {"paths": paths, "mode": "inspect"})
    routes = {
        "profile": lambda: project_profiles.configure(project, **values),
        "intake": lambda: intake.manage(project, **values),
        "organize": lambda: organization.organize(project, **values),
        "semantic": lambda: semantics.start(project, **values),
        "adaptation": lambda: art_adaptation.start(project, **values),
        "task": lambda: workflow.job_status(project, values["request_id"]),
        "cancel": lambda: workflow.cancel(project, values["request_id"]),
    }
    if action not in routes:
        raise ValueError("Unknown native panel action")
    return routes[action]()


def run_job(job, paths, mode):
    if mode == "plan":
        task = job.state.get("scan_task")
        if not task:
            task = organization.organize(job.project, "scan")
            job.update(scan_task=task, stage="Scanning selected project assets")
        result = job.wait(task)
        plan = organization.organize(
            job.project,
            "plan",
            scan_id=result["development"]["scan_id"],
            settings={"include": paths},
        )
        return {
            "plan_id": plan["plan_id"],
            "summary": plan["summary"],
            "message": str(plan["summary"]["move"])
            + " assets can be organized. Review the plan, then apply.",
            "plan": plan,
        }
    result = job.wait(project_library.search(job.project))
    budget = project_profiles.read(job.project)["preparation"]["triangle_budget"]
    entries = [
        row
        for row in result["development"]["entries"]
        if any(row["path"] == p or row["path"].startswith(p + "/") for p in paths)
    ]
    issues = [
        {
            "path": row["path"],
            "issue": "Triangle budget exceeded",
            "triangles": row["triangles"],
            "budget": budget,
        }
        for row in entries
        if row.get("triangles", 0) > budget
    ]
    return {
        "entries": entries,
        "issues": issues,
        "message": str(len(entries))
        + " models inspected; "
        + str(len(issues))
        + " exceed the saved triangle budget.",
    }


def service(project):
    target = registry.resolve(project)
    root = core.state_root(target.root)
    os.environ["PTS_PROJECT"] = str(target.project_file or target.root)
    gate = root / "panel-service"
    gate.mkdir(exist_ok=True)
    # A separate OS lock allows a crashed process to be replaced immediately.
    with organization.annotation_lock(gate, nonblocking=True):
        requests = root / "panel-requests"
        requests.mkdir(exist_ok=True)
        last_scan = 0.0
        while True:
            heartbeat = root / "editor.json"
            if not heartbeat.is_file() or time.time() - heartbeat.stat().st_mtime > 90:
                return
            for path in sorted(requests.glob("*.json")):
                if (
                    not re.fullmatch(r"[a-f0-9]{32}", path.stem)
                    or path.is_symlink()
                    or path.stat().st_size > 64 * 1024
                ):
                    continue
                response = root / "panel-results" / path.name
                if response.exists():
                    path.unlink(missing_ok=True)
                    continue
                try:
                    request = json.loads(path.read_text(encoding="utf-8"))
                    result = dispatch(project, request["action"], request.get("values"))
                    result.setdefault("message", "Done")
                except Exception as error:
                    result = {"status": "error", "error": str(error)}
                core.atomic_json(response, result)
                path.unlink(missing_ok=True)
            if time.monotonic() - last_scan > 5:
                last_scan = time.monotonic()
                core.atomic_json(gate / "heartbeat.json", {"pid": os.getpid()})
                try:
                    if project_profiles.read(project)["intake"]["enabled"]:
                        result = intake.manage(project, "scan")
                        core.atomic_json(
                            root / "intake-watcher.json", {"updated_utc": workflow.now(), **result}
                        )
                except Exception as error:
                    core.atomic_json(
                        root / "intake-watcher.json",
                        {"error": str(error), "updated_utc": workflow.now()},
                    )
            time.sleep(0.25)
