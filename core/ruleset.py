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
    allow_ting: bool = True

    # 尾牌留置（流局）設定
    # - fixed: 固定留 N 張（預設 16）
    # - gang_plus_one: 以 base 為底，每有 1 次槓增加 1 張留置（俗稱「一槓一」）
    dead_wall_mode: str = "fixed"   # "fixed" | "gang_plus_one"
    dead_wall_base: int = 16        # 台灣常見：尾牌留 16 張

    # ====== 新增：混合式台數計算設定 ======
    scoring_profile: str = "taiwan_base"
    # 是否採用見花見字（影響部份台型的定義；預設 True 以符合一般台灣 16 張）
    see_flower_see_wind: bool = True
    # 外部 JSON 覆蓋檔路徑（可為 None；若提供則優先）
    scoring_overrides_path: str | None = None
