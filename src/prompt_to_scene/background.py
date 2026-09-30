"""Durable multi-step workflows sharing normal task status and cancellation."""

import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import core, registry, workflow


def submit(project, kind, parameters, asset_id=None):
    if kind not in {"composition", "generation", "quality"}:
        raise ValueError("Unknown workflow")
    target = registry.resolve(project)
    root = core.state_root(target.root)
    revision = uuid.uuid4().hex
    folder = root / "jobs" / revision
    state = {
        "request_id": revision,
        "kind": kind,
        "asset_id": asset_id or kind + "_" + revision,
        "status": "building",
        "stage": "Starting " + kind,
        "children": [],
        "created_utc": workflow.now(),
    }
    core.atomic_json(
        folder / "spec.json",
        {
            "kind": kind,
            "project": str(target.project_file or target.root),
            "request_id": revision,
            "parameters": parameters,
        },
    )
    core.atomic_json(folder / "state.json", state)
    try:
        child = workflow.launch_worker(folder / "spec.json")
        core.atomic_json(folder / "process.json", {"pid": child.pid})
    except OSError as error:
        state.update(status="error", error=str(error))
        core.atomic_json(folder / "state.json", state)
        raise
    return state


class Job:
    def __init__(self, path):
        self.path = Path(path)
        self.spec = core.read_optional_json(self.path)
        self.project = self.spec["project"]
        self.root = core.state_root(registry.resolve(self.project).root)
        self.id = workflow.identifier(self.spec["request_id"])
        self.state = core.read_optional_json(self.path.with_name("state.json"))

    def check(self):
        if (self.root / "cancel" / self.id).exists():
            for child in self.state.get("children", []):
                workflow.cancel(self.project, child)
            raise InterruptedError("Workflow cancelled; completed assets remain available")

    def update(self, **values):
        self.state.update(values, updated_utc=workflow.now())
        core.atomic_json(self.path.with_name("state.json"), self.state)

    def track(self, task):
        self.update(
            children=list(dict.fromkeys([*self.state.get("children", []), task["request_id"]]))
        )
        return task

    def wait(self, task, timeout=1200):
        self.track(task)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check()
            result = workflow.job_status(self.project, task["request_id"])
            if result["status"] in workflow.TERMINAL:
                if result["status"] not in {"completed", "imported"}:
                    raise RuntimeError(result.get("error") or result["status"])
                return result
            time.sleep(0.3)
        raise TimeoutError(
            "Stage still pending. Open the editor, leave Play mode, then resume this workflow."
        )

    def action(self, operation, **kwargs):
        return self.wait(workflow.action(self.project, operation, **kwargs))


def run(path):
    from . import compositions, generation, quality

    job = Job(path)
    try:
        job.check()
        result = {
            "composition": compositions.run,
            "generation": generation.run,
            "quality": quality.run,
        }[job.spec["kind"]](job, **job.spec["parameters"])
        job.update(**result, status="completed", error=None, completed_utc=workflow.now())
    except Exception as error:
        job.update(
            status="cancelled" if isinstance(error, InterruptedError) else "error",
            error=str(error),
            completed_utc=workflow.now(),
        )


@contextmanager
def lock(path):
    gate = Path(path).with_name("mutation-lock")
    try:
        gate.mkdir()
    except FileExistsError as error:
        raise ValueError("Another client is updating this workflow; retry shortly") from error
    try:
        yield
    finally:
        gate.rmdir()


def resume(project, request_id):
    root = core.state_root(registry.resolve(project).root)
    path = root / "jobs" / workflow.identifier(request_id) / "spec.json"
    if not path.is_file() or not core.read_optional_json(path).get("kind"):
        raise ValueError("Choose a composition, generation or quality workflow")
    with lock(path):
        job = Job(path)
        current = workflow.job_status(project, request_id)
        if current["status"] not in {"error", "cancelled"}:
            return current
        marker = root / "cancel" / request_id
        marker.unlink(missing_ok=True)
        job.update(status="building", error=None, stage="Resuming saved workflow")
        try:
            child = workflow.launch_worker(path)
            core.atomic_json(path.with_name("process.json"), {"pid": child.pid})
        except OSError as error:
            job.update(status="error", error=str(error))
            raise
        return job.state
