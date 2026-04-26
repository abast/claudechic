"""Unit tests for WorkflowEngine -- phase context injection and advance lock."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from claudechic.checks.protocol import CheckDecl
from claudechic.paths import WORKFLOW_LIBRARY_ROOT, compute_state_dir
from claudechic.workflows.engine import (
    WorkflowEngine,
    WorkflowManifest,
)
from claudechic.workflows.phases import Phase

pytestmark = [pytest.mark.fast]


def _make_engine(
    phases: list[Phase] | None = None,
    confirm_callback: Any = None,
) -> WorkflowEngine:
    """Build a WorkflowEngine with sensible defaults for testing."""
    if phases is None:
        phases = [
            Phase(id="proj:design", namespace="proj", file="design.md"),
            Phase(id="proj:implement", namespace="proj", file="implement.md"),
            Phase(id="proj:deploy", namespace="proj", file="deploy.md"),
        ]
    manifest = WorkflowManifest(workflow_id="proj", phases=phases)
    persist = AsyncMock()
    cb = confirm_callback or AsyncMock(return_value=True)
    return WorkflowEngine(manifest, persist, cb)


async def test_engine_injects_phase_context():
    """_run_single_check for manual-confirm includes phase_id, phase_index, phase_total, check_id."""
    captured_ctx: dict[str, Any] | None = None

    async def capture_confirm(
        question: str, context: dict[str, Any] | None = None
    ) -> bool:
        nonlocal captured_ctx
        captured_ctx = context
        return True

    engine = _make_engine(confirm_callback=capture_confirm)
    assert engine.get_current_phase() == "proj:design"

    check_decl = CheckDecl(
        id="proj:design:advance:0",
        namespace="proj",
        type="manual-confirm",
        params={"question": "Ready to advance?"},
    )

    result = await engine._run_single_check(check_decl)
    assert result.passed is True
    assert captured_ctx is not None
    assert captured_ctx["phase_id"] == "proj:design"
    # phase_index is 1-based: design is index 0 in list, +1 = 1
    assert captured_ctx["phase_index"] == 1
    assert captured_ctx["phase_total"] == 3
    assert captured_ctx["check_id"] == "proj:design:advance:0"


async def test_advance_lock_prevents_concurrent():
    """Two concurrent attempt_phase_advance calls serialize (second waits for first)."""
    call_order: list[str] = []
    gate = asyncio.Event()

    async def slow_confirm(
        question: str, context: dict[str, Any] | None = None
    ) -> bool:
        call_order.append("enter")
        await gate.wait()
        call_order.append("exit")
        return True

    phases = [
        Phase(
            id="proj:design",
            namespace="proj",
            file="design.md",
            advance_checks=[
                CheckDecl(
                    id="proj:design:advance:0",
                    namespace="proj",
                    type="manual-confirm",
                    params={"question": "Advance?"},
                )
            ],
        ),
        Phase(id="proj:implement", namespace="proj", file="implement.md"),
        Phase(id="proj:deploy", namespace="proj", file="deploy.md"),
    ]
    engine = _make_engine(phases=phases, confirm_callback=slow_confirm)

    checks = engine.get_advance_checks_for("proj:design")

    # Launch two concurrent advance attempts
    task1 = asyncio.create_task(
        engine.attempt_phase_advance("proj", "proj:design", "proj:implement", checks)
    )
    # Give task1 time to acquire the lock
    await asyncio.sleep(0.05)

    # task2 should block on the lock
    task2 = asyncio.create_task(
        engine.attempt_phase_advance("proj", "proj:design", "proj:implement", checks)
    )
    await asyncio.sleep(0.05)

    # Only one "enter" so far (task1 holds the lock, task2 is waiting)
    assert call_order.count("enter") == 1, (
        f"Expected 1 enter before gate, got: {call_order}"
    )

    # Release the gate so task1 completes
    gate.set()
    result1 = await task1

    # task2 now gets the lock but phase already advanced, so it gets mismatch
    result2 = await task2

    assert result1.success is True
    assert result2.success is False
    assert "mismatch" in result2.reason.lower()


# ===========================================================================
# workflow_root pinning — advance_checks must resolve relative paths against
# the workflow root (typically the main agent's cwd), not the Python
# process's cwd. This is what unblocks phase transitions like
# specification -> implementation when advance_phase is called from a
# sub-agent whose process cwd differs from where files were written.
# ===========================================================================


async def test_workflow_root_pins_command_check_cwd(tmp_path, monkeypatch):
    """command-output-check runs in workflow_root, not process cwd."""
    # Create the expected file inside the workflow root.
    spec_dir = tmp_path / ".project_team" / "demo" / "specification"
    spec_dir.mkdir(parents=True)
    (spec_dir / "SPECIFICATION.md").write_text("spec", encoding="utf-8")

    # Intentionally run the process from a DIFFERENT directory so we can
    # prove the subprocess inherits the workflow_root, not cwd.
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    assert Path(os.getcwd()).resolve() == other.resolve()

    manifest = WorkflowManifest(
        workflow_id="proj",
        phases=[
            Phase(id="proj:specification", namespace="proj", file="spec.md"),
            Phase(id="proj:implementation", namespace="proj", file="impl.md"),
        ],
    )
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        workflow_root=tmp_path,
    )

    check_decl = CheckDecl(
        id="proj:specification:advance:0",
        namespace="proj",
        type="command-output-check",
        params={
            "command": "ls .project_team/*/specification/SPECIFICATION.md 2>/dev/null",
            "pattern": r"SPECIFICATION\.md",
        },
    )

    result = await engine._run_single_check(check_decl)
    assert result.passed is True, result.evidence


async def test_workflow_root_pins_file_exists_check(tmp_path, monkeypatch):
    """file-exists-check resolves relative paths against workflow_root."""
    target = tmp_path / ".project_team" / "demo" / "SPECIFICATION.md"
    target.parent.mkdir(parents=True)
    target.write_text("spec", encoding="utf-8")

    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        workflow_root=tmp_path,
    )

    check_decl = CheckDecl(
        id="proj:spec",
        namespace="proj",
        type="file-exists-check",
        params={"path": ".project_team/demo/SPECIFICATION.md"},
    )
    result = await engine._run_single_check(check_decl)
    assert result.passed is True, result.evidence


async def test_manifest_cwd_overrides_workflow_root(tmp_path):
    """Explicit `cwd` in the manifest wins over the engine's workflow_root."""
    # File lives only under `override_root`, NOT under workflow_root.
    override_root = tmp_path / "override"
    (override_root / "subdir").mkdir(parents=True)
    (override_root / "subdir" / "marker.txt").write_text("hi", encoding="utf-8")

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        workflow_root=tmp_path,  # deliberately the wrong root
    )

    check_decl = CheckDecl(
        id="proj:spec",
        namespace="proj",
        type="command-output-check",
        params={
            "command": "ls subdir/marker.txt 2>/dev/null",
            "pattern": r"marker\.txt",
            "cwd": str(override_root),  # manifest override
        },
    )
    result = await engine._run_single_check(check_decl)
    assert result.passed is True, result.evidence


