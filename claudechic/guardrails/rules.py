"""Minimal rule loader for SDK guardrail hooks.

Parses .claude/guardrails/rules.yaml into Rule objects and provides
matching functions for PreToolUse hook evaluation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Rule:
    """A single guardrail rule parsed from rules.yaml."""

    id: str
    name: str
    trigger: list[str]  # e.g. ["PreToolUse/Bash"] or ["PreToolUse/Write", "PreToolUse/Edit"]
    enforcement: str  # "deny" | "warn" | "log" | "user_confirm"
    detect_pattern: re.Pattern[str] | None = None
    detect_field: str = "command"  # which tool_input field to match against
    exclude_pattern: re.Pattern[str] | None = None
    message: str = ""
    block_roles: list[str] = field(default_factory=list)
    allow_roles: list[str] = field(default_factory=list)
    phase_block: list[str] = field(default_factory=list)
    phase_allow: list[str] = field(default_factory=list)


def load_rules(rules_path: Path) -> list[Rule]:
    """Parse rules.yaml into Rule objects. Returns empty list if file missing."""
    if not rules_path.is_file():
        return []

    with rules_path.open() as f:
        data = yaml.safe_load(f)

    if not data or "rules" not in data:
        return []

    rules: list[Rule] = []
    for entry in data["rules"]:
        # Parse trigger — can be string or list
        raw_trigger = entry.get("trigger", "")
        if isinstance(raw_trigger, str):
            triggers = [raw_trigger]
        else:
            triggers = list(raw_trigger)

        # Parse detect pattern
        detect = entry.get("detect", {})
        detect_pattern = None
        detect_field = "command"
        if detect:
            pattern_str = detect.get("pattern", "")
            if pattern_str:
                detect_pattern = re.compile(pattern_str)
            detect_field = detect.get("field", "command")

        # Parse exclude pattern
        exclude_pattern = None
        exclude_str = entry.get("exclude_if_matches", "")
        if exclude_str:
            exclude_pattern = re.compile(exclude_str)

        # Parse role restrictions
        block_roles = entry.get("block", [])
        if isinstance(block_roles, str):
            block_roles = [block_roles]
        allow_roles = entry.get("allow", [])
        if isinstance(allow_roles, str):
            allow_roles = [allow_roles]

        # Parse phase restrictions
        phase_block = entry.get("phase_block", [])
        if isinstance(phase_block, str):
            phase_block = [phase_block]
        phase_allow = entry.get("phase_allow", [])
        if isinstance(phase_allow, str):
            phase_allow = [phase_allow]

        rules.append(
            Rule(
                id=entry.get("id", ""),
                name=entry.get("name", ""),
                trigger=triggers,
                enforcement=entry.get("enforcement", "deny"),
                detect_pattern=detect_pattern,
                detect_field=detect_field,
                exclude_pattern=exclude_pattern,
                message=entry.get("message", ""),
                block_roles=block_roles,
                allow_roles=allow_roles,
                phase_block=phase_block,
                phase_allow=phase_allow,
            )
        )

    return rules


def matches_trigger(rule: Rule, tool_name: str) -> bool:
    """Check if rule's trigger matches the tool event.

    Trigger format: "PreToolUse/Bash" — we extract the tool name part after '/'.
    """
    for trigger in rule.trigger:
        parts = trigger.split("/", 1)
        if len(parts) == 2:
            trigger_tool = parts[1]
            if trigger_tool == tool_name:
                return True
        elif len(parts) == 1:
            # Bare trigger like "PreToolUse" matches all tools
            if parts[0] == "PreToolUse":
                return True
    return False


def match_rule(rule: Rule, tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Check exclude pattern first, then detect pattern.

    Returns True if the rule matches (i.e., should fire).
    """
    if rule.detect_pattern is None:
        # No detect pattern = always matches (after trigger check)
        return True

    # Get the field to match against
    text = tool_input.get(rule.detect_field, "")
    if not isinstance(text, str):
        text = str(text)

    # Check exclude first — if exclude matches, rule does NOT fire
    if rule.exclude_pattern and rule.exclude_pattern.search(text):
        return False

    # Check detect pattern
    return bool(rule.detect_pattern.search(text))


def should_skip_for_role(rule: Rule, agent_role: str | None) -> bool:
    """Return True if the rule should be skipped for this agent role.

    - block_roles: rule only fires for these roles (skip if role not in list)
    - allow_roles: rule never fires for these roles (skip if role in list)
    """
    if rule.block_roles:
        # Rule only applies to specific roles
        if agent_role is None or agent_role not in rule.block_roles:
            return True
    if rule.allow_roles:
        # Rule is skipped for allowed roles
        if agent_role and agent_role in rule.allow_roles:
            return True
    return False


def should_skip_for_phase(rule: Rule, phase_state: dict[str, Any] | None) -> bool:
    """Return True if rule should be skipped based on current phase.

    Phase state is read from .claude/guardrails/phase_state.json.
    """
    if not rule.phase_block and not rule.phase_allow:
        return False  # No phase restrictions

    if phase_state is None:
        return False  # No phase info = don't skip

    current_phase = phase_state.get("current_phase", "")
    if not current_phase:
        return False

    if rule.phase_block and current_phase in rule.phase_block:
        return True  # Skip: blocked in this phase
    if rule.phase_allow and current_phase not in rule.phase_allow:
        return True  # Skip: not in allowed phase

    return False


def read_phase_state(phase_state_path: Path) -> dict[str, Any] | None:
    """Read phase state from JSON file. Returns None if missing."""
    if not phase_state_path.is_file():
        return None
    try:
        with phase_state_path.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
