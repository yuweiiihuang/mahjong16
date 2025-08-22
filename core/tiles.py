
from __future__ import annotations
from enum import IntEnum
import random
from typing import List

# 0..33: 34 張（萬、筒、條 各1-9；字牌 東南西北中發白）
# 34..41: 8 張花牌（四季 + 四君子）
N_TILES = 34
N_FLOWERS = 8

class Tile(IntEnum):
    W1,W2,W3,W4,W5,W6,W7,W8,W9,     D1,D2,D3,D4,D5,D6,D7,D8,D9,     B1,B2,B3,B4,B5,B6,B7,B8,B9,     E,S,W,N,C,F,P = range(N_TILES)

def is_flower(x: int) -> bool:
    return x >= N_TILES and x < N_TILES + N_FLOWERS

def flower_ids() -> List[int]:
    return list(range(N_TILES, N_TILES + N_FLOWERS))

def full_wall(include_flowers: bool=True, rng: random.Random|None=None) -> List[int]:
    r = rng if rng else random
    wall: List[int] = []
    for t in range(N_TILES):
        wall += [t]*4
    if include_flowers:
        wall += flower_ids()  # 四季四君子各1
    r.shuffle(wall)
    return wall

def tile_to_str(t: int) -> str:
    if is_flower(t):
        return f"F{t - N_TILES + 1}"
    names = [
        *[f"{i+1}W" for i in range(9)],
        *[f"{i+1}D" for i in range(9)],
        *[f"{i+1}B" for i in range(9)],
        "E","S","W","N","C","F","P"
    ]
    return names[int(t)]

def hand_to_str(hand: List[int]) -> str:
    return " ".join(sorted([tile_to_str(t) for t in hand]))