# ===========================================================================
# state_dir expansion — $STATE_DIR in check params is expanded to the
# engine's state_dir absolute path before check execution.
# ===========================================================================


async def test_state_dir_expands_in_command_check(tmp_path):
    """$STATE_DIR in command-output-check params expands to state_dir path."""
    state = tmp_path / "state"
    spec_dir = state / "specification"
    spec_dir.mkdir(parents=True)
    (spec_dir / "SPEC.md").write_text("spec content", encoding="utf-8")

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        state_dir=state,
    )

    check_decl = CheckDecl(
        id="proj:spec-check",
        namespace="proj",
        type="command-output-check",
        params={
            "command": "ls $STATE_DIR/specification/SPEC.md",
            "pattern": r"SPEC\.md",
        },
    )
    result = await engine._run_single_check(check_decl)
    assert result.passed is True, result.evidence


async def test_state_dir_expands_in_file_exists_check(tmp_path):
    """$STATE_DIR in file-exists-check path param expands to state_dir."""
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "STATUS.md").write_text("status", encoding="utf-8")

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        state_dir=state,
    )

    check_decl = CheckDecl(
        id="proj:status-check",
        namespace="proj",
        type="file-exists-check",
        params={"path": "$STATE_DIR/STATUS.md"},
    )
    result = await engine._run_single_check(check_decl)
    assert result.passed is True, result.evidence


