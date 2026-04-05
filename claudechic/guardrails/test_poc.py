#!/usr/bin/env python3
"""PoC test for SDK guardrail hooks — proves mechanism works and measures timing."""

from __future__ import annotations

import time
from pathlib import Path

# Adjust path to find the rules module
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from claudechic.guardrails.rules import (
    Rule,
    load_rules,
    match_rule,
    matches_trigger,
    should_skip_for_role,
)

RULES_PATH = Path(__file__).resolve().parents[4] / ".claude/guardrails/rules.yaml"


def test_load_rules():
    """Test that rules.yaml loads correctly."""
    rules = load_rules(RULES_PATH)
    assert len(rules) > 0, f"No rules loaded from {RULES_PATH}"
    print(f"✓ Loaded {len(rules)} rules from {RULES_PATH}")
    for r in rules:
        print(f"  {r.id}: {r.name} ({r.enforcement}) triggers={r.trigger}")


def test_trigger_matching():
    """Test trigger matching logic."""
    rules = load_rules(RULES_PATH)

    # R01 should match Bash
    r01 = next(r for r in rules if r.id == "R01")
    assert matches_trigger(r01, "Bash"), "R01 should match Bash"
    assert not matches_trigger(r01, "Write"), "R01 should not match Write"

    # R05 should match both Write and Edit
    r05 = next(r for r in rules if r.id == "R05")
    assert matches_trigger(r05, "Write"), "R05 should match Write"
    assert matches_trigger(r05, "Edit"), "R05 should match Edit"
    assert not matches_trigger(r05, "Bash"), "R05 should not match Bash"

    print("✓ Trigger matching works correctly")


def test_detect_patterns():
    """Test detect pattern matching."""
    rules = load_rules(RULES_PATH)

    # R02: pip install should match
    r02 = next(r for r in rules if r.id == "R02")
    assert match_rule(r02, "Bash", {"command": "pip install requests"})
    assert match_rule(r02, "Bash", {"command": "pip3 install numpy"})
    # pixi run pip install should be excluded
    assert not match_rule(r02, "Bash", {"command": "pixi run pip install foo"})
    print("✓ R02 pip-install detection works")

    # R01: pytest should match
    r01 = next(r for r in rules if r.id == "R01")
    assert match_rule(r01, "Bash", {"command": "pytest"})
    assert match_rule(r01, "Bash", {"command": "pytest -v"})
    # pytest with redirect should be excluded
    assert not match_rule(r01, "Bash", {"command": "pytest > output.log"})
    # Single file test should be excluded
    assert not match_rule(r01, "Bash", {"command": "pytest tests/test_foo.py"})
    print("✓ R01 pytest detection works")

    # R03: conda install
    r03 = next(r for r in rules if r.id == "R03")
    assert match_rule(r03, "Bash", {"command": "conda install numpy"})
    assert match_rule(r03, "Bash", {"command": "mamba install numpy"})
    print("✓ R03 conda/mamba detection works")

    # R05: file_path field matching
    r05 = next(r for r in rules if r.id == "R05")
    assert match_rule(r05, "Write", {"file_path": ".claude/guardrails/rules.yaml"})
    assert not match_rule(r05, "Write", {"file_path": "src/main.py"})
    print("✓ R05 file_path field matching works")


def test_role_blocking():
    """Test role-based rule skipping."""
    rules = load_rules(RULES_PATH)

    # R04: only blocks Subagent role
    r04 = next(r for r in rules if r.id == "R04")
    assert not should_skip_for_role(r04, "Subagent"), "R04 should fire for Subagent"
    assert should_skip_for_role(r04, "Coordinator"), "R04 should skip for Coordinator"
    assert should_skip_for_role(r04, None), "R04 should skip when no role"

    # R01: no role restrictions — should never skip
    r01 = next(r for r in rules if r.id == "R01")
    assert not should_skip_for_role(r01, "Subagent"), "R01 has no role restriction"
    assert not should_skip_for_role(r01, None), "R01 has no role restriction"

    print("✓ Role-based filtering works correctly")


