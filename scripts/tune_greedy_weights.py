"""Tune GreedyBot heuristic weights by minimising draw rate.

The script performs a local grid search over the :class:`HeuristicWeights`
parameters used by :class:`bots.greedy.GreedyBotStrategy`.  Each trial samples a
starting configuration on a fixed-resolution grid, then hill-climbs by
evaluating neighbouring points.  Every configuration is simulated with four
greedy players, and the configuration with the lowest draw percentage is
reported at the end of the run.

Example
-------

.. code-block:: bash

    python scripts/tune_greedy_weights.py --hands 512 --trials 30 --seed 42

Ranges for the grid can be customised through CLI flags; values can be provided
either as ``min:max`` inclusive ranges (aligned to the grid step) or as
comma-separated lists.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

TABLE_SIZE = 4

# Ensure the project root (two levels up) is importable when invoked as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from app.table import TableManager
from bots.greedy import GreedyBotStrategy, HeuristicWeights
from domain import Mahjong16Env, Ruleset


@dataclass(frozen=True)
class SearchDomain:
    """Discrete domain for sampling scaled integral weight values."""

    name: str
    values: tuple[int, ...]
    scale: int = 1

    @classmethod
    def from_spec(cls, spec: str, *, name: str, scale: int, allow_float: bool = True) -> "SearchDomain":
        spec = spec.strip()
        if not spec:
            raise ValueError(f"{name} spec cannot be empty")

        def to_int(token: str) -> int:
            value = float(token)
            scaled = round(value * scale)
            if allow_float:
                if not math.isclose(scaled / scale, value, abs_tol=1e-9):
                    raise ValueError(f"{name} value {token} is incompatible with grid step (scale={scale})")
            else:
                if not value.is_integer():
                    raise ValueError(f"{name} expects integer values (got {token})")
                if not math.isclose(scaled / scale, value, abs_tol=1e-9):
                    raise ValueError(f"{name} value {token} is incompatible with integer grid (scale={scale})")
            return int(scaled)

        if ":" in spec:
            start_str, end_str = spec.split(":", 1)
            start = to_int(start_str)
            end = to_int(end_str)
            if start > end:
                raise ValueError(f"{name} range requires start <= end (got {start}>{end})")
            step = 1
            values = tuple(range(start, end + 1, step))
        else:
            parts = [part.strip() for part in spec.split(",") if part.strip()]
            if not parts:
                raise ValueError(f"{name} spec must contain at least one value")
            values = tuple(sorted({to_int(part) for part in parts}))

        if not values:
            raise ValueError(f"{name} spec resolved to an empty domain")
        return cls(name=name, values=values, scale=scale)

    def sample(self, rng: random.Random) -> int:
        return rng.choice(self.values)

    def neighbours(self, value: int) -> Sequence[int]:
        idx = self.values.index(value)
        options: list[int] = []
        if idx > 0:
            options.append(self.values[idx - 1])
        if idx + 1 < len(self.values):
            options.append(self.values[idx + 1])
        return options

def tuple_to_weights(values: tuple[int, int, int, int, int]) -> HeuristicWeights:
    structure, bad_shape, isolated, cap, availability = values
    return HeuristicWeights(
        structure_weight=structure,
        bad_shape_weight=bad_shape,
        isolated_weight=isolated,
        isolated_cap=cap,
        availability_weight=availability,
    )


def format_weights(weights: HeuristicWeights, scale: int) -> str:
    structure = weights.structure_weight / scale if scale else weights.structure_weight
    bad_shape = weights.bad_shape_weight / scale if scale else weights.bad_shape_weight
    isolated = weights.isolated_weight / scale if scale else weights.isolated_weight
    availability = weights.availability_weight / scale if scale else weights.availability_weight
    return (
        f"struct={structure:.2f}, bad_shape={bad_shape:.2f}, "
        f"isolated_w={isolated:.2f}, availability_w={availability:.2f}, "
        f"isolated_cap={weights.isolated_cap}"
    )


class StrategyWrapper:
    """Normalise strategy interfaces to expose a ``choose`` method."""

    def __init__(self, impl: Any) -> None:
        self.impl = impl

    def choose(self, obs: Mapping[str, Any]) -> Mapping[str, Any]:
        if hasattr(self.impl, "choose"):
            return self.impl.choose(obs)
        if hasattr(self.impl, "select"):
            return self.impl.select(obs)
        raise TypeError(f"Strategy object {self.impl!r} does not support choose/select")


def ensure_legal_actions(
    obs: Mapping[str, Any], env: Mahjong16Env, pid: int
) -> Sequence[Mapping[str, Any]]:
    """Return legal actions from observation or query the environment as fallback."""

    actions = obs.get("legal_actions") if isinstance(obs, Mapping) else None
    if actions:
        return actions  # type: ignore[return-value]
    fallback = env.legal_actions(pid)
    if fallback and isinstance(obs, dict):
        obs.setdefault("legal_actions", fallback)
    return fallback


@dataclass
class TrialMetrics:
    """Outcome statistics for a single weight configuration."""

    trial_index: int
    weights: HeuristicWeights
    weight_scale: int
    hands_requested: int
    hands_played: int
    draws: int
    wins: int
    tsumo_wins: int
    ron_wins: int
    steps: int
    draw_rate: float
    seed: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hands", type=int, default=256, help="Hands per evaluation (default: 256)")
    parser.add_argument(
        "--trials",
        type=int,
        default=10,
        help="Number of local-search restarts to run (default: 10)",
    )
    parser.add_argument("--max-steps", type=int, default=25, help="Max hill-climb steps per restart (default: 25)")
    parser.add_argument("--grid-step", type=float, default=1.0, help="Grid resolution for weights (default: 1.0)")
    parser.add_argument("--seed", type=int, default=None, help="Base RNG seed for sampling and environment")
    parser.add_argument(
        "--scoring-profile",
        "--profile",
        dest="scoring_profile",
        default="taiwan_base",
        help="Scoring profile for the simulation ruleset (default: taiwan_base)",
    )
    parser.add_argument(
        "--rule-profile",
        default="common",
        help="Rule profile for the simulation ruleset (default: common)",
    )
    parser.add_argument(
        "--structure-weight-range",
        default="80:120",
        help="Domain for structure_weight (aligned to grid, default: 80:120)",
    )
    parser.add_argument(
        "--bad-shape-weight-range",
        default="3:8",
        help="Domain for bad_shape_weight (aligned to grid, default: 3:8)",
    )
    parser.add_argument(
        "--isolated-weight-range",
        default="1:3",
        help="Domain for isolated_weight (aligned to grid, default: 1:3)",
    )
    parser.add_argument(
        "--availability-weight-range",
        default="1:4",
        help="Domain for availability_weight (aligned to grid, default: 1:4)",
    )
    parser.add_argument(
        "--isolated-cap-range",
        default="8:16",
        help="Domain for isolated_cap (min:max or comma list, default: 8:16)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for serialised trial metrics (JSON list)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar output",
    )
    return parser.parse_args()


def run_trial(
    trial_index: int,
    *,
    weights: HeuristicWeights,
    weight_scale: int,
    args: argparse.Namespace,
    hands: int,
    base_seed: int | None,
    progress: Progress | None = None,
    task_id: TaskID | None = None,
) -> TrialMetrics:
    env_seed = (base_seed + trial_index) if base_seed is not None else None

    rules = Ruleset(
        n_players=TABLE_SIZE,
        scoring_profile=args.scoring_profile,
        rule_profile=args.rule_profile,
    )

    env = Mahjong16Env(rules, seed=env_seed)
    table = TableManager(rules, seed=env_seed)
    table.initialize(TABLE_SIZE)

    strategies = [StrategyWrapper(GreedyBotStrategy(weights=weights)) for _ in range(TABLE_SIZE)]

    draws = 0
    wins = 0
    tsumo_wins = 0
    ron_wins = 0
    steps = 0
    hands_played = 0

    for _hand in range(hands):
        obs = table.start_hand(env)
        done = False
        while not done:
            if getattr(env, "done", False):
                break
            pid = int(obs.get("player", env.turn)) if isinstance(obs, Mapping) else env.turn
            legal = ensure_legal_actions(obs, env, pid) or []
            try:
                action = strategies[pid].choose(obs)
            except Exception:
                action = {"type": "PASS"}
            if isinstance(action, Mapping):
                action = dict(action)
            if not isinstance(action, dict) or not action:
                action = {"type": "PASS"}
            if legal and action not in legal:
                action = legal[0]
            obs, _reward, done, _info = env.step(action)
            steps += 1
        else:
            # Loop exhausted naturally; mirror env.done for clarity
            done = getattr(env, "done", done)

        if getattr(env, "done", False) and not done:
            done = True

        hands_played += 1
        winner = getattr(env, "winner", None)
        win_source = str(getattr(env, "win_source", None) or "DRAW").upper()
        if winner is None:
            draws += 1
        else:
            wins += 1
            if win_source in {"TSUMO", "ZIMO"}:
                tsumo_wins += 1
            elif win_source == "RON":
                ron_wins += 1

        table.finish_hand(env)
        if progress is not None and task_id is not None:
            progress.advance(task_id)

    draw_rate = (draws / hands_played) if hands_played else math.nan

    return TrialMetrics(
        trial_index=trial_index,
        weights=weights,
        hands_requested=hands,
        hands_played=hands_played,
        draws=draws,
        wins=wins,
        tsumo_wins=tsumo_wins,
        ron_wins=ron_wins,
        steps=steps,
        draw_rate=draw_rate,
        seed=env_seed,
        weight_scale=weight_scale,
    )


def print_progress(result: TrialMetrics, *, log: Callable[[str], None] = print) -> None:
    draw_pct = result.draw_rate * 100 if not math.isnan(result.draw_rate) else float("nan")
    log(
        f"Eval {result.trial_index + 1:02d} | "
        f"draws={result.draws}/{result.hands_played} ({draw_pct:.2f}%) | "
        f"wins={result.wins} (tsumo={result.tsumo_wins}, ron={result.ron_wins}) | "
        f"weights=({format_weights(result.weights, result.weight_scale)})"
    )


def choose_best(results: Sequence[TrialMetrics]) -> TrialMetrics | None:
    best: TrialMetrics | None = None
    for result in results:
        if math.isnan(result.draw_rate):
            continue
        if best is None or result.draw_rate < best.draw_rate:
            best = result
        elif best is not None and math.isclose(result.draw_rate, best.draw_rate):
            if result.wins > best.wins:
                best = result
    return best


def main() -> None:
    args = parse_args()

    progress_cm: Progress | None = None
    progress: Progress | None = None
    if not args.no_progress:
        progress_cm = Progress(
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=True,
        )
        progress = progress_cm.__enter__()

    try:
        rng = random.Random(args.seed)

        grid_step = float(args.grid_step)
        if grid_step <= 0 or grid_step > 1:
            raise SystemExit("grid_step must be in the interval (0, 1]")
        weight_scale = int(round(1.0 / grid_step))
        if weight_scale <= 0 or not math.isclose(grid_step * weight_scale, 1.0, abs_tol=1e-9):
            raise SystemExit("grid_step must evenly divide 1.0 (e.g. 1, 0.5, 0.25, 0.2)")

        structure_domain = SearchDomain.from_spec(
            args.structure_weight_range,
            name="structure_weight_range",
            scale=weight_scale,
        )
        bad_shape_domain = SearchDomain.from_spec(
            args.bad_shape_weight_range,
            name="bad_shape_weight_range",
            scale=weight_scale,
        )
        isolated_domain = SearchDomain.from_spec(
            args.isolated_weight_range,
            name="isolated_weight_range",
            scale=weight_scale,
        )
        availability_domain = SearchDomain.from_spec(
            args.availability_weight_range,
            name="availability_weight_range",
            scale=weight_scale,
        )
        cap_domain = SearchDomain.from_spec(
            args.isolated_cap_range,
            name="isolated_cap_range",
            scale=1,
            allow_float=False,
        )

        domains = (structure_domain, bad_shape_domain, isolated_domain, cap_domain, availability_domain)

        hands = max(0, int(args.hands))
        restarts = max(0, int(args.trials))
        max_steps = max(1, int(args.max_steps))

        results: list[TrialMetrics] = []
        cache: dict[tuple[int, int, int, int, int], TrialMetrics] = {}
        eval_counter = 0

        def evaluate(config: tuple[int, int, int, int, int]) -> TrialMetrics:
            nonlocal eval_counter
            metric = cache.get(config)
            if metric is not None:
                return metric

            task_id: TaskID | None = None
            if progress is not None and hands > 0:
                task_id = progress.add_task(f"Eval {eval_counter + 1}", total=hands)

            weights = tuple_to_weights(config)
            try:
                metric = run_trial(
                    eval_counter,
                    weights=weights,
                    weight_scale=weight_scale,
                    args=args,
                    hands=hands,
                    base_seed=args.seed,
                    progress=progress,
                    task_id=task_id,
                )
            except Exception:
                if progress is not None and task_id is not None:
                    progress.remove_task(task_id)
                raise

            cache[config] = metric
            results.append(metric)

            log_fn = progress.console.print if progress is not None else print
            print_progress(metric, log=log_fn)

            if progress is not None and task_id is not None:
                progress.remove_task(task_id)

            eval_counter += 1
            return metric

        def is_better(candidate: TrialMetrics, baseline: TrialMetrics) -> bool:
            if math.isnan(candidate.draw_rate):
                return False
            if math.isnan(baseline.draw_rate):
                return True
            if candidate.draw_rate < baseline.draw_rate - 1e-9:
                return True
            if math.isclose(candidate.draw_rate, baseline.draw_rate, abs_tol=1e-9):
                return candidate.wins > baseline.wins
            return False

        best_overall: TrialMetrics | None = None
        log = progress.console.print if progress is not None else print

        for restart in range(restarts):
            log(f"\n=== Restart {restart + 1}/{restarts} ===")
            start_config = (
                structure_domain.sample(rng),
                bad_shape_domain.sample(rng),
                isolated_domain.sample(rng),
                cap_domain.sample(rng),
                availability_domain.sample(rng),
            )
            current_config = start_config
            current_result = evaluate(current_config)

            for _ in range(max_steps):
                neighbours: list[tuple[int, int, int, int, int]] = []
                for idx, domain in enumerate(domains):
                    for neighbour_value in domain.neighbours(current_config[idx]):
                        candidate = list(current_config)
                        candidate[idx] = neighbour_value
                        neighbours.append(tuple(candidate))

                if not neighbours:
                    break

                best_candidate_result: TrialMetrics | None = None
                best_candidate_config: tuple[int, int, int, int, int] | None = None
                for config in neighbours:
                    result = evaluate(config)
                    if best_candidate_result is None or is_better(result, best_candidate_result):
                        best_candidate_result = result
                        best_candidate_config = config

                if best_candidate_result is None or best_candidate_config is None:
                    break
                if not is_better(best_candidate_result, current_result):
                    break

                current_config = best_candidate_config
                current_result = best_candidate_result

            if best_overall is None or is_better(current_result, best_overall):
                best_overall = current_result

        best = best_overall or choose_best(results)
        if best is None:
            log("No valid trials were completed.")
            return

        log("\n=== Best configuration ===")
        weights = best.weights
        log(
            f"draws={best.draws}/{best.hands_played} ({best.draw_rate * 100:.2f}%) | "
            f"wins={best.wins} (tsumo={best.tsumo_wins}, ron={best.ron_wins}) | "
            f"seed={best.seed}"
        )
        log(
            "HeuristicWeights("
            f"structure_weight={weights.structure_weight / best.weight_scale if best.weight_scale else weights.structure_weight:.2f}, "
            f"bad_shape_weight={weights.bad_shape_weight / best.weight_scale if best.weight_scale else weights.bad_shape_weight:.2f}, "
            f"isolated_weight={((weights.isolated_weight / best.weight_scale) if best.weight_scale else weights.isolated_weight):.2f}, "
            f"isolated_cap={weights.isolated_cap}, "
            f"availability_weight={weights.availability_weight / best.weight_scale if best.weight_scale else weights.availability_weight:.2f})"
        )

        json_out: Path | None = getattr(args, "json_out", None)
        if json_out:
            payload = [asdict(result) for result in results]
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            log(f"Trial metrics written to {json_out}")
    finally:
        if progress_cm is not None:
            progress_cm.__exit__(None, None, None)


if __name__ == "__main__":
    main()