async def test_state_dir_and_workflow_root_independent(tmp_path, monkeypatch):
    """state_dir and workflow_root resolve independently — no interference."""
    # Set up separate directories
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "artifact.txt").write_text("from state_dir", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "marker.txt").write_text("from workflow_root", encoding="utf-8")

    # Point process cwd somewhere else to prove neither leaks
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        workflow_root=repo,
        state_dir=state,
    )

    # $STATE_DIR resolves to state_dir
    state_check = CheckDecl(
        id="proj:state",
        namespace="proj",
        type="command-output-check",
        params={
            "command": "ls $STATE_DIR/artifact.txt",
            "pattern": r"artifact\.txt",
        },
    )
    result_state = await engine._run_single_check(state_check)
    assert result_state.passed is True, result_state.evidence

    # Relative path resolves via workflow_root (cwd pinning)
    root_check = CheckDecl(
        id="proj:root",
        namespace="proj",
        type="command-output-check",
        params={
            "command": "ls marker.txt",
            "pattern": r"marker\.txt",
        },
    )
    result_root = await engine._run_single_check(root_check)
    assert result_root.passed is True, result_root.evidence


def test_compute_state_dir(tmp_path):
    """compute_state_dir produces expected path with sessions.py-compatible encoding."""
    workflow_root = tmp_path / "my_project"
    workflow_root.mkdir()
    project_name = "demo"

    result = compute_state_dir(workflow_root, project_name)

    # Must live under WORKFLOW_LIBRARY_ROOT
    assert str(result).startswith(str(WORKFLOW_LIBRARY_ROOT))

    # Must end with project_name
    assert result.name == project_name

    # project_key encoding: same as sessions.py — replace os.sep with dash,
    # strip colons, replace underscores and dots with dashes
    expected_key = (
        str(workflow_root.absolute())
        .replace(os.sep, "-")
        .replace(":", "")
        .replace("_", "-")
        .replace(".", "-")
    )
    assert result.parent.name == expected_key
    assert result == WORKFLOW_LIBRARY_ROOT / expected_key / project_name


async def test_state_dir_none_skips_expansion(tmp_path, monkeypatch):
    """When state_dir is None, $STATE_DIR is left unexpanded (backward compat)."""
    monkeypatch.chdir(tmp_path)

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        state_dir=None,  # explicitly None
    )

    # A command containing $STATE_DIR — since state_dir is None, the literal
    # string "$STATE_DIR" is NOT expanded. The command will see it as-is,
    # which means `echo '$STATE_DIR/...'` preserves the variable literally.
    check_decl = CheckDecl(
        id="proj:noexpand",
        namespace="proj",
        type="command-output-check",
        params={
            "command": "echo '$STATE_DIR/should-stay-literal'",
            "pattern": r"\$STATE_DIR",
        },
    )
    result = await engine._run_single_check(check_decl)
    assert result.passed is True, (
        f"$STATE_DIR should remain literal when state_dir=None: {result.evidence}"
    )


# ===========================================================================
# Compositional correctness — expansion is uniform, mechanical, and
# independent of check type. See Composability guidance.
# ===========================================================================


async def test_state_dir_expansion_uniform_across_check_types(tmp_path):
    """$STATE_DIR expands identically in command, file-exists, and file-content checks."""
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "SPEC.md").write_text("# Specification\nversion: 1", encoding="utf-8")

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        state_dir=state,
    )

    # command-output-check
    r1 = await engine._run_single_check(
        CheckDecl(
            id="proj:cmd",
            namespace="proj",
            type="command-output-check",
            params={"command": "cat $STATE_DIR/SPEC.md", "pattern": "Specification"},
        )
    )
    assert r1.passed is True, f"command-output-check: {r1.evidence}"

    # file-exists-check
    r2 = await engine._run_single_check(
        CheckDecl(
            id="proj:exists",
            namespace="proj",
            type="file-exists-check",
            params={"path": "$STATE_DIR/SPEC.md"},
        )
    )
    assert r2.passed is True, f"file-exists-check: {r2.evidence}"

    # file-content-check
    r3 = await engine._run_single_check(
        CheckDecl(
            id="proj:content",
            namespace="proj",
            type="file-content-check",
            params={"path": "$STATE_DIR/SPEC.md", "pattern": r"version:\s+1"},
        )
    )
    assert r3.passed is True, f"file-content-check: {r3.evidence}"


