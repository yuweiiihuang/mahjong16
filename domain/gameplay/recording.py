"""Private, versioned hand records and deterministic offline verification.

These records include concealed tiles. They must never be used as browser snapshots.
Storage, player identity and research observation exports belong to later adapters.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from ..rules.ruleset import Ruleset
from ..scoring.engine import compute_payments, score_with_breakdown
from ..scoring.lookup import load_scoring_assets
from ..scoring.score_types import ScoringContext, ScoringTable
from ..tiles import N_TILES, flower_ids

if TYPE_CHECKING:
    from .game_env import MahjongEnvironment

FORMAT_VERSION = 1
STATE_FIELDS = (
    "wall", "discard_pile", "discard_count", "total_open_melds", "flower_win_type",
    "n_gang", "reaction_queue", "reaction_idx", "claims", "reaction_responses",
    "last_discard", "done", "winner", "win_source", "win_tile", "turn_at_win",
    "win_by_gang_draw", "win_by_qiang_gang", "_recent_gang_draw_pid", "qiang_gang_mode",
    "pending_kakan", "_public_live", "seat_winds", "seating_order", "_seat_index",
    "dealer_pid", "quan_feng", "dealer_streak", "winner_is_dealer", "turn", "phase",
)


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _turn_action(action: dict) -> dict:
    """Compare turn semantics without optional display fields, using engine defaults."""
    result = dict(action)
    if result.get("type") in ("DISCARD", "TING"):
        result.setdefault("from", "hand")
    if result.get("type") == "TING":
        result.pop("waits", None)
    if result.get("type") == "HU":
        result.setdefault("source", "TSUMO")
    return result


def engine_version() -> str:
    """Identify actual domain code, including uncommitted changes and scoring logic."""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def private_state(env: MahjongEnvironment) -> dict:
    """Return all round state needed to detect replay divergence, without RNG or callbacks."""
    state = {key: getattr(env, key) for key in STATE_FIELDS}
    state["players"] = [player.as_dict() for player in env.players]
    state["flower_sets"] = [sorted(items) for items in env._flower_manager.player_sets]
    state["flower_union"] = sorted(env._flower_manager.union)
    return _json_copy(state)


def _settlement(env: MahjongEnvironment, table: ScoringTable) -> dict | None:
    if not env.done:
        return None
    ctx = ScoringContext.from_env(env, table)
    tai, breakdown = score_with_breakdown(ctx)
    payments, _ = compute_payments(
        ctx, env.rules.base_points, env.rules.tai_points, rewards=tai, breakdown=breakdown,
    )
    return _json_copy({
        "winner": env.winner, "win_source": env.win_source, "win_tile": env.win_tile,
        "flower_win_type": env.flower_win_type, "tai": tai,
        "breakdown": breakdown, "payments": payments,
    })


class HandRecorder:
    """Capture accepted steps in memory; callers explicitly export each private record.

    ponytail: retain records in memory for offline verification; use the planned SQLite
    adapter before enabling persistent recording on the public server.
    """

    def __init__(self) -> None:
        self.records: list[dict] = []
        self._table: ScoringTable | None = None
        self._window = 0

    def begin(self, env: MahjongEnvironment) -> None:
        """Capture the complete shuffled wall before dealing, including flower draws."""
        self._table = load_scoring_assets(
            env.rules.scoring_profile, env.rules.scoring_overrides_path,
        )
        self._window = 0
        self.records.append({
            "format_version": FORMAT_VERSION, "engine_version": engine_version(),
            "hand_id": str(uuid4()), "rules": asdict(env.rules),
            "scoring": asdict(self._table), "seed": env.reset_rng_seed,
            "setup": {"wall": list(env.wall), "seat_winds": list(env.seat_winds),
                      "dealer_pid": env.dealer_pid, "quan_feng": env.quan_feng,
                      "dealer_streak": env.dealer_streak},
            "steps": [], "status": "incomplete", "settlement": None,
        })

    def initialized(self, env: MahjongEnvironment) -> None:
        record = self.records[-1]
        record["initial_state"] = private_state(env)
        record["final_hash"] = _digest(record["initial_state"])
        self._finish(env)

    def before_step(self, env: MahjongEnvironment, action: dict, pid: int | None) -> dict:
        """Freeze the actual actor and order before simultaneous responses are resolved."""
        if not self.records or _digest(private_state(env)) != self.records[-1]["final_hash"]:
            raise ValueError("牌局狀態在紀錄步驟之外被修改。")
        actor = (env.turn if env.phase == "TURN" else
                 env.reaction_queue[env.reaction_idx]) if pid is None else pid
        legal = env.legal_actions(actor)
        if env.phase == "TURN":
            valid = _turn_action(action) in [_turn_action(candidate) for candidate in legal]
        else:
            valid = action in legal
        if not valid:
            raise ValueError("不能記錄非法操作。")
        return {"seq": len(self.records[-1]["steps"]) + 1, "pid": actor,
                "phase": env.phase, "window": self._window if env.phase == "REACTION" else None,
                "action": deepcopy(action), "pending_before": env.pending_reactions(),
                "before_hash": self.records[-1]["final_hash"]}

    def after_step(self, env: MahjongEnvironment, step: dict, result: tuple) -> None:
        """Keep both submitted choices and the result; unanswered seats are not passes."""
        _, rewards, done, info = result
        if step["phase"] != "REACTION" and env.phase == "REACTION":
            self._window += 1
        closed = step["phase"] == "REACTION" and env.phase != "REACTION"
        step.update({"after_hash": _digest(private_state(env)), "rewards": list(rewards),
                     "done": done, "info": deepcopy(info),
                     "unanswered": ([pid for pid in step["pending_before"] if pid != step["pid"]]
                                    if closed else None)})
        record = self.records[-1]
        record["steps"].append(step)
        record["final_hash"] = step["after_hash"]
        self._finish(env)

    def _finish(self, env: MahjongEnvironment) -> None:
        if env.done:
            self.records[-1]["status"] = "completed"
            self.records[-1]["settlement"] = _settlement(env, self._table)

    def document(self) -> dict:
        """Return an independent JSON-compatible copy of the latest hand."""
        if not self.records:
            raise ValueError("尚未開始紀錄牌局。")
        return _json_copy(self.records[-1])


def replay_hand(document: dict) -> MahjongEnvironment:
    """Verify version, initial deal, every accepted step and final scoring.

    Raise ValueError on incompatible or malformed records; never deserialize executable objects.
    Incomplete records verify only their captured prefix and are not declared finished.
    """
    from .game_env import MahjongEnvironment

    try:
        if document["format_version"] != FORMAT_VERSION:
            raise ValueError("不支援的牌譜格式版本。")
        if document["engine_version"] != engine_version():
            raise ValueError("牌譜與目前引擎版本不同。")
        rules = Ruleset(**document["rules"])
        if asdict(rules) != document["rules"]:
            raise ValueError("牌譜規則設定無法完整還原。")
        wall = document["setup"]["wall"]
        expected = Counter({tile: 4 for tile in range(N_TILES)})
        if rules.include_flowers:
            expected.update(flower_ids())
        if (not isinstance(wall, list) or any(type(tile) is not int for tile in wall)
                or Counter(wall) != expected):
            raise ValueError("牌牆內容不合法。")
        table = ScoringTable(**document["scoring"])

        class ReplayEnvironment(MahjongEnvironment):
            def _reset_round_state(self) -> None:
                super()._reset_round_state()
                self.wall = list(wall)

        env = ReplayEnvironment(rules, seed=0)
        for key in ("seat_winds", "dealer_pid", "quan_feng", "dealer_streak"):
            setattr(env, f"preset_{key}", deepcopy(document["setup"][key]))
        env.reset()
        if private_state(env) != document["initial_state"]:
            raise ValueError("初始發牌狀態不一致。")
        # Use the same recorder to verify ancillary fields, not just the selected action.
        recorder = HandRecorder()
        recorder.records = [{"steps": [], "final_hash": _digest(private_state(env)),
                             "status": "incomplete", "settlement": None}]
        recorder._table = table
        recorder._finish(env)
        env.recorder = recorder
        for step in document["steps"]:
            if type(step["pid"]) is not int or not 0 <= step["pid"] < rules.n_players:
                raise ValueError("牌譜座位不合法。")
            env.step(deepcopy(step["action"]), pid=step["pid"])
            if _json_copy(recorder.records[-1]["steps"][-1]) != step:
                raise ValueError(f"第 {step['seq']} 步紀錄不一致。")
        record = recorder.records[-1]
        for key in ("status", "settlement", "final_hash"):
            if record[key] != document[key]:
                raise ValueError(f"牌譜 {key} 不一致。")
        env.recorder = None
        return env
    except (KeyError, TypeError, AssertionError, IndexError, AttributeError) as exc:
        raise ValueError(f"無效牌譜：{exc}") from exc
