from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Ruleset:
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

    # 尾牌留置（流局）設定
    # - fixed: 固定留 N 張（預設 16）
    # - gang_plus_one: 以 base 為底，每有 1 次槓增加 1 張留置（俗稱「一槓一」）
    dead_wall_mode: str = "fixed"   # "fixed" | "gang_plus_one"
    dead_wall_base: int = 16        # 台灣常見：尾牌留 16 張
