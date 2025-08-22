
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Ruleset:
    include_flowers: bool = True
    n_players: int = 4
    initial_hand: int = 16
    max_rounds: int = 1
    allow_chi: bool = True
    allow_pon: bool = True
    allow_kan: bool = True
    allow_ron: bool = True
    allow_tsumo: bool = True
    # TODO: 台/番與結算、搶槓、三家付、連莊、風圈等
