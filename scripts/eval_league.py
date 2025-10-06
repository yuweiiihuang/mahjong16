"""Run a small league of Mahjong16 bots and summarise the results.

The script orchestrates repeated headless matches between a roster of agents
and reports aggregated standings.  Agents can be referenced by built‑in alias
(`auto`, `greedy`, `random`, `rulebot`) or by an import path in the form
``package.module:ClassOrFactory``.  Each match draws four participants (or the
configured table size), plays a fixed number of hands, and accumulates points
using the standard scoring pipeline from :mod:`core.scoring`.

Example
-------

.. code-block:: bash

    python scripts/eval_league.py \
        --hands 32 --matches 5 --seed 123 \
        greedy random rulebot bots.greedy:GreedyBotStrategy

The output includes an ASCII table ranked by average points per match and a
JSON serialisation when ``--json-out`` is supplied.
"""

from __future__ import annotations

import argparse
import importlib
import itertools
import json
import math
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

# Ensure the project root (two levels up) is importable when invoked as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.table import TableManager
from core import Mahjong16Env, Ruleset
from core.scoring.engine import compute_payments, score_with_breakdown
from core.scoring.tables import load_scoring_assets
from core.scoring.types import ScoringContext


StrategyFactory = Callable[..., Any]


@dataclass(frozen=True)
class AgentSpec:
    """Definition of a league participant."""

    name: str
    target: str
    factory: StrategyFactory


@dataclass
class HandRecord:
    """Minimal outcome data for a single hand."""

    index: int
    winner: int | None
    win_source: str | None
    flower_type: str | None
    payments: list[int]


@dataclass
class MatchResult:
    """Aggregate data for a single match (multi-hand table)."""

    agents: list[AgentSpec]
    totals: list[int]
    hands_played: int
    hand_records: list[HandRecord]


@dataclass
class AgentStats:
    """Accumulated statistics for a league participant."""

    name: str
    matches: int = 0
    hands: int = 0
    wins: int = 0
    tsumo_wins: int = 0
    ron_wins: int = 0
    draws: int = 0
    total_points: int = 0
    final_points_sq: float = 0.0
    best_final: int | None = None
    worst_final: int | None = None
    special_wins: Counter[str] = field(default_factory=Counter)

    def register_match(
        self,
        *,
        final_points: int,
        hands_played: int,
        wins: int,
        tsumo_wins: int,
        ron_wins: int,
        draws: int,
        special_wins: Mapping[str, int],
    ) -> None:
        """Update cumulative statistics after a match."""

        self.matches += 1
        self.hands += hands_played
        self.wins += wins
        self.tsumo_wins += tsumo_wins
        self.ron_wins += ron_wins
        self.draws += draws
        self.total_points += final_points
        self.final_points_sq += float(final_points) ** 2
        if self.best_final is None or final_points > self.best_final:
            self.best_final = final_points
        if self.worst_final is None or final_points < self.worst_final:
            self.worst_final = final_points
        if special_wins:
            self.special_wins.update(special_wins)


class StrategyAdapter:
    """Uniform adaptor around strategy implementations."""

    def __init__(self, impl: Any) -> None:
        self.impl = impl

    def choose(self, obs):  # type: ignore[override]
        if hasattr(self.impl, "choose"):
            return self.impl.choose(obs)
        if hasattr(self.impl, "select"):
            return self.impl.select(obs)
        raise TypeError(
            f"Strategy object {self.impl!r} does not expose a choose/select method"
        )


_BUILTIN_FACTORIES: Mapping[str, StrategyFactory] | None = None


def builtin_factories() -> Mapping[str, StrategyFactory]:
    global _BUILTIN_FACTORIES
    if _BUILTIN_FACTORIES is None:
        from app.strategies import AutoStrategy
        from bots.greedy import GreedyBotStrategy
        from bots.random_bot import RandomBot
        from bots.rulebot import RuleBot

        _BUILTIN_FACTORIES = {
            "auto": lambda seed=None: AutoStrategy(),
            "greedy": lambda seed=None: GreedyBotStrategy(),
            "greedybot": lambda seed=None: GreedyBotStrategy(),
            "random": lambda seed=None: RandomBot(seed=seed),
            "randombot": lambda seed=None: RandomBot(seed=seed),
            "rulebot": lambda seed=None: RuleBot(),
            "rule": lambda seed=None: RuleBot(),
        }
    return _BUILTIN_FACTORIES


