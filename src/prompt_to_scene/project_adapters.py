"""Inspect selected native systems, prepare a concrete adapter, then compile and bind."""

import json
import time
import uuid

from . import background, core, creations, development, game_art, registry, workflow


def inspect_system(project, flow_id):
    """Inspect selected scene components/actors and public adapter contracts.

    Select the inventory/health provider in the engine first. Compatible existing adapters
    can be bound directly. Unity can generate a typed forwarding component for a public
    atomic transaction API. UE reports Blueprint interface contracts and an editable starter.
    """
    return development.request(
        project,
        "adapter_wizard",
        mode="inspect",
        content_json=json.dumps(dict(flow_id=core.asset_id(flow_id))),
    )


def prepare(project, inspection_id, target, mapping=None):
    """Prepare a reviewed mapping from an actual inspection result, without editing game code.

    Unity mapping keys: quantity (int Method(string)), health and max_health (float fields
    or properties), commit (bool Method(ItemQuantity[], ItemQuantity[], float)). The commit
    method must perform one atomic transaction. Compatible native adapters need no mapping.
    Missing APIs are returned as questions; no private fields or transaction semantics are guessed.
    """
    result = workflow.job_status(project, workflow.identifier(inspection_id))
    if result.get("status") != "completed":
        raise ValueError("Wait for system inspection to finish")
    scan = json.loads(result["development"]["plan_json"])
    provider = next((r for r in scan["providers"] if r["target"] == target), None)
    if not provider:
        raise ValueError("Choose a provider returned by this inspection")
    mapping = mapping or {}
    if not isinstance(mapping, dict) or mapping.keys() - {
        "quantity",
        "health",
        "max_health",
        "commit",
    }:
        raise ValueError("Use quantity, health, max_health and commit mappings")
    questions = []
    if not provider["compatible"]:
        if registry.resolve(project).engine == "unreal":
            questions.append(
                "为所选 Actor 实现 BPI_PTSProjectAdapter 的 ReadQuantity、ReadHealth "
                "和原子 CommitGameplay，再重新扫描；"
                "可用 create_adapter_starter 生成可编辑蓝图。"
            )
        else:
            for key in ("quantity", "health", "max_health", "commit"):
                choices = provider.get(key, [])
                if key not in mapping and len(choices) == 1:
                    mapping[key] = choices[0]
                if mapping.get(key) not in choices:
                    questions.append(
                        f"选择 {key} 的公开接口，或在游戏组件中提供所需接口；"
                        f"候选：{', '.join(choices) or '无'}"
                    )
    row = dict(
        adapter_id=uuid.uuid4().hex,
        engine=registry.resolve(project).engine,
        flow_id=scan["flow_id"],
        provider=provider,
        mapping=mapping,
        questions=questions,
        status="needs_input" if questions else "ready",
    )
    core.atomic_json(
        game_art.root(project) / "project-adapters" / (row["adapter_id"] + ".json"), row
    )
    return row


def catalog(project):
    """List adapter plans and actual install/binding receipts."""
    return {
        "adapters": [
            core.read_optional_json(p)
            for p in sorted((game_art.root(project) / "project-adapters").glob("*.json"))
        ]
    }


def starter(project, name="ProjectGameplayAdapter"):
    """Create an editable native adapter starter, with atomic transaction examples and no binding.

    UE duplicates the engine-only Blueprint example in the project. Unity writes a compilable
    component scaffold. Fill the project's actual API calls, then inspect/prepare/install it.
    Existing game classes and assets are never replaced by the starter.
    """
    import re

    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", name):
        raise ValueError("Use a short class name containing letters and digits")
    return development.request(
        project, "adapter_wizard", mode="starter", content_json=json.dumps(dict(name=name))
    )


def install(project, adapter_id):
    """Install a complete mapping, wait for compilation, and bind it to the gameplay flow."""
    path = game_art.root(project) / "project-adapters" / (workflow.identifier(adapter_id) + ".json")
    with background.lock(path):
        row = core.read_optional_json(path)
        if not row or row["questions"]:
            raise ValueError("Resolve the adapter plan's missing interfaces before installation")
        if row.get("task"):
            return workflow.job_status(project, row["task"]["request_id"])
        row["task"] = background.submit(project, "project_adapter", dict(adapter_id=adapter_id))
        core.atomic_json(path, row)
        return row["task"]


def run(job, adapter_id):
    path = game_art.root(job.project) / "project-adapters" / (adapter_id + ".json")
    row = core.read_optional_json(path)
    payload = json.dumps(row)
    if not row["provider"]["compatible"]:
        job.update(stage="Generating typed project adapter")
        creations.step(
            job,
            "install_task",
            lambda: development.request(
                job.project, "adapter_wizard", mode="install", content_json=payload
            ),
        )
    if not row["provider"]["compatible"] and not job.state.get("compiler_ready"):
        deadline = time.monotonic() + 120
        while True:
            job.check()
            task = job.wait(
                development.request(
                    job.project, "adapter_wizard", mode="ready", content_json=payload
                )
            )
            status = json.loads(task["development"]["plan_json"])
            if status.get("ready"):
                job.update(compiler_ready=True)
                break
            if status.get("compilation_failed"):
                raise ValueError(
                    "Unity compilation failed; resolve Console errors then resume this task"
                )
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "Waiting for adapter compilation; resume after Unity finishes importing"
                )
            job.update(stage="Unity is compiling the generated adapter")
            time.sleep(1)
    job.update(stage="Waiting for compilation and binding the project system")
    bound = creations.step(
        job,
        "bind_task",
        lambda: development.request(
            job.project, "adapter_wizard", mode="bind", content_json=payload
        ),
    )
    with background.lock(path):
        current = core.read_optional_json(path)
        current.update(status="bound", binding=bound["development"], owns_external_save=False)
        core.atomic_json(path, current)
    return dict(
        stage="Project system adapter bound", adapter_id=adapter_id, binding=bound["development"]
    )
