"""Monte Carlo Tree Search bot implementation for Mahjong16."""

from __future__ import annotations

import copy
import math
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bots.heuristics import HeuristicSnapshot, heuristic as evaluate_heuristic
from core.env import PRIORITY, Mahjong16Env


Action = Dict[str, Any]
Observation = Dict[str, Any]


@dataclass(frozen=True)
class MCTSBotConfig:
    """Configuration options for :class:`MCTSBot`.

    Attributes:
        simulations: Number of playouts performed per decision.
        uct_c: Exploration constant for the UCT formula.
        rollout_depth: Maximum depth for rollout simulations.
        time_budget: Optional wall-clock budget (seconds) per decision.
        seed: Optional RNG seed used for deterministic behaviour.
    """

    simulations: int = 128
    uct_c: float = 1.4
    rollout_depth: int = 12
    time_budget: Optional[float] = 0.6
    seed: Optional[int] = None


def _freeze_action(action: Action) -> Tuple[Tuple[str, Any], ...]:
    """Create a hashable representation of an action dict."""

    def _freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(_freeze(v) for v in value)
        if isinstance(value, set):
            return tuple(sorted(_freeze(v) for v in value))
        return value

    return tuple(sorted((k, _freeze(v)) for k, v in action.items()))


def _copy_actions(actions: Iterable[Action]) -> List[Action]:
    return [copy.deepcopy(a) for a in actions]


class MCTSNode:
    """Single node within the MCTS search tree."""

    __slots__ = (
        "player",
        "phase",
        "action",
        "parent",
        "visits",
        "total_value",
        "children",
        "unexpanded_actions",
        "snapshot",
    )

    def __init__(
        self,
        *,
        player: int,
        phase: str,
        legal_actions: Sequence[Action],
        snapshot: Dict[str, Any],
        action: Optional[Action] = None,
        parent: Optional["MCTSNode"] = None,
    ) -> None:
        self.player = player
        self.phase = phase
        self.action = copy.deepcopy(action) if action is not None else None
        self.parent = parent
        self.visits = 0
        self.total_value = 0.0
        self.children: Dict[Tuple[Tuple[str, Any], ...], "MCTSNode"] = {}
        self.unexpanded_actions = _copy_actions(legal_actions)
        self.snapshot = copy.deepcopy(snapshot)

    def is_terminal(self) -> bool:
        return not self.unexpanded_actions and not self.children

    def best_child(self, c: float, rng: random.Random) -> "MCTSNode":
        """Select the best child according to the UCT formula."""

        assert self.children, "best_child called on node without children"
        parent_visits = max(1, self.visits)

        def score(child: "MCTSNode") -> float:
            if child.visits == 0:
                return float("inf")
            exploitation = child.total_value / child.visits
            exploration = c * math.sqrt(math.log(parent_visits) / child.visits)
            priority_bonus = 0.0
            if self.phase == "REACTION" and child.action is not None:
                atype = (child.action.get("type") or "").upper()
                priority_bonus = PRIORITY.get(atype, -1) * 1e-3
            return exploitation + exploration + priority_bonus

        best_score = None
        best_nodes: List[MCTSNode] = []
        for child in self.children.values():
            value = score(child)
            if best_score is None or value > best_score:
                best_score = value
                best_nodes = [child]
            elif math.isclose(value, best_score):
                best_nodes.append(child)
        return rng.choice(best_nodes)


