from sdk import Mahjong16Env, Ruleset, Tile
from tests.helpers.tile_pool import TilePool

def test_deadwall_fixed_flow():
    # 固定留 16 張：當牆剩下 16 張時，下一家無法摸牌應流局
    env = Mahjong16Env(
        Ruleset(include_flowers=False, dead_wall_mode="fixed", dead_wall_base=16),
        seed=1,
    )
    env.reset()
    # 直接把牆縮到 16 張，模擬無人宣告 → 下一家摸不到就流局
    env.wall = env.wall[:16]
    pid = env.turn
    t = env.players[pid].hand[0]
    obs, _, _, _ = env.step({"type": "DISCARD", "tile": t, "from": "hand"})
    # 三家 PASS
    obs, _, _, _ = env.step({"type": "PASS"})
    obs, _, _, _ = env.step({"type": "PASS"})
    obs, rew, done, _ = env.step({"type": "PASS"})
    assert done, "應因尾牌留置而流局"
    assert sum(rew) == 0  # 樣板結算：流局全 0

def test_deadwall_gang_plus_one():
    # 一槓一：base=16，每有 1 槓增加 1 留置
    env = Mahjong16Env(
        Ruleset(include_flowers=False, dead_wall_mode="gang_plus_one", dead_wall_base=16),
        seed=2,
    )
    env.reset()
    for player in env.players:
        player.hand.clear()
        player.melds.clear()
        player.river.clear()
        player.flowers.clear()
        player.drawn = None

    env.phase = "TURN"
    env.turn = 0
    env.last_discard = None

    pool = TilePool(include_flowers=False)
    X = Tile.B1
    env.players[0].hand = pool.take([
        X,
        Tile.W1, Tile.W2, Tile.W3, Tile.W4,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.B2, Tile.B3, Tile.B4, Tile.B5,
        Tile.E, Tile.S, Tile.W, Tile.N,
    ])
    env.players[1].hand = pool.take([
        X, X, X,
        Tile.W5, Tile.W6, Tile.W7, Tile.W8,
        Tile.D4, Tile.D5, Tile.D6, Tile.D7, Tile.D8,
        Tile.B2, Tile.B3,
        Tile.E, Tile.S,
    ])
    env.players[2].hand = pool.take([
        Tile.W6, Tile.W7, Tile.W8, Tile.W9,
        Tile.D9, Tile.D1, Tile.D2, Tile.D3,
        Tile.B4, Tile.B5, Tile.B6, Tile.B7,
        Tile.C, Tile.F, Tile.P, Tile.N,
    ])
    env.players[3].hand = pool.take([
        Tile.W1, Tile.W2, Tile.W3, Tile.W4,
        Tile.D4, Tile.D5, Tile.D6, Tile.D7,
        Tile.B6, Tile.B7, Tile.B8, Tile.B9,
        Tile.E, Tile.S, Tile.W, Tile.P,
    ])

    env.wall = pool.remaining()
    # 讓牆剩 17 張；反應中產生 1 槓 → 補摸時也應因 16+1=17 留置而流局
    env.wall = env.wall[:17]
    # P0 丟 X → P1 宣告 GANG → 其他 PASS
    obs, _, _, _ = env.step({"type": "DISCARD", "tile": int(X), "from": "hand"})
    obs, _, _, _ = env.step({"type": "GANG"})
    obs, _, _, _ = env.step({"type": "PASS"})
    obs, _, done, _ = env.step({"type": "PASS"})
    assert done, "因一槓一（16+1）而無法補摸，應流局"
