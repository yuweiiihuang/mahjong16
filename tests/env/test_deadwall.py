from core import Mahjong16Env
from core.ruleset import Ruleset

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
    t = env.players[pid]["hand"][0]
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
    # 讓牆剩 17 張；反應中產生 1 槓 → 補摸時也應因 16+1=17 留置而流局
    env.wall = env.wall[:17]
    # 使 P1 對 P0 的棄牌可大明槓
    for p in env.players:
        p["melds"].clear()
    X = env.players[1]["hand"][0]
    need = 3 - env.players[1]["hand"].count(X)
    i = 0
    while need > 0 and i < len(env.players[1]["hand"]):
        if env.players[1]["hand"][i] != X:
            env.players[1]["hand"][i] = X
            need -= 1
        i += 1
    if X not in env.players[0]["hand"]:
        env.players[0]["hand"][0] = X
    # P0 丟 X → P1 宣告 GANG → 其他 PASS
    obs, _, _, _ = env.step({"type": "DISCARD", "tile": X, "from": "hand"})
    obs, _, _, _ = env.step({"type": "GANG"})
    obs, _, _, _ = env.step({"type": "PASS"})
    obs, _, done, _ = env.step({"type": "PASS"})
    assert done, "因一槓一（16+1）而無法補摸，應流局"