class MCTSBot:
    """Monte Carlo Tree Search bot for Mahjong16.

    The bot clones the provided environment and performs simulated playouts
    before choosing an action. The :class:`MCTSBotConfig` allows tuning the
    number of simulations, the UCT exploration constant, and the rollout
    horizon. Provide an optional seed for deterministic behaviour.
    """

    def __init__(self, env: Mahjong16Env, config: Optional[MCTSBotConfig] = None) -> None:
        self.env = env
        self.config = config or MCTSBotConfig()
        self.rng = random.Random(self.config.seed)
        self._scratch_env: Optional[Mahjong16Env] = None

    # ------------------------------------------------------------------
    # Public API

    def choose(self, obs: Observation) -> Action:
        """Choose an action using Monte Carlo Tree Search."""

        actions: List[Action] = obs.get("legal_actions", []) or []
        if not actions:
            return {"type": "PASS"}

        for action in actions:
            if (action.get("type") or "").upper() == "HU":
                return copy.deepcopy(action)

        if len(actions) == 1:
            return copy.deepcopy(actions[0])

        root_snapshot = self.env.snapshot()
        root = MCTSNode(
            player=obs.get("player", 0),
            phase=obs.get("phase", "TURN"),
            legal_actions=actions,
            snapshot=root_snapshot,
        )

        max_iterations = max(1, self.config.simulations)
        start_time = time.perf_counter()
        for _ in range(max_iterations):
            if (
                self.config.time_budget is not None
                and time.perf_counter() - start_time >= self.config.time_budget
            ):
                break
            self._simulate(root)

        if not root.children:
            return copy.deepcopy(actions[0])

        best_child = max(
            root.children.values(),
            key=lambda node: (node.visits, node.total_value / node.visits if node.visits else -float("inf")),
        )
        return copy.deepcopy(best_child.action or actions[0])

    # ------------------------------------------------------------------
    # Core MCTS steps

    def _simulate(self, root: MCTSNode) -> None:
        env = self._scratch_from_snapshot(root.snapshot)
        node = root
        obs = env._obs(node.player)
        path = [node]

        while True:
            if getattr(env, "done", False) or node.is_terminal():
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

            if node.unexpanded_actions:
                action = node.unexpanded_actions.pop(
                    self.rng.randrange(len(node.unexpanded_actions))
                )
                obs, _, done, _ = env.step(action)
                child = MCTSNode(
                    player=obs.get("player", root.player),
                    phase=obs.get("phase", "TURN"),
                    legal_actions=obs.get("legal_actions", []) or env.legal_actions(),
                    snapshot=env.snapshot(),
                    action=action,
                    parent=node,
                )
                node.children[_freeze_action(action)] = child
                path.append(child)
                value = self._rollout(env, obs, done, root.player)
                self._backpropagate(path, value)
                return

            child = node.best_child(self.config.uct_c, self.rng)
            obs, _, done, _ = env.step(child.action or {"type": "PASS"})
            node = child
            path.append(node)
            if done:
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

    def _rollout(self, env: Mahjong16Env, obs: Observation, done: bool, root_player: int) -> float:
        depth = 0
        while not done and depth < self.config.rollout_depth:
            actions = obs.get("legal_actions", []) or env.legal_actions()
            if not actions:
                break
            action = self._rollout_policy(obs, actions)
            obs, _, done, _ = env.step(action)
            depth += 1
        return self._evaluate(env, root_player)

    def _rollout_policy(self, obs: Observation, actions: Sequence[Action]) -> Action:
        phase = obs.get("phase")
        for action in actions:
            if (action.get("type") or "").upper() == "HU":
                return action

        if phase == "REACTION":
            return self._rollout_reaction(obs, actions)
        return self._rollout_turn(obs, actions)

    def _rollout_reaction(self, obs: Observation, actions: Sequence[Action]) -> Action:
        baseline = evaluate_heuristic(obs.get("hand") or [], obs.get("melds"))
        best_action: Optional[Action] = None
        best_key = (baseline.cost, 1)

        for action in actions:
            atype = (action.get("type") or "").upper()
            if atype not in {"CHI", "PONG", "GANG"}:
                continue

            hand, melds = self._after_claim(obs, action)
            snapshot = evaluate_heuristic(hand, melds)
            priority = 0 if atype == "GANG" else 1
            key = (snapshot.cost, priority)
            if key < best_key:
                best_key = key
                best_action = action

        return best_action if best_action is not None else {"type": "PASS"}

    def _rollout_turn(self, obs: Observation, actions: Sequence[Action]) -> Action:
        tings = [a for a in actions if (a.get("type") or "").upper() == "TING"]
        if tings:
            return max(tings, key=lambda action: len(action.get("waits") or []))

        best_action: Optional[Action] = None
        best_key: Optional[Tuple[int, int, int]] = None

        for action in actions:
            if (action.get("type") or "").upper() != "DISCARD":
                continue

            hand, melds = self._after_discard(obs, action)
            snapshot = evaluate_heuristic(hand, melds)
            singles = snapshot.singles
            tie_break = 0 if action.get("from") == "drawn" else 1
            key = (snapshot.cost, singles, tie_break)
            if best_key is None or key < best_key:
                best_key = key
                best_action = action

        return best_action if best_action is not None else self.rng.choice(list(actions))

    def _evaluate(self, env: Mahjong16Env, root_player: int) -> float:
        if getattr(env, "done", False):
            winner = getattr(env, "winner", None)
            if winner is None:
                return 0.0
            if winner == root_player:
                return 1.0
            return -1.0

        pov = env._obs(root_player)
        hand = list(pov.get("hand") or [])
        drawn = pov.get("drawn")
        if drawn is not None:
            hand.append(drawn)
        snapshot: HeuristicSnapshot = evaluate_heuristic(hand, pov.get("melds"))
        # Convert heuristic cost into a bounded score in [-1, 1]
        value = -snapshot.cost / 10.0
        value += snapshot.melds * 0.05
        if snapshot.has_pair:
            value += 0.05
        return max(-1.0, min(1.0, value))

    def _backpropagate(self, path: Sequence[MCTSNode], value: float) -> None:
        for node in reversed(path):
            node.visits += 1
            node.total_value += value

    # ------------------------------------------------------------------
    # Helpers

    def _scratch_from_snapshot(self, snapshot: Dict[str, Any]) -> Mahjong16Env:
        if self._scratch_env is None:
            self._scratch_env = Mahjong16Env.from_snapshot(self.env.rules, snapshot)
        else:
            self._scratch_env.restore(snapshot)
        return self._scratch_env

    def _after_discard(self, obs: Observation, action: Action) -> Tuple[List[int], List[dict]]:
        hand = list(obs.get("hand") or [])
        drawn = obs.get("drawn")
        melds = [dict(m) for m in (obs.get("melds") or [])]

        tile = action.get("tile")
        source = action.get("from", "hand")

        if source != "drawn":
            if tile in hand:
                hand.remove(tile)
            if drawn is not None:
                hand.append(drawn)

        return hand, melds

    def _after_claim(self, obs: Observation, action: Action) -> Tuple[List[int], List[dict]]:
        hand = list(obs.get("hand") or [])
        melds = [dict(m) for m in (obs.get("melds") or [])]
        last_discard = obs.get("last_discard") or {}
        tile = last_discard.get("tile")
        atype = (action.get("type") or "").upper()

        def _remove_tiles(target: List[int], value: int, amount: int) -> None:
            removed = 0
            for idx in range(len(target) - 1, -1, -1):
                if target[idx] == value:
                    target.pop(idx)
                    removed += 1
                    if removed == amount:
                        return

        if atype == "CHI":
            a, b = action.get("use", [None, None])
            if a in hand:
                hand.remove(a)
            if b in hand:
                hand.remove(b)
            melds.append({"type": "CHI", "tiles": [a, b, tile]})
        elif atype == "PONG":
            if tile is not None:
                _remove_tiles(hand, tile, 2)
                melds.append({"type": "PONG", "tiles": [tile] * 3})
        elif atype == "GANG":
            if tile is not None:
                _remove_tiles(hand, tile, 3)
                melds.append({"type": "GANG", "tiles": [tile] * 4})

        return hand, melds


__all__ = ["MCTSBot", "MCTSBotConfig"]
