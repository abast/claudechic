"""CheckFailed -> Hints adapter. Bridges check failures into hint data."""

from __future__ import annotations

from claudechic.checks.protocol import CheckResult, OnFailureConfig


def check_failed_to_hint(
    check_result: CheckResult,
    on_failure: OnFailureConfig,
    check_id: str,
) -> dict | None:
    """Adapter: convert failed CheckResult to hint data.

    Returns None if check passed. Engine feeds result into
    hints pipeline via run_pipeline().
    """
    if check_result.passed:
        return None

    message = on_failure.message
    if check_result.evidence:
        message = f"{on_failure.message}\n  Evidence: {check_result.evidence}"

    return {
        "id": f"check-failed:{check_id}",
        "message": message,
        "severity": on_failure.severity,
        "lifecycle": on_failure.lifecycle,
        "trigger": "always",  # Already failed -- fire immediately
    }
