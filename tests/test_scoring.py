import pytest

from core import Mahjong16Env, Ruleset
from core.judge import settle_scores_stub
from core.tiles import tile_to_str


def _tid(label: str) -> int:
    """以 tile_to_str 反查牌面字串的 tile id（純測試用）。"""
    for i in range(128):
        if tile_to_str(i) == label:
            return i
    raise AssertionError(f"Unknown tile label: {label}")


def _fresh_env(include_flowers=True):
    rules = Ruleset(include_flowers=include_flowers, dead_wall_mode="fixed", dead_wall_base=16)
    env = Mahjong16Env(rules, seed=0)
    env.reset()
    return env


def _set_winner_basic(env, pid=0, win_source="RON"):
    env.winner = pid
    env.win_source = win_source
    env.turn = pid
    env.phase = "DONE"
    # 保底欄位
    p = env.players[pid]
    p.setdefault("hand", [])
    p.setdefault("drawn", None)
    p.setdefault("melds", [])
    p.setdefault("flowers", [])
    p.setdefault("river", [])


def test_menqing_tsumo_is_3_only():
    """門清自摸 → 3 台（不再與門清/自摸重複）；避免無字無花+2 介入，手牌放一張風牌。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="TSUMO")
    p = env.players[0]
    p["melds"] = []                 # 門清
    p["flowers"] = []               # 無花
    p["hand"] = [_tid("1W")] * 16 + [_tid("E")]  # 含風牌避免「無字無花+2」
    p["drawn"] = None
    # 非海底
    env.wall = [0] * (env.rules.dead_wall_base + 1)
    rewards = settle_scores_stub(env)
    assert rewards[0] == 3 and sum(rewards) == 3


def test_tsumo_non_closed_is_1():
    """自摸但非門清（有碰/槓）→ +1。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="TSUMO")
    p = env.players[0]
    p["melds"] = [{"type": "PONG", "tiles": [_tid("1W")] * 3}]
    p["flowers"] = []
    p["hand"] = [_tid("2W")] * 17
    env.wall = [0] * (env.rules.dead_wall_base + 10)  # 不是海底
    rewards = settle_scores_stub(env)
    assert rewards[0] == 1


def test_menqing_ron_is_1():
    """門清榮和 → +1。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = []     # 門清
    p["flowers"] = []
    p["hand"] = [_tid("E")] + [_tid("1W")] * 16  # 放風避免無字無花+2
    rewards = settle_scores_stub(env)
    assert rewards[0] == 1


def test_flowers_add_up():
    """見花見台：每張花 +1。"""
    env = _fresh_env(include_flowers=True)
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [{"type": "CHI", "tiles": [_tid("1W"), _tid("2W"), _tid("3W")]}]  # 打破門清，避免 +1 介入
    p["flowers"] = [999, 998, 997]  # 測試只看列表長度，不看實際花編號
    p["hand"] = [_tid("E")] + [_tid("1W")] * 16
    rewards = settle_scores_stub(env)
    assert rewards[0] == 3


def test_wind_and_dragon_pungs_each_plus_one():
    """風刻 +1、三元刻 +1。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [
        {"type": "PONG", "tiles": [_tid("E")] * 3},
        {"type": "PONG", "tiles": [_tid("C")] * 3},  # 中
    ]
    p["flowers"] = []
    p["hand"] = [_tid("1W")] * 17
    rewards = settle_scores_stub(env)
    assert rewards[0] == 2


def test_kong_add_one():
    """槓牌（明槓）+1；本環境未分暗槓，僅驗證 +1。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [{"type": "GANG", "tiles": [_tid("5W")] * 4}]
    p["flowers"] = []
    p["hand"] = [_tid("1W")] * 17
    rewards = settle_scores_stub(env)
    assert rewards[0] == 1


def test_no_honor_no_flower_plus_two():
    """無字無花 +2（整副牌含副露皆無字，且無花）。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = []             # 門清或有無皆可，此處選空
    p["flowers"] = []           # 無花
    # 手牌/副露皆為數牌（萬/筒/條）
    p["hand"] = [_tid("1W")] * 9 + [_tid("1B")] * 4 + [_tid("1D")] * 4
    rewards = settle_scores_stub(env)
    assert rewards[0] == 2


def test_haitei_tsumo_plus_one():
    """海底撈月 +1（最後一張牌自摸）。此例同時應有『自摸 +1』，總計 2。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="TSUMO")
    p = env.players[0]
    p["melds"] = [{"type": "PONG", "tiles": [_tid("1W")] * 3}]  # 打破門清 → 只計自摸1 + 海底1
    p["flowers"] = []
    p["hand"] = [_tid("E")] + [_tid("2W")] * 16  # 放風避免無字無花+2
    # 牆牌數量 = 尾牌留置 → 海底
    reserved = env.rules.dead_wall_base
    env.wall = [0] * reserved
    rewards = settle_scores_stub(env)
    assert rewards[0] == 2
