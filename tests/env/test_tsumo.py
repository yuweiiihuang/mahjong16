from domain import Mahjong16Env
from domain.rules import Ruleset
from domain.tiles import Tile


def _make_tsumo_hand() -> tuple[list[int], int]:
    """構造一手以刻子組成的自摸牌型，避免依賴字串查表。"""

    hand = (
        [int(Tile.W1)] * 3
        + [int(Tile.W2)] * 3
        + [int(Tile.W3)] * 3
        + [int(Tile.W4)] * 3
        + [int(Tile.W5)] * 3
        + [int(Tile.W9)]
    )
    drawn = int(Tile.W9)
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
    env.players[pid].hand = list(hand)
    env.players[pid].drawn = drawn
    env.players[pid].melds = []
    env.players[pid].flowers = []
    env.players[pid].river = []
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
