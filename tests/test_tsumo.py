import pytest

from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str


def _tid(label: str) -> int:
    """
    將牌面字串（如 '1W', '9W', 'E', 'C'）轉成專案內部的 tile id。
    透過掃描合理範圍找出對應的 id；若專案 tile 範圍調整，請視需要擴大上限值。
    """
    for i in range(60):
        if tile_to_str(i) == label:
            return i
    raise AssertionError(f"Unknown tile label: {label}")


def _make_tsumo_hand():
    """
    構造一手可自摸的 17 張牌（16 手牌 + 1 drawn）：
    - 五組刻子（各 3 張）：1W, 2W, 3W, 4W, 5W
    - 一對將：9W（手中 1 張，drawn 再補 1 張成對）
    這種「5 刻 + 將」在 16 張台麻視為一般和牌型（5 組面子 + 將 = 17 張）。
    """
    t1 = _tid("1W")
    t2 = _tid("2W")
    t3 = _tid("3W")
    t4 = _tid("4W")
    t5 = _tid("5W")
    pr = _tid("9W")
    hand = [t1] * 3 + [t2] * 3 + [t3] * 3 + [t4] * 3 + [t5] * 3 + [pr]  # 16
    drawn = pr  # 第 17 張，補成將
    return hand, drawn


def test_tsumo_basic():
    """
    目標：驗證在 TURN 階段，當手牌 + drawn 可胡時，legal_actions 會提供 HU，
         且 step({'type':'HU'}) 會正確結束對局並標記勝家。
    """
    rules = Ruleset(
        include_flowers=False,   # 減少花牌干擾（不影響本測試）
        dead_wall_mode="fixed",
        dead_wall_base=16,
    )
    env = Mahjong16Env(rules, seed=0)
    env.reset()

    # 直接設定可自摸的局面
    hand, drawn = _make_tsumo_hand()
    pid = 0
    env.players[pid]["hand"] = list(hand)
    env.players[pid]["drawn"] = drawn
    env.players[pid]["melds"] = []
    env.players[pid]["flowers"] = []
    env.players[pid]["river"] = []
    env.turn = pid
    env.phase = "TURN"

    acts = env.legal_actions()
    assert any(a.get("type") == "HU" for a in acts), f"HU 未出現在合法行動中：{acts}"

    # 執行自摸
    obs, rew, done, info = env.step({"type": "HU"})

    assert done is True, "自摸後應該結束對局（done=True）"
    assert env.winner == pid, "自摸者應被標記為勝家"
    assert env.phase == "DONE", "結束態應為 DONE"
    assert isinstance(rew, list) and len(rew) == rules.n_players, "rewards 需為每位玩家各一個值"
