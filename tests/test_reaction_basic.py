from core import Mahjong16Env, Ruleset
from core.tiles import Tile

def force_hand(env, pid, tiles, drawn=None):
    env.players[pid]["hand"] = list(tiles)
    env.players[pid]["drawn"] = drawn

def test_priority_pon_over_chi():
    # 建立環境並人工設牌：P0 丟出 5W；P1 有 3W,4W,5W 可吃，P2 有 5W,5W 可碰
    env = Mahjong16Env(Ruleset(include_flowers=False), seed=42)
    env.reset()
    # 清空並設定最小狀態
    for p in env.players:
        p["hand"].clear(); p["drawn"]=None; p["melds"].clear(); p["river"].clear()
    env.wall = []  # 關閉自動摸牌以穩定測試
    # 設定手牌
    force_hand(env, 0, [Tile.W1]*16)  # 不重要
    force_hand(env, 1, [Tile.W3, Tile.W4] + [Tile.W1]*14)  # 可吃 3-4-5
    force_hand(env, 2, [Tile.W5, Tile.W5] + [Tile.W1]*14)  # 可碰
    force_hand(env, 3, [Tile.W1]*16)
    env.phase = "TURN"; env.turn = 0; env.last_discard = None
    # P0 模擬丟 5W
    env.players[0]["hand"][0] = Tile.W5
    obs, _, _, _ = env.step({"type":"DISCARD","tile": int(Tile.W5), "from":"hand"})
    # 反應視窗：先到 P1（可 CHI），我們選 CHI；再到 P2（可 PONG），我們也宣告 PONG；P3 PASS
    # P1 選 CHI（3W,4W）
    obs, _, _, _ = env.step({"type":"CHI","use":[int(Tile.W3), int(Tile.W4)]})
    # P2 宣告 PONG
    obs, _, _, _ = env.step({"type":"PONG"})
    # P3 PASS
    obs, _, _, _ = env.step({"type":"PASS"})
    # 結算應選擇 PONG 優先於 CHI，故輪到 P2，且 P2 手上應移除兩張 5W 並新增明刻
    assert env.turn == 2
    melds = env.players[2]["melds"]
    assert any(m.get("type")=="PONG" for m in melds), "應形成明刻（PONG）"
