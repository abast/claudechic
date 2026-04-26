"""Centralized path constants and helpers.

Pure functions — no UI or agent dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKFLOW_LIBRARY_ROOT = Path.home() / ".claudechic" / "workflow_library"


def compute_state_dir(workflow_root: Path, project_name: str) -> Path:
    """Compute the workflow state directory for a project.

    Uses the same lossy encoding as ``sessions.py`` (replace path
    separators with dashes, strip colons/underscores/dots) to derive
    a ``project_key`` from *workflow_root*.

    Returns ``~/.claudechic/workflow_library/{project_key}/{project_name}/``.
    """
    project_key = (
        str(workflow_root.absolute())
        .replace(os.sep, "-")
        .replace(":", "")
        .replace("_", "-")
        .replace(".", "-")
    )
    return WORKFLOW_LIBRARY_ROOT / project_key / project_name
