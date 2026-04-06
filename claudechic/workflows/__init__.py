"""Workflow orchestration layer.

Public API for manifest loading, phase management, and workflow engine.
This is the orchestration layer — it imports from guardrails/, checks/, hints/.
"""

from __future__ import annotations

from claudechic.workflows.agent_folders import assemble_phase_prompt, create_post_compact_hook
from claudechic.workflows.engine import PhaseAdvanceResult, WorkflowEngine, WorkflowManifest
from claudechic.workflows.loader import LoadResult, ManifestLoader
from claudechic.workflows.phases import Phase

__all__ = [
    "LoadResult",
    "ManifestLoader",
    "Phase",
    "PhaseAdvanceResult",
    "WorkflowEngine",
    "WorkflowManifest",
    "assemble_phase_prompt",
    "create_post_compact_hook",
]
