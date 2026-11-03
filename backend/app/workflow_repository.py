"""Workflow definitions on disk, one JSON file per workflow."""
from pathlib import Path

from pydantic import ValidationError

from .default_workflows import DEFAULT_WORKFLOWS
from .settings_store import DATA_DIR
from .workflow_models import Workflow


class LastWorkflow(Exception):
    """The last workflow cannot be removed: the engine always needs one."""


class WorkflowRepository:
    def __init__(self, folder: Path | None = None):
        self.folder = folder or DATA_DIR / "workflows"
        self.folder.mkdir(parents=True, exist_ok=True)
        if not any(self.folder.glob("*.json")):
            for workflow in DEFAULT_WORKFLOWS:
                self.save(workflow)

    def all(self) -> dict[str, Workflow]:
        workflows = {}
        for path in sorted(self.folder.glob("*.json")):
            try:
                workflow = Workflow.model_validate_json(path.read_text())
            except (OSError, ValidationError):
                continue  # A damaged file must not take the application down.
            workflows[workflow.id] = workflow
        return workflows

    def save(self, workflow: Workflow) -> None:
        (self.folder / f"{workflow.id}.json").write_text(workflow.model_dump_json(indent=2))

    def delete(self, workflow_id: str) -> None:
        if len(self.all()) <= 1:
            raise LastWorkflow
        (self.folder / f"{workflow_id}.json").unlink(missing_ok=True)
