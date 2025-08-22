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

def test_discard_then_reaction_window_and_pass_all():
    env = Mahjong16Env(Ruleset(), seed=123)
    obs = env.reset()
    discards = [a for a in obs["legal_actions"] if a["type"] == "DISCARD"]
    assert discards, "必須要有可丟牌的動作"
    a0 = discards[0]
    # 丟牌 -> 進入 REACTION（輪到 P1 回應）
    obs2, rew, done, info = env.step(a0)
    assert obs2["phase"] == "REACTION"
    assert obs2["player"] == 1, "丟牌後應由下家先回應"
    # 三家都 PASS -> 輪到 P1 摸到 drawn，phase 回到 TURN
    obs3, _, _, _ = env.step({"type":"PASS"})
    obs4, _, _, _ = env.step({"type":"PASS"})
    obs5, _, _, _ = env.step({"type":"PASS"})
    assert obs5["phase"] == "TURN"
    assert obs5["player"] == 1
    assert env.players[1]["drawn"] is not None
    assert len(env.players[1]["hand"]) == env.rules.initial_hand
