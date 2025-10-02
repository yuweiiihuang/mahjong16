"""Ruleset definitions for the Taiwan 16-tile Mahjong environment.

Use this dataclass to configure environment behavior, including action toggles,
dead-wall reservation mode, and scoring profile injection.
"""

from __future__ import annotations
from dataclasses import dataclass

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
      base_points: Flat amount each opponent pays before multiplying tai.
      tai_points: Monetary value per tai point.
      see_flower_see_wind: Variant switch for certain rules (placeholder).
      scoring_overrides_path: Optional explicit scoring JSON path.
    """
    include_flowers: bool = True
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
    dead_wall_mode: str = "fixed"   # "fixed" | "gang_plus_one"
    dead_wall_base: int = 16        # 台灣常見：尾牌留 16 張

    # ====== 新增：混合式台數計算設定 ======
    scoring_profile: str = "taiwan_base"
    base_points: int = 100
    tai_points: int = 20
    # 是否採用見花見字（影響部份台型的定義；預設 True 以符合一般台灣 16 張）
    see_flower_see_wind: bool = True
    # 外部 JSON 覆蓋檔路徑（可為 None；若提供則優先）
    scoring_overrides_path: str | None = None

    # 風位/莊家與計分擴充（預設關閉以維持既有測試行為）
    # - randomize_seating_and_dealer: True 時，重置時隨機莊家與門風座位
    # - enable_wind_flower_scoring: True 時，開啟圈風/門風/正花/花槓等台數計算
    randomize_seating_and_dealer: bool = False
    enable_wind_flower_scoring: bool = True
    # - enable_flower_wins: True 時，啟用七搶一／八仙過海的自動結算判斷
    enable_flower_wins: bool = True