def resolve_factory(target: str) -> StrategyFactory:
    table = builtin_factories()
    alias = target.lower()
    if alias in table:
        return table[alias]
    if ":" not in target:
        raise ValueError(f"Unknown agent specifier: {target}")
    module_name, attr_path = target.split(":", 1)
    module = importlib.import_module(module_name)
    obj = module
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    if not callable(obj):  # pragma: no cover - defensive
        raise TypeError(f"Resolved object is not callable: {target}")
    return obj  # type: ignore[return-value]


def parse_agent_spec(token: str) -> AgentSpec:
    if "=" in token:
        alias, target = token.split("=", 1)
        name = alias.strip()
    else:
        target = token
        name = token.split(":", 1)[0].split(".")[-1]
    factory = resolve_factory(target)
    display = name or getattr(factory, "__name__", target)
    return AgentSpec(name=display, target=target, factory=factory)


def instantiate_strategy(factory: StrategyFactory, *, seed: int | None = None) -> Any:
    try:
        return factory(seed=seed)
    except TypeError:
        if seed is None:
            return factory()
        try:
            return factory(seed)
        except TypeError:
            return factory()


def iter_matchups(roster: Sequence[AgentSpec], table_size: int) -> Iterator[tuple[AgentSpec, ...]]:
    if len(roster) < table_size:
        raise ValueError(
            f"Need at least {table_size} agents, received {len(roster)}"
        )
    if len(roster) == table_size:
        yield tuple(roster)
        return
    for combo in itertools.combinations(roster, table_size):
        yield combo


def to_payments_list(raw: Mapping[int, Any] | Sequence[int], n_players: int) -> list[int]:
    if isinstance(raw, Mapping):
        return [int(raw.get(pid, 0)) for pid in range(n_players)]
    return [int(raw[pid]) if pid < len(raw) else 0 for pid in range(n_players)]


def play_match(
    agents: Sequence[AgentSpec],
    *,
    hands: int,
    rules: Ruleset,
    scoring_table,
    match_seed: int,
) -> MatchResult:
    n_players = len(agents)
    env = Mahjong16Env(rules, seed=match_seed)
    table = TableManager(rules, seed=match_seed)
    table.initialize(n_players)

    strategies = [
        StrategyAdapter(instantiate_strategy(agent.factory, seed=match_seed + idx))
        for idx, agent in enumerate(agents)
    ]

    totals = [0 for _ in range(n_players)]
    records: list[HandRecord] = []

    for hand_index in range(1, hands + 1):
        obs = table.start_hand(env)
        done = bool(getattr(env, "done", False))

        step_guard = 0
        while not done:
            acts = obs.get("legal_actions") or []
            if not acts:
                acts = env.legal_actions()
                if not acts:
                    if getattr(env, "done", False):
                        break
                    raise RuntimeError(
                        f"Player {obs.get('player')} has no legal actions"
                    )
                obs = dict(obs)
                obs["legal_actions"] = acts

            pid = obs.get("player")
            if not isinstance(pid, int):  # pragma: no cover - defensive
                raise RuntimeError("Observation missing player identifier")
            action = strategies[pid].choose(obs)
            obs, _rew, done, _info = env.step(action)
            step_guard += 1
            if step_guard > 4000:
                raise RuntimeError("Aborting hand due to excessive steps")

        ctx = ScoringContext.from_env(env, scoring_table)
        rewards, breakdown = score_with_breakdown(ctx)
        payments_raw, _ = compute_payments(
            ctx,
            rules.base_points,
            rules.tai_points,
            rewards=rewards,
            breakdown=breakdown,
        )
        payments = to_payments_list(payments_raw, n_players)
        for pid in range(n_players):
            totals[pid] += payments[pid]

        winner = getattr(env, "winner", None)
        win_source = getattr(env, "win_source", None)
        flower_type = getattr(env, "flower_win_type", None)
        records.append(
            HandRecord(
                index=hand_index,
                winner=winner if isinstance(winner, int) else None,
                win_source=(win_source.upper() if isinstance(win_source, str) else None),
                flower_type=(flower_type if isinstance(flower_type, str) else None),
                payments=payments,
            )
        )

        table.finish_hand(env)

    return MatchResult(
        agents=list(agents),
        totals=totals,
        hands_played=len(records),
        hand_records=records,
    )


