
from core import Mahjong16Env, Ruleset

def test_reset_and_deal():
    env = Mahjong16Env(Ruleset(), seed=123)
    obs = env.reset()
    # 每家 16 張手牌
    for i, p in enumerate(env.players):
        assert len(p["hand"]) == env.rules.initial_hand
        if i == 0:
            assert p["drawn"] is not None, "莊家開局應有 drawn（一張第17張）"
        else:
            assert p["drawn"] is None, "閒家開局不應有 drawn"
    # 當前行動必為莊家
    assert obs["player"] == 0
    # 合法動作應包含丟 drawn
    assert any(a["type"]=="DISCARD" and a.get("from")=="drawn" for a in obs["legal_actions"])

def test_step_discard_and_turn():
    env = Mahjong16Env(Ruleset(), seed=123)
    obs = env.reset()
    discards = [a for a in obs["legal_actions"] if a["type"] == "DISCARD"]
    assert discards, "必須要有可丟牌的動作"
    a0 = discards[0]
    obs2, rew, done, info = env.step(a0)
    # 輪轉至 P1，且 P1 應該已經摸到 drawn
    assert obs2["player"] == 1
    assert env.players[1]["drawn"] is not None
    assert len(env.players[1]["hand"]) == env.rules.initial_hand
    # P0 丟牌後不應有 drawn，且仍維持 16 張手牌
    assert env.players[0]["drawn"] is None
    assert len(env.players[0]["hand"]) == env.rules.initial_hand
