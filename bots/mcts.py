"""Monte Carlo Tree Search bot implementation for Mahjong16."""

from __future__ import annotations

import copy
import math
import random
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
        seed: Optional RNG seed used for deterministic behaviour.
    """

    simulations: int = 128
    uct_c: float = 1.4
    rollout_depth: int = 12
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

        for _ in range(max(1, self.config.simulations)):
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
        if self._scratch_env is None:
            self._scratch_env = Mahjong16Env(self.env.rules)
        env = self._scratch_env
        env.restore(root.snapshot)
        node = root
        obs = env._obs(node.player)
        path = [node]

        while True:
            if getattr(env, "done", False) or node.is_terminal():
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

            if node.unexpanded_actions:
                action = node.unexpanded_actions.pop(self.rng.randrange(len(node.unexpanded_actions)))
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
            candidates = [a for a in actions if (a.get("type") or "").upper() != "PASS"]
            if candidates:
                candidates.sort(key=lambda a: PRIORITY.get((a.get("type") or "").upper(), -1), reverse=True)
                return candidates[0]
            return actions[0]

        discards = [a for a in actions if (a.get("type") or "").upper() == "DISCARD"]
        if discards:
            base_hand = list(obs.get("hand") or [])
            drawn = obs.get("drawn")
            if drawn is not None:
                base_hand.append(drawn)
            melds = obs.get("melds")
            best_cost: Optional[int] = None
            best: List[Action] = []
            for action in discards:
                tile = action.get("tile")
                if tile is None:
                    continue
                candidate_hand = list(base_hand)
                try:
                    candidate_hand.remove(tile)
                except ValueError:
                    continue
                snapshot = evaluate_heuristic(candidate_hand, melds)
                cost = snapshot.cost
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best = [action]
                elif cost == best_cost:
                    best.append(action)
            if best:
                return self.rng.choice(best)
            return self.rng.choice(discards)
        return self.rng.choice(list(actions))

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


__all__ = ["MCTSBot", "MCTSBotConfig"]
