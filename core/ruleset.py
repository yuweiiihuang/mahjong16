"""Ruleset definitions for the Taiwan 16-tile Mahjong environment.

Use this dataclass to configure environment behavior, including action toggles,
dead-wall reservation mode, scoring profile injection, and rule profile presets.
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


_RULE_PROFILE_KEYS = {
    "include_flowers",
    "dead_wall_mode",
    "dead_wall_base",
    "scoring_overrides_path",
    "randomize_seating_and_dealer",
    "enable_wind_flower_scoring",
    "enable_flower_wins",
}


@dataclass
class Ruleset:
    """Game rules configuration used by `Mahjong16Env`.

    Attributes:
      include_flowers: Whether to include flowers in the wall and auto-replace.
      n_players: Number of players (default 4).
      initial_hand: Initial concealed tiles per player (16 for Taiwan variant).
      max_rounds: Max number of rounds (not enforced by core env yet).
      allow_chi/pong/gang/hu/zimo/ting: Action toggles.
      dead_wall_mode: 'fixed' or 'gang_plus_one' (one extra reserved per gang).
      dead_wall_base: Base reserved tiles for the dead wall (commonly 16).
      scoring_profile: Key used to load a scoring table from JSON.
      rule_profile: Key used to load rule toggles (winds, flowers, overrides) from JSON.
      base_points: Flat amount each opponent pays before multiplying tai.
      tai_points: Monetary value per tai point.
      scoring_overrides_path: Optional explicit scoring JSON path (defaults from rule profile).
      randomize_seating_and_dealer: Randomize seat winds/dealer (defaults from rule profile).
      enable_wind_flower_scoring: Enable wind/flower scoring (defaults from rule profile).
      enable_flower_wins: Enable flower auto-win detection (defaults from rule profile).
    """
    include_flowers: bool | None = None
    n_players: int = 4
    initial_hand: int = 16
    max_rounds: int = 1

    # 動作開關
    allow_chi: bool = True
    allow_pong: bool = True
    allow_gang: bool = True
    allow_hu: bool = True
    allow_zimo: bool = True
    allow_ting: bool = True

    # 尾牌留置（流局）設定
    # - fixed: 固定留 N 張（預設 16）
    # - gang_plus_one: 以 base 為底，每有 1 次槓增加 1 張留置（俗稱「一槓一」）
    dead_wall_mode: str | None = None   # "fixed" | "gang_plus_one"
    dead_wall_base: int | None = None   # 台灣常見：尾牌留 16 張

    # ====== 新增：混合式台數計算設定 ======
    scoring_profile: str = "taiwan_base"
    rule_profile: str = "common"
    base_points: int = 100
    tai_points: int = 20
    # 風位/莊家與花牌相關設定（預設由 rule_profile 提供，可個別覆寫）
    # - randomize_seating_and_dealer: True 時，重置時隨機莊家與門風座位
    # - enable_wind_flower_scoring: True 時，開啟圈風/門風/正花/花槓等台數計算
    # - enable_flower_wins: True 時，啟用七搶一／八仙過海的自動結算判斷
    scoring_overrides_path: str | None = None
    randomize_seating_and_dealer: bool | None = None
    enable_wind_flower_scoring: bool | None = None
    enable_flower_wins: bool | None = None

    def __post_init__(self) -> None:
        profile_name = (self.rule_profile or "common").strip() or "common"
        profile = {}
        try:
            profile = load_rule_profile(profile_name)
        except FileNotFoundError:
            if profile_name != "common":
                profile = load_rule_profile("common")

        profile_include = profile.get("include_flowers")
        if self.include_flowers is None:
            self.include_flowers = _coerce_bool(profile_include, True)
        else:
            self.include_flowers = _coerce_bool(self.include_flowers, True)

        profile_dead_wall_mode = profile.get("dead_wall_mode")
        if self.dead_wall_mode is None:
            self.dead_wall_mode = _coerce_dead_wall_mode(profile_dead_wall_mode, "fixed")
        else:
            self.dead_wall_mode = _coerce_dead_wall_mode(self.dead_wall_mode, "fixed")

        profile_dead_wall_base = profile.get("dead_wall_base")
        if self.dead_wall_base is None:
            self.dead_wall_base = _coerce_int(profile_dead_wall_base, 16)
        else:
            self.dead_wall_base = _coerce_int(self.dead_wall_base, 16)

        if self.scoring_overrides_path is None:
            raw_override = profile.get("scoring_overrides_path")
            self.scoring_overrides_path = _clean_optional_str(raw_override)
        else:
            self.scoring_overrides_path = _clean_optional_str(self.scoring_overrides_path)

        profile_randomize = profile.get("randomize_seating_and_dealer")
        if self.randomize_seating_and_dealer is None:
            self.randomize_seating_and_dealer = _coerce_bool(profile_randomize, True)
        else:
            self.randomize_seating_and_dealer = _coerce_bool(self.randomize_seating_and_dealer, True)

        profile_wind_scoring = profile.get("enable_wind_flower_scoring")
        if self.enable_wind_flower_scoring is None:
            self.enable_wind_flower_scoring = _coerce_bool(profile_wind_scoring, True)
        else:
            self.enable_wind_flower_scoring = _coerce_bool(self.enable_wind_flower_scoring, True)

        profile_flower_wins = profile.get("enable_flower_wins")
        if self.enable_flower_wins is None:
            self.enable_flower_wins = _coerce_bool(profile_flower_wins, True)
        else:
            self.enable_flower_wins = _coerce_bool(self.enable_flower_wins, True)


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _coerce_dead_wall_mode(value: Any, default: str) -> str:
    valid = {"fixed", "gang_plus_one"}
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in valid:
            return candidate
    elif value is not None:
        candidate = str(value).strip().lower()
        if candidate in valid:
            return candidate
    base = default.strip().lower() if isinstance(default, str) else ""
    return base if base in valid else "fixed"


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return int(default)
    if isinstance(value, bool):
        return int(value)
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return int(default)
    return candidate


@lru_cache(maxsize=16)
def load_rule_profile(profile_name: str) -> dict[str, Any]:
    profile_key = (profile_name or "common").strip() or "common"
    candidates = _candidate_rule_paths(profile_key)
    seen: set[Path] = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue
        profile = _extract_rule_profile(data, profile_key)
        if isinstance(profile, Mapping):
            return dict(profile)
    raise FileNotFoundError(f"Rule profile '{profile_key}' not found under configs/rules/profiles.")


def _candidate_rule_paths(profile_name: str) -> list[Path]:
    root = _project_root()
    configs_dir = root / "configs"
    rules_dir = configs_dir / "rules"
    profiles_dir = rules_dir / "profiles"
    paths = [profiles_dir / f"{profile_name}.json", rules_dir / f"{profile_name}.json"]
    if profile_name != "common":
        paths.extend([
            profiles_dir / "common.json",
            rules_dir / "common.json",
        ])
    # Legacy fallback (flat configs/<profile>.json) for early exports
    paths.append(configs_dir / f"{profile_name}.json")
    if profile_name != "common":
        paths.append(configs_dir / "common.json")
    return paths


def _extract_rule_profile(data: Any, profile_name: str) -> Mapping[str, Any] | None:
    if isinstance(data, Mapping):
        profiles = data.get("profiles")
        if isinstance(profiles, Mapping):
            candidate = profiles.get(profile_name)
            if isinstance(candidate, Mapping):
                return candidate
        direct = data.get(profile_name)
        if isinstance(direct, Mapping):
            return direct
        if data.keys() and set(map(str, data.keys())).issubset(_RULE_PROFILE_KEYS):
            return data
    return None


def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parent.parent
    except Exception:
        return Path.cwd()