async def test_absolute_path_after_expansion_unchanged(tmp_path):
    """$STATE_DIR expands to absolute path; file checks don't re-resolve it."""
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "data.txt").write_text("hello", encoding="utf-8")

    # workflow_root points somewhere ELSE — if the expanded absolute path
    # were re-resolved against workflow_root, the check would fail.
    other_root = tmp_path / "wrong_root"
    other_root.mkdir()

    manifest = WorkflowManifest(workflow_id="proj", phases=[])
    engine = WorkflowEngine(
        manifest=manifest,
        persist_fn=AsyncMock(),
        confirm_callback=AsyncMock(return_value=True),
        workflow_root=other_root,
        state_dir=state,
    )

    result = await engine._run_single_check(
        CheckDecl(
            id="proj:abs",
            namespace="proj",
            type="file-exists-check",
            params={"path": "$STATE_DIR/data.txt"},
        )
    )
    assert result.passed is True, (
        f"Absolute path from $STATE_DIR should not be re-resolved against workflow_root: {result.evidence}"
    )


def test_compute_state_dir_deterministic(tmp_path):
    """Same inputs always produce the same state_dir path."""
    root = tmp_path / "repo"
    root.mkdir()

    result1 = compute_state_dir(root, "myproject")
    result2 = compute_state_dir(root, "myproject")
    assert result1 == result2


def test_compute_state_dir_worktree_vs_main(tmp_path):
    """state_dir is derived from workflow_root, so worktree agents sharing
    the same original repo root get the same state_dir."""
    # Main repo and worktree have different filesystem paths, but the
    # caller is expected to pass the *original* repo root (not the worktree
    # path) so that all agents converge on the same state_dir.
    main_root = tmp_path / "repo"
    main_root.mkdir()

    # Both main and worktree agents pass the same workflow_root
    state_main = compute_state_dir(main_root, "team")
    state_worktree = compute_state_dir(main_root, "team")
    assert state_main == state_worktree

    # But a *different* root produces a different state_dir
    other_root = tmp_path / "other_repo"
    other_root.mkdir()
    state_other = compute_state_dir(other_root, "team")
    assert state_other != state_main


# ===========================================================================
# Two-pass check execution — automated checks run before manual confirms
# so users aren't prompted when an automated check will fail anyway.
# ===========================================================================


async def test_manual_confirm_runs_after_automated_checks(tmp_path, monkeypatch):
    """manual-confirm is NOT called when an automated check fails first.

    YAML order has manual-confirm BEFORE command-output-check, but the
    engine reorders so automated checks run first. The confirm callback
    must never be invoked.
    """
    monkeypatch.chdir(tmp_path)
    confirm_called = False

    async def track_confirm(
        question: str, context: dict[str, Any] | None = None
    ) -> bool:
        nonlocal confirm_called
        confirm_called = True
        return True

    # manual-confirm listed FIRST in YAML order, then a failing automated check
    checks = [
        CheckDecl(
            id="proj:design:advance:0",
            namespace="proj",
            type="manual-confirm",
            params={"question": "Ready to advance?"},
        ),
        CheckDecl(
            id="proj:design:advance:1",
            namespace="proj",
            type="command-output-check",
            params={
                "command": "echo 'no match here'",
                "pattern": r"THIS_WILL_NOT_MATCH",
            },
        ),
    ]

    phases = [
        Phase(
            id="proj:design",
            namespace="proj",
            file="design.md",
            advance_checks=checks,
        ),
        Phase(id="proj:implement", namespace="proj", file="implement.md"),
    ]
    engine = _make_engine(phases=phases, confirm_callback=track_confirm)

    result = await engine.attempt_phase_advance(
        "proj", "proj:design", "proj:implement", checks
    )

    assert result.success is False
    assert "advance:1" in result.failed_check_id
    assert confirm_called is False, (
        "manual-confirm should NOT be called when automated checks fail first"
    )
