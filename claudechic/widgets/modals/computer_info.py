"""ComputerInfoModal - shows system info (host, OS, Python, SDK, CWD)."""

from __future__ import annotations

import importlib.metadata
import platform
from pathlib import Path

from claudechic.widgets.modals.base import InfoModal, InfoSection


def _get_version(package: str) -> str:
    """Get package version or 'unknown' if not installed."""
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


class ComputerInfoModal(InfoModal):
    """Modal showing system/environment information."""

    def __init__(self, cwd: str | Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cwd = str(cwd) if cwd else "(unknown)"

    def _get_title(self) -> str:
        return "System Info"

    def _get_sections(self) -> list[InfoSection]:
        return [
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
        ]
