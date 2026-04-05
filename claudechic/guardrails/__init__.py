"""SDK-based guardrail hook system — evaluates rules.yaml via PreToolUse hooks."""

from claudechic.guardrails.rules import (
    Rule,
    load_rules,
    matches_trigger,
    match_rule,
    should_skip_for_role,
    should_skip_for_phase,
)

__all__ = [
    "Rule",
    "load_rules",
    "matches_trigger",
    "match_rule",
    "should_skip_for_role",
    "should_skip_for_phase",
]