def update_league(stats: Mapping[str, AgentStats], result: MatchResult) -> None:
    n_players = len(result.agents)
    wins = [0] * n_players
    tsumo = [0] * n_players
    ron = [0] * n_players
    draws = [0] * n_players
    special: list[Counter[str]] = [Counter() for _ in range(n_players)]

    for record in result.hand_records:
        if record.winner is None:
            for idx in range(n_players):
                draws[idx] += 1
            continue
        seat = record.winner
        wins[seat] += 1
        if record.win_source == "TSUMO":
            tsumo[seat] += 1
        elif record.win_source == "RON":
            ron[seat] += 1
        if record.flower_type:
            special[seat][record.flower_type] += 1

    for idx, agent in enumerate(result.agents):
        stats[agent.name].register_match(
            final_points=result.totals[idx],
            hands_played=result.hands_played,
            wins=wins[idx],
            tsumo_wins=tsumo[idx],
            ron_wins=ron[idx],
            draws=draws[idx],
            special_wins=special[idx],
        )


def compute_metrics(stat: AgentStats) -> dict[str, Any]:
    avg_match = stat.total_points / stat.matches if stat.matches else 0.0
    avg_hand = stat.total_points / stat.hands if stat.hands else 0.0
    win_rate = stat.wins / stat.hands if stat.hands else 0.0
    tsumo_rate = stat.tsumo_wins / stat.hands if stat.hands else 0.0
    ron_rate = stat.ron_wins / stat.hands if stat.hands else 0.0
    draw_rate = stat.draws / stat.hands if stat.hands else 0.0
    variance = 0.0
    if stat.matches:
        mean_sq = stat.final_points_sq / stat.matches
        variance = max(0.0, mean_sq - avg_match**2)
    stddev = math.sqrt(variance)
    return {
        "name": stat.name,
        "matches": stat.matches,
        "hands": stat.hands,
        "wins": stat.wins,
        "tsumo_wins": stat.tsumo_wins,
        "ron_wins": stat.ron_wins,
        "draws": stat.draws,
        "total_points": stat.total_points,
        "avg_points_per_match": avg_match,
        "avg_points_per_hand": avg_hand,
        "win_rate": win_rate,
        "tsumo_rate": tsumo_rate,
        "ron_rate": ron_rate,
        "draw_rate": draw_rate,
        "stddev_final": stddev,
        "best_final": stat.best_final,
        "worst_final": stat.worst_final,
        "special_wins": dict(stat.special_wins),
    }


def render_table(metrics: Iterable[Mapping[str, Any]]) -> str:
    metrics_list = list(metrics)
    if not metrics_list:
        return "(no results)"
    metrics_list.sort(key=lambda m: m["avg_points_per_match"], reverse=True)
    headers = [
        "Agent",
        "Matches",
        "Hands",
        "AvgPts/Match",
        "AvgPts/Hand",
        "Win%",
        "Ron%",
        "Tsumo%",
        "Draw%",
        "StdDev",
        "Best",
        "Worst",
    ]

    rows = []
    for row in metrics_list:
        rows.append(
            [
                row["name"],
                f"{row['matches']}",
                f"{row['hands']}",
                f"{row['avg_points_per_match']:.2f}",
                f"{row['avg_points_per_hand']:.2f}",
                f"{row['win_rate'] * 100:.1f}",
                f"{row['ron_rate'] * 100:.1f}",
                f"{row['tsumo_rate'] * 100:.1f}",
                f"{row['draw_rate'] * 100:.1f}",
                f"{row['stddev_final']:.2f}",
                f"{row['best_final'] if row['best_final'] is not None else 0}",
                f"{row['worst_final'] if row['worst_final'] is not None else 0}",
            ]
        )

    col_widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    header_line = " ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = " ".join("-" * col_widths[i] for i in range(len(headers)))
    body_lines = [
        " ".join(r[i].ljust(col_widths[i]) for i in range(len(headers)))
        for r in rows
    ]
    return "\n".join([header_line, sep_line, *body_lines])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "agents",
        nargs="+",
        help=(
            "Agent specs (alias or name=module:callable). Provide at least as many entries "
            "as there are seats at the table."
        ),
    )
    parser.add_argument("--players", type=int, default=4, help="Number of seats per table.")
    parser.add_argument("--hands", type=int, default=16, help="Hands per match (default: 16).")
    parser.add_argument(
        "--matches",
        type=int,
        default=1,
        help="Number of matches to run for each seating combination (default: 1).",
    )
    parser.add_argument("--seed", type=int, default=None, help="Base RNG seed for reproducibility.")
    parser.add_argument(
        "--profile",
        default="taiwan_base",
        help="Scoring profile name (default: taiwan_base).",
    )
    parser.add_argument(
        "--scoring-json",
        type=Path,
        default=None,
        help="Optional path to override scoring assets (JSON).",
    )
    parser.add_argument(
        "--base-points",
        type=int,
        default=100,
        help="Flat base points applied before tai multiplication (default: 100).",
    )
    parser.add_argument(
        "--tai-points",
        type=int,
        default=20,
        help="Point value per tai (default: 20).",
    )
    parser.add_argument(
        "--dead-wall-mode",
        choices=["fixed", "gang_plus_one"],
        default="fixed",
        help="Dead wall reservation mode (default: fixed).",
    )
    parser.add_argument(
        "--dead-wall-base",
        type=int,
        default=16,
        help="Base reserved tiles for the dead wall (default: 16).",
    )
    parser.add_argument(
        "--no-flowers",
        action="store_true",
        help="Disable flowers in the wall and scoring.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write aggregated metrics to JSON at the given path.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-match progress logging.",
    )
    return parser.parse_args(argv)


