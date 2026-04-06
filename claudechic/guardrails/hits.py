"""Hit logging — append-only JSONL audit trail for rule matches.

Leaf module — stdlib only, no claudechic imports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True)
class HitRecord:
    """A single rule hit — the audit unit."""

    rule_id: str  # Qualified: "project-team:pip_block"
    agent_role: str | None  # Role of the agent that triggered the hit
    tool_name: str  # e.g. "Bash", "Write"
    enforcement: str  # "deny", "warn", "log"
    timestamp: float  # time.time()
    outcome: str = ""  # "blocked", "allowed", "ack", "overridden"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "agent_role": self.agent_role,
            "tool_name": self.tool_name,
            "enforcement": self.enforcement,
            "timestamp": self.timestamp,
            "outcome": self.outcome,
        }


class HitLogger:
    """Append-only hit logger. Writes to JSONL file.

    Thread-safe for single-writer (the app process). Each line is
    a JSON object — one hit per line. File is opened in append mode
    and flushed after each write for crash safety.
    """

    def __init__(self, hits_path: Path) -> None:
        self._path = hits_path
        self._file: TextIO | None = None

    def record(self, hit: HitRecord) -> None:
        """Append a hit record to the log file."""
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._path.open("a", encoding="utf-8")
        self._file.write(json.dumps(hit.to_dict()) + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
