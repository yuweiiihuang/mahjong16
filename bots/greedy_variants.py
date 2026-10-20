"""Independent, visible-information ablations of the default Greedy strategy."""
from __future__ import annotations

from typing import Sequence

from bots.greedy import (
    GreedyBotStrategy, _after_claim, _after_discard, _heuristic,
    _live_counts_from_obs, _snapshot_order,
)
from domain.rules.ruleset import Ruleset


class GreedyLookaheadStrategy(GreedyBotStrategy):
    """Compare PASS and claims after the best legal post-CHI/PONG discard.

    Only the reaction decision changes. Later TURN decisions retain default Greedy,
    including its TING preference. GANG keeps its original score: replacement draws
    cannot be predicted from the visible observation.
    """

    def __init__(self, rules: Ruleset | None = None) -> None:
        super().__init__()
        self.allow_same_tile_discard_after_chi = (
            rules or Ruleset()).allow_same_tile_discard_after_chi

    def _choose_reaction(self, obs: dict, actions: Sequence[dict]) -> dict:
        live = _live_counts_from_obs(obs)

        def score(hand: list[int], melds: list[dict]) -> tuple[int, ...]:
            return _snapshot_order(_heuristic(hand, melds, self.weights, live_counts=live))

        best = next(a for a in actions if a["type"] == "PASS")
        best_key = score(obs["hand"], obs["melds"]) + (1,)
        for action in actions:
            kind = action["type"]
            if kind not in ("CHI", "PONG", "GANG"):
                continue
            hand, melds = _after_claim(obs, action)
            if kind in ("CHI", "PONG"):
                blocked = (obs["last_discard"]["tile"] if kind == "CHI"
                           and not self.allow_same_tile_discard_after_chi else None)
                outcomes = []
                for tile in sorted(set(hand)):
                    if tile == blocked:
                        continue
                    remaining = list(hand)
                    remaining.remove(tile)
                    outcomes.append(score(remaining, melds))
                if not outcomes:
                    continue
                key = min(outcomes) + (1,)
            else:
                key = score(hand, melds) + (0,)
            if key < best_key:
                best, best_key = action, key
        return best


class GreedyDefenseStrategy(GreedyBotStrategy):
    """Fold distant hands against public threats using a tile-completion proxy.

    A threat means declared TING or four exposed melds. With at least two structure
    steps remaining, prefer discards compatible with fewer unseen pair/triplet/run
    completions, retaining default Greedy among ties. This is a risk ordering, not
    a calibrated probability; Taiwan discards do not imply riichi-style safety.
    Reactions, wins, TING and near-ready attacking hands retain the default policy.
    """

    def _choose_turn(self, obs: dict, actions: Sequence[dict]) -> dict:
        baseline = super()._choose_turn(obs, actions)
        if baseline["type"] != "DISCARD":
            return baseline
        threats = [p for i, p in enumerate(obs.get("players", []))
                   if i != obs["player"] and (
                       p.get("declared_ting", False)
                       or sum(m["type"] in ("CHI", "PONG", "GANG")
                              for m in p.get("melds", [])) >= 4)]
        if not threats:
            return baseline
        hand, melds = _after_discard(obs, baseline)
        if _heuristic(hand, melds, self.weights,
                      include_availability=False).structure_distance < 2:
            return baseline
        unseen = _live_counts_from_obs(obs)

        def risk(action: dict) -> int:
            tile = action["tile"]
            n = unseen[tile]
            ways = n + n * (n - 1) // 2
            if tile < 27:
                suit, rank = divmod(tile, 9)
                for start in range(max(0, rank - 2), min(rank, 6) + 1):
                    a, b = [suit * 9 + r for r in range(start, start + 3) if r != rank]
                    ways += unseen[a] * unseen[b]
            return ways

        discards = [a for a in actions if a["type"] == "DISCARD"]
        minimum = min(map(risk, discards))
        safest = [a for a in discards if risk(a) == minimum]
        return super()._choose_turn(obs, safest)
