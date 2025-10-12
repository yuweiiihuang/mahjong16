from __future__ import annotations
from typing import Any, Dict, List, Tuple

from .breakdown import ScoreAccumulator
from .rules import RULE_PIPELINE
from .state import DerivedScoringState, build_state
from .types import ScoringContext


def score_with_breakdown(ctx: ScoringContext) -> tuple[List[int], Dict[int, List[Dict[str, Any]]]]:
    """Calculate per-player rewards and a labeled breakdown for the winner."""

    winner = ctx.winner
    if winner is None:
        return [0] * ctx.rules.n_players, {i: [] for i in range(ctx.rules.n_players)}

    state: DerivedScoringState = build_state(ctx)

    table = ctx.table
    accumulator = ScoreAccumulator(table, winner, ctx.rules.n_players)

    for apply_rule in RULE_PIPELINE:
        keep_going = apply_rule(ctx, state, accumulator)
        if keep_going is False:
            break

    rewards = [0] * ctx.rules.n_players
    total = accumulator.total()
    rewards[winner] = total
    return rewards, accumulator.to_breakdown()


def compute_payments(
    ctx: ScoringContext,
    base_points: int,
    tai_points: int,
    rewards: List[int] | None = None,
    breakdown: Dict[int, List[Dict[str, Any]]] | None = None,
) -> tuple[List[int], Dict[int, List[Dict[str, Any]]]]:
    """Return net chip movement per player under the Taiwan 16-tile payout rule."""

    if rewards is None or breakdown is None:
        rewards, breakdown = score_with_breakdown(ctx)
    else:
        rewards = list(rewards)
        breakdown = {pid: list(items) for pid, items in breakdown.items()}
    n_players = ctx.rules.n_players
    payments = [0] * n_players
    winner = ctx.winner
    if winner is None:
        return payments, breakdown

    try:
        base_points_int = int(base_points)
    except Exception:
        base_points_int = 0
    try:
        tai_points_int = int(tai_points)
    except Exception:
        tai_points_int = 0

    base_tai = int(rewards[winner]) if winner < len(rewards) else 0

    dealer_pid = getattr(ctx, "dealer_pid", None)
    try:
        dealer_streak = max(0, int(getattr(ctx, "dealer_streak", 0) or 0))
    except Exception:
        dealer_streak = 0

    dealer_bonus_for_payer = 0
    if dealer_pid is not None:
        try:
            dealer_bonus_for_payer = max(0, 2 * dealer_streak + 1)
        except Exception:
            dealer_bonus_for_payer = 0

    def extra_tai_for(opponent_pid: int) -> int:
        if dealer_pid is None:
            return 0
        if winner == dealer_pid:
            return 0
        if opponent_pid == dealer_pid:
            return dealer_bonus_for_payer
        return 0

    def payout_for(opponent_pid: int) -> int:
        total_tai = base_tai + extra_tai_for(opponent_pid)
        return base_points_int + total_tai * tai_points_int

    source = (ctx.win_source or "").upper()
    if source in ("TSUMO", "ZIMO"):
        for pid in range(n_players):
            if pid == winner:
                continue
            amount = payout_for(pid)
            payments[winner] += amount
            payments[pid] -= amount
    else:
        payer = getattr(ctx, "turn_at_win", None)
        if isinstance(payer, int) and 0 <= payer < n_players:
            amount = payout_for(payer)
            payments[winner] += amount
            payments[payer] -= amount

    return payments, breakdown
