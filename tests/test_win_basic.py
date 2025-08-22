from core import Mahjong16Env, Ruleset
from core.judge import is_win_16
from core.tiles import Tile  # 假設有 W1..W9, D1..D9, B1..B9, 以及 E/S/W/N/C/F/P

def test_is_win_simple_all_chows():
    # W123 W456 W789 D123 D456 + 將(E,E) = 5面子+眼睛 → 胡
    tiles = [
        int(Tile.W1), int(Tile.W2), int(Tile.W3),
        int(Tile.W4), int(Tile.W5), int(Tile.W6),
        int(Tile.W7), int(Tile.W8), int(Tile.W9),
        int(Tile.D1), int(Tile.D2), int(Tile.D3),
        int(Tile.D4), int(Tile.D5), int(Tile.D6),
        int(Tile.E), int(Tile.E),
    ]
    assert is_win_16(tiles, [], Ruleset(include_flowers=False)) is True

def test_is_win_false_missing_one_tile():
    # 少一張 D6 → 無法達成 5 組面子
    tiles = [
        int(Tile.W1), int(Tile.W2), int(Tile.W3),
        int(Tile.W4), int(Tile.W5), int(Tile.W6),
        int(Tile.W7), int(Tile.W8), int(Tile.W9),
        int(Tile.D1), int(Tile.D2), int(Tile.D3),
        int(Tile.D4), int(Tile.D5),
        int(Tile.E), int(Tile.E),
    ]
    assert is_win_16(tiles, [], Ruleset(include_flowers=False)) is False

def test_is_win_with_existing_melds():
    # 先算 1 組已完成面子（PONG W9），剩下手牌需是 4 面子 + 眼睛
    melds = [{"type": "PONG", "tiles": [int(Tile.W9)]*3}]
    tiles = [
        int(Tile.W1), int(Tile.W2), int(Tile.W3),
        int(Tile.W4), int(Tile.W5), int(Tile.W6),
        int(Tile.D1), int(Tile.D2), int(Tile.D3),
        int(Tile.D4), int(Tile.D5), int(Tile.D6),
        int(Tile.E), int(Tile.E),
    ]  # 4 組順 + 眼睛
    assert is_win_16(tiles, melds, Ruleset(include_flowers=False)) is True
