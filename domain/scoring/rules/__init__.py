"""Rule application pipeline for the scoring engine."""

from .base import apply_base_rules
from .flowers import apply_flowers_rules
from .honors import apply_honors_rules
from .patterns import apply_patterns_rules
from .timings import apply_timings_rules
from .waits import apply_waits_rules

RULE_PIPELINE = (
    apply_flowers_rules,
    apply_base_rules,
    apply_waits_rules,
    apply_patterns_rules,
    apply_honors_rules,
    apply_timings_rules,
)

__all__ = [
    "RULE_PIPELINE",
    "apply_base_rules",
    "apply_flowers_rules",
    "apply_honors_rules",
    "apply_patterns_rules",
    "apply_timings_rules",
    "apply_waits_rules",
]
