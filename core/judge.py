# file: core/judge.py
from __future__ import annotations
from typing import Any, Dict, List

# Compatibility adapter, delegating to refactored modules.

from .hand import is_win_16, waits_for_hand_16, waits_after_discard_17
from .scoring.tables import load_scoring_assets
from .scoring.types import ScoringContext, ScoringTable
from .scoring.engine import score_with_breakdown as _engine_score


def score_with_breakdown(env) -> tuple[List[int], Dict[int, List[Dict[str, Any]]]]:
    rules = env.rules
    profile_name = getattr(rules, "scoring_profile", "taiwan_base")
    table: ScoringTable = load_scoring_assets(profile_name, getattr(rules, "scoring_overrides_path", None))
    ctx = ScoringContext.from_env(env, table)
    return _engine_score(ctx)


def _score_env(env) -> List[int]:
    rewards, _ = score_with_breakdown(env)
    return rewards


def settle_scores_stub(env) -> List[int]:
    return _score_env(env)

