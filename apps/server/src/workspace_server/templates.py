"""The worker prompts from `config/templates/workers`: how a model does the AI work the app
starts (a scheduled check, or one task now)."""

from __future__ import annotations

import os

from .settings import setting

FALLBACK_WORKER = (
    "You are {name}, a worker for the {workspace} Brain. Call get_due_tasks; claim one task at "
    "a time with claim_task; work from the packet; propose what it asks for with the tool its "
    "output contract names, passing the run_id; finish with complete_task. A person reviews "
    "every proposal; never publish or send anything yourself."
)
FALLBACK_RUN = (
    "You are working one task for the {workspace} Brain through its MCP tools. Call "
    "claim_task with task_id {task_id}; work from the packet; propose what it asks for with "
    "the tool its output contract names, passing the run_id; finish with complete_task. Never "
    "publish or send anything."
)


def find_templates_dir(explicit: str | None = None) -> str | None:
    candidates = [
        explicit,
        setting("TEMPLATES_DIR"),
        os.path.join(os.getcwd(), "config", "templates"),
    ]
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        here = os.path.dirname(here)
        candidates.append(os.path.join(here, "config", "templates"))
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return os.path.abspath(candidate)
    return None


class TemplateLibrary:
    def __init__(self, root: str | None) -> None:
        self.root = root

    def worker_prompt(self, name: str, workspace: str) -> str:
        """The scheduled check: take whatever is due."""
        template = self._worker_file("worker.md", FALLBACK_WORKER)
        return template.replace("{name}", name).replace("{workspace}", workspace)

    def run_prompt(self, workspace: str, task_id: str) -> str:
        """One task, now: for a run started from the workspace, or pasted into any client."""
        template = self._worker_file("run-task.md", FALLBACK_RUN)
        return template.replace("{workspace}", workspace).replace("{task_id}", task_id)

    def _worker_file(self, name: str, fallback: str) -> str:
        path = os.path.join(self.root, "workers", name) if self.root else ""
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        return fallback
