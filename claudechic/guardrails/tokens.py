"""One-time override tokens for warn/deny enforcement.

Leaf module — stdlib only, no claudechic imports.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class OverrideToken:
    """One-time authorization for a specific blocked action."""

    rule_id: str
    tool_name: str
    tool_input_hash: str
    enforcement: str = ""  # "warn" or "deny" — prevents cross-level bypass


def _hash_tool_input(tool_input: dict) -> str:
    """Deterministic hash of tool input for token matching."""
    try:
        canonical = json.dumps(tool_input, sort_keys=True)
    except (TypeError, ValueError):
        canonical = str(sorted(tool_input.items()))
    return hashlib.sha256(canonical.encode()).hexdigest()


class OverrideTokenStore:
    """One-time override tokens for warn/deny enforcement.

    Lifecycle: created at app init, lives for app lifetime.
    Independent of workflow engine existence.
    """

    def __init__(self) -> None:
        self._tokens: list[OverrideToken] = []

    def store(
        self,
        rule_id: str,
        tool_name: str,
        tool_input: dict,
        enforcement: str = "",
    ) -> None:
        """Store a one-time override token after acknowledgment or user approval.

        Args:
            enforcement: "warn" or "deny" — tags the token so a warn-level
                token cannot be consumed by a deny-level rule (prevents
                agents from bypassing user authority via acknowledge_warning).
        """
        self._tokens.append(
            OverrideToken(
                rule_id=rule_id,
                tool_name=tool_name,
                tool_input_hash=_hash_tool_input(tool_input),
                enforcement=enforcement,
            )
        )

    def consume(
        self,
        rule_id: str,
        tool_name: str,
        tool_input: dict,
        enforcement: str = "",
    ) -> bool:
        """Consume a one-time override token if one matches.

        Returns True if consumed. Token enforcement must match the
        requesting enforcement level — a warn token cannot satisfy
        a deny rule.
        """
        input_hash = _hash_tool_input(tool_input)
        for i, token in enumerate(self._tokens):
            if (
                token.rule_id == rule_id
                and token.tool_name == tool_name
                and token.tool_input_hash == input_hash
                and token.enforcement == enforcement
            ):
                self._tokens.pop(i)
                return True
        return False
