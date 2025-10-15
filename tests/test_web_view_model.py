from domain import Mahjong16Env, Ruleset

from ui.web.bridge import WebSessionBridge
from ui.web.view_model import build_action_prompt, build_table_state


def _make_env(seed: int = 7) -> Mahjong16Env:
    rules = Ruleset(scoring_profile="taiwan_base", rule_profile="common")
    return Mahjong16Env(rules, seed=seed)


def test_build_table_state_produces_player_panels() -> None:
    env = _make_env()
    obs = env.reset()
    state = build_table_state(
        env,
        pov_pid=obs["player"],
        score_state={"totals": [1000] * env.rules.n_players, "deltas": [0] * env.rules.n_players},
    )
    assert "players" in state
    assert len(state["players"]) == env.rules.n_players
    assert state["status"]["remaining"] == len(env.wall)


def test_build_action_prompt_matches_legal_actions() -> None:
    env = _make_env()
    obs = env.reset()
    prompt, lookup = build_action_prompt(obs)
    assert prompt["player"] == obs["player"]
    assert len(prompt["actions"]) == len(obs["legal_actions"])
    for item in prompt["actions"]:
        assert item["id"] in lookup


def test_web_session_bridge_roundtrip() -> None:
    bridge = WebSessionBridge()
    bridge.update_base_state({"status": {}, "players": []})
    request = {
        "player": 0,
        "phase": "TURN",
        "actions": [{"id": "a0", "label": "PASS"}],
    }
    serial = bridge.prepare_pending(request, {"a0": {"type": "PASS"}})
    state = bridge.latest_state()
    assert state is not None
    assert state["pending_request"]["serial"] == serial
    bridge.submit_action(serial=serial, action_id="a0")
    action = bridge.wait_for_action()
    assert action["type"] == "PASS"