def build_rules(args: argparse.Namespace) -> Ruleset:
    return Ruleset(
        include_flowers=not args.no_flowers,
        n_players=args.players,
        dead_wall_mode=args.dead_wall_mode,
        dead_wall_base=args.dead_wall_base,
        scoring_profile=args.profile,
        scoring_overrides_path=(
            str(args.scoring_json) if args.scoring_json is not None else None
        ),
        base_points=args.base_points,
        tai_points=args.tai_points,
        randomize_seating_and_dealer=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.players <= 1:
        raise SystemExit("Table size must be at least 2.")
    if args.hands <= 0:
        raise SystemExit("Hands per match must be a positive integer.")
    if args.matches <= 0:
        raise SystemExit("Matches per combination must be positive.")

    roster = [parse_agent_spec(token) for token in args.agents]
    names = [spec.name for spec in roster]
    if len(set(names)) != len(names):
        duplicates = ", ".join(
            sorted(name for name, count in Counter(names).items() if count > 1)
        )
        raise SystemExit(
            "Agent display names must be unique; duplicate(s) found: " + duplicates
        )
    rules = build_rules(args)
    scoring_table = load_scoring_assets(
        args.profile,
        str(args.scoring_json) if args.scoring_json is not None else rules.scoring_overrides_path,
    )

    rng = random.Random(args.seed)
    combos = list(iter_matchups(roster, args.players))
    total_matches = len(combos) * args.matches
    stats = {spec.name: AgentStats(spec.name) for spec in roster}

    match_counter = 0
    for combo in combos:
        for _ in range(args.matches):
            seating = list(combo)
            rng.shuffle(seating)
            match_seed = rng.randrange(1 << 30)
            result = play_match(
                seating,
                hands=args.hands,
                rules=rules,
                scoring_table=scoring_table,
                match_seed=match_seed,
            )
            update_league(stats, result)
            match_counter += 1
            if not args.quiet:
                summary = ", ".join(
                    f"{agent.name}:{result.totals[idx]:+d}"
                    for idx, agent in enumerate(result.agents)
                )
                print(f"[{match_counter}/{total_matches}] {summary}")

    metrics = [compute_metrics(stat) for stat in stats.values()]
    print()
    print(render_table(metrics))

    if args.json_out is not None:
        payload = {
            "config": {
                "players": args.players,
                "hands_per_match": args.hands,
                "matches_per_combo": args.matches,
                "seed": args.seed,
                "profile": args.profile,
                "scoring_json": str(args.scoring_json) if args.scoring_json else None,
                "base_points": args.base_points,
                "tai_points": args.tai_points,
                "include_flowers": not args.no_flowers,
                "dead_wall_mode": args.dead_wall_mode,
                "dead_wall_base": args.dead_wall_base,
            },
            "agents": metrics,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