def test_timing():
    """Measure hook overhead per tool call."""
    # Warm up
    load_rules(RULES_PATH)

    iterations = 100
    timings: list[float] = []

    for _ in range(iterations):
        t0 = time.monotonic()

        rules = load_rules(RULES_PATH)
        for rule in rules:
            if not matches_trigger(rule, "Bash"):
                continue
            if should_skip_for_role(rule, None):
                continue
            match_rule(rule, "Bash", {"command": "echo hello"})

        elapsed = time.monotonic() - t0
        timings.append(elapsed * 1000)  # ms

    avg = sum(timings) / len(timings)
    p50 = sorted(timings)[len(timings) // 2]
    p99 = sorted(timings)[int(len(timings) * 0.99)]
    max_t = max(timings)

    print(f"\n📊 Timing ({iterations} iterations, Bash tool, no-match path):")
    print(f"  avg={avg:.2f}ms  p50={p50:.2f}ms  p99={p99:.2f}ms  max={max_t:.2f}ms")

    # Also measure a matching path
    match_timings: list[float] = []
    for _ in range(iterations):
        t0 = time.monotonic()

        rules = load_rules(RULES_PATH)
        for rule in rules:
            if not matches_trigger(rule, "Bash"):
                continue
            if should_skip_for_role(rule, None):
                continue
            if match_rule(rule, "Bash", {"command": "pip install requests"}):
                break

        elapsed = time.monotonic() - t0
        match_timings.append(elapsed * 1000)

    avg = sum(match_timings) / len(match_timings)
    p50 = sorted(match_timings)[len(match_timings) // 2]
    p99 = sorted(match_timings)[int(len(match_timings) * 0.99)]

    print(f"\n📊 Timing ({iterations} iterations, Bash tool, R02-match path):")
    print(f"  avg={avg:.2f}ms  p50={p50:.2f}ms  p99={p99:.2f}ms")

    assert avg < 20, f"Average overhead {avg:.2f}ms exceeds 20ms target"
    print("\n✓ Performance target met: < 20ms per hook evaluation")


def test_full_hook_simulation():
    """Simulate the full hook flow for each enforcement type."""
    rules = load_rules(RULES_PATH)
    print("\n🔄 Simulating full hook flow:")

    # Test deny: pip install should be blocked
    tool_input = {"command": "pip install requests"}
    for rule in rules:
        if not matches_trigger(rule, "Bash"):
            continue
        if should_skip_for_role(rule, None):
            continue
        if not match_rule(rule, "Bash", tool_input):
            continue
        assert rule.enforcement == "deny"
        assert rule.id == "R02"
        result = {"decision": "block", "reason": rule.message}
        print(f"  ✓ DENY: {rule.id} blocked 'pip install requests'")
        print(f"    → {result['reason'][:80]}...")
        break

    # Test allow: echo hello should pass all rules
    tool_input = {"command": "echo hello"}
    matched = False
    for rule in rules:
        if not matches_trigger(rule, "Bash"):
            continue
        if should_skip_for_role(rule, None):
            continue
        if match_rule(rule, "Bash", tool_input):
            matched = True
            break
    assert not matched, "echo hello should not match any rule"
    print("  ✓ ALLOW: 'echo hello' passed all rules (no match)")

    # Test role skip: git push as Coordinator should be allowed
    tool_input = {"command": "git push origin main"}
    for rule in rules:
        if not matches_trigger(rule, "Bash"):
            continue
        if should_skip_for_role(rule, "Coordinator"):
            continue
        if match_rule(rule, "Bash", tool_input):
            assert False, "git push by Coordinator should be allowed (R04 only blocks Subagent)"
    print("  ✓ ALLOW: 'git push' as Coordinator (R04 skipped)")

    # Test role block: git push as Subagent should be blocked
    tool_input = {"command": "git push origin main"}
    blocked = False
    for rule in rules:
        if not matches_trigger(rule, "Bash"):
            continue
        if should_skip_for_role(rule, "Subagent"):
            continue
        if match_rule(rule, "Bash", tool_input):
            assert rule.id == "R04"
            blocked = True
            print(f"  ✓ DENY: 'git push' as Subagent blocked by {rule.id}")
            break
    assert blocked, "git push by Subagent should be blocked by R04"


if __name__ == "__main__":
    print("=" * 60)
    print("SDK Guardrail Hook PoC — Test Suite")
    print("=" * 60)
    print()

    test_load_rules()
    print()
    test_trigger_matching()
    print()
    test_detect_patterns()
    print()
    test_role_blocking()
    print()
    test_timing()
    print()
    test_full_hook_simulation()

    print()
    print("=" * 60)
    print("✅ All PoC tests passed!")
    print("=" * 60)
