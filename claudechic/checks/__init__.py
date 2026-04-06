"""Public API for the checks package."""

from claudechic.checks.adapter import check_failed_to_hint
from claudechic.checks.builtins import register_check_type
from claudechic.checks.protocol import Check, CheckDecl, CheckResult, OnFailureConfig

__all__ = [
    "Check",
    "CheckDecl",
    "CheckResult",
    "OnFailureConfig",
    "check_failed_to_hint",
    "register_check_type",
]
