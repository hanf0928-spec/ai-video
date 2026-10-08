
"""ComfyUI workflow JSON template loader + variable substitution."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..core.config import settings
from ..core.exceptions import ComfyUIError


WORKFLOW_ROOT = settings.ROOT / "workflows"


def load_workflow(relative_path: str) -> dict:
    """Load a workflow json from the workflows/ folder."""
    p = WORKFLOW_ROOT / relative_path
    if not p.exists():
        raise ComfyUIError(f"workflow not found: {relative_path}")
    return json.loads(p.read_text(encoding="utf-8"))


def substitute(workflow: dict, variables: dict[str, Any]) -> dict:
    """Replace `${var}` placeholders in all string fields of a workflow."""
    wf = copy.deepcopy(workflow)

    def _walk(node: Any):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                node[k] = _walk(v)
            return node
        if isinstance(node, list):
            return [_walk(x) for x in node]
        if isinstance(node, str):
            s = node
            for key, val in variables.items():
                token = "${" + key + "}"
                if token in s:
                    s = s.replace(token, str(val))
            return s
        return node

    return _walk(wf)


def list_workflows() -> list[str]:
    """List all workflow json files recursively."""
    files = []
    for p in WORKFLOW_ROOT.rglob("*.json"):
        files.append(str(p.relative_to(WORKFLOW_ROOT)))
    return files


def save_workflow(relative_path: str, workflow: dict) -> Path:
    p = WORKFLOW_ROOT / relative_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
