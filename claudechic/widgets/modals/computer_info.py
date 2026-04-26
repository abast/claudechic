"""Unified Info modal - system info + session diagnostics."""

from __future__ import annotations

import importlib.metadata
import json
import platform
from pathlib import Path

from claudechic.sessions import get_project_sessions_dir
from claudechic.widgets.modals.base import InfoModal, InfoSection


def _get_version(package: str) -> str:
    """Get package version or 'unknown' if not installed."""
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _read_last_compact_summary(jsonl_path: str) -> str | None:
    """Read the last compaction summary from a session JSONL file.

    After autocompaction, the SDK writes a user message with isCompactSummary=true.
    The summary text is in message.content (a string).
    """
    path = Path(jsonl_path)
    if not path.is_file():
        return None
    try:
        last_summary = None
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "isCompactSummary" not in line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("isCompactSummary"):
                    content = msg.get("message", {}).get("content", "")
                    if isinstance(content, str) and content:
                        last_summary = content
        return last_summary
    except OSError:
        return None


def _resolve_jsonl_path(session_id: str | None, cwd: Path | None) -> str:
    """Compute the JSONL file path for the current session."""
    if not session_id:
        return "(no active session)"
    sessions_dir = get_project_sessions_dir(cwd)
    if not sessions_dir:
        return "(sessions directory not found)"
    return str(sessions_dir / f"{session_id}.jsonl")


class ComputerInfoModal(InfoModal):
    """Unified modal showing system info and session diagnostics."""

    def __init__(
        self,
        cwd: str | Path | None = None,
        session_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._cwd = str(cwd) if cwd else "(unknown)"
        self._cwd_path = Path(cwd) if cwd else None
        self._session_id = session_id
        self._jsonl_path = _resolve_jsonl_path(session_id, self._cwd_path)
        self._compact_summary = _read_last_compact_summary(self._jsonl_path)

    def _get_title(self) -> str:
        return "Info"

    def _get_sections(self) -> list[InfoSection]:
        return [
            # System
            InfoSection(title="Host", content=platform.node()),
            InfoSection(
                title="OS",
                content=(
                    f"{platform.system()} {platform.release()} ({platform.machine()})"
                ),
            ),
            InfoSection(title="Python", content=platform.python_version()),
            InfoSection(title="SDK", content=_get_version("claude-code-sdk")),
            InfoSection(title="claudechic", content=_get_version("claudechic")),
            InfoSection(title="CWD", content=self._cwd),
            # Session
            InfoSection(title="Session JSONL", content=self._jsonl_path),
            InfoSection(
                title="Last Compaction",
                content=self._compact_summary or "",
                scrollable=True,
            ),
        ]
