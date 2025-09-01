from core import Mahjong16Env, Ruleset
from core.tiles import Tile
from core.scoring.tables import load_scoring_assets
from core.scoring.types import ScoringContext
from core.scoring.engine import score_with_breakdown


def force_reset_env(include_flowers=False):
    env = Mahjong16Env(Ruleset(include_flowers=include_flowers), seed=0)
    env.reset()
    # sanitize players
    for p in env.players:
        p["hand"].clear(); p["melds"].clear(); p["river"].clear(); p["flowers"].clear(); p["drawn"] = None
    env.wall = [int(Tile.W9)] * 32  # safe tail for draws
    env.phase = "TURN"
    env.turn = 0
    env.last_discard = None
    return env


def test_angang_action_adds_concealed_kong_and_draws():
    env = force_reset_env(include_flowers=False)
    # P0 has 3x 1W in hand and 1W on drawn → can ANGANG
    p0 = env.players[0]
    p0["hand"] = [int(Tile.W1)] * 3 + [int(Tile.W2)] * 13
    p0["drawn"] = int(Tile.W1)

    # list legal actions should include ANGANG of 1W
    acts = env.legal_actions()
    assert any(a.get("type") == "ANGANG" and a.get("tile") == int(Tile.W1) for a in acts)

    # perform ANGANG
    obs, _, done, _ = env.step({"type": "ANGANG", "tile": int(Tile.W1)})
    assert not done
    # ANGANG meld present with 4x 1W; counts as concealed kong
    mtypes = [m.get("type") for m in env.players[0]["melds"]]
    assert "ANGANG" in mtypes
    tiles = next(m.get("tiles") for m in env.players[0]["melds"] if m.get("type") == "ANGANG")
    assert tiles == [int(Tile.W1)] * 4
    # drew a supplement tile into drawn (we filled wall with W9)
    assert env.players[0]["drawn"] == int(Tile.W9)
    # n_gang incremented
    assert env.n_gang >= 1


def test_kakan_triggers_qiang_gang_and_ron():
    env = force_reset_env(include_flowers=False)
    # P0: already PONG 3D, has the 4th 3D in hand so can KAKAN
    p0 = env.players[0]
    p0["melds"] = [{"type": "PONG", "tiles": [int(Tile.D3)] * 3}]
    # hand: include D3 once plus fillers to 16
    p0["hand"] = [int(Tile.D3)] + [int(Tile.W2)] * 15

    # P1: waiting on D3: W123 W456 W789 D12 D456 + pair E,E (16 tiles)
    p1 = env.players[1]
    p1["hand"] = (
        [int(Tile.W1), int(Tile.W2), int(Tile.W3)] +
        [int(Tile.W4), int(Tile.W5), int(Tile.W6)] +
        [int(Tile.W7), int(Tile.W8), int(Tile.W9)] +
        [int(Tile.D1), int(Tile.D2)] +
        [int(Tile.D4), int(Tile.D5), int(Tile.D6)] +
        [int(Tile.E), int(Tile.E)]
    )

    # P0 declares KAKAN on D3 → opens qiang_gang reaction window
    obs, _, done, _ = env.step({"type": "KAKAN", "tile": int(Tile.D3)})
    assert not done and obs.get("phase") == "REACTION" and obs.get("player") == 1
    # P1 HU (qiang gang)
    obs, _, _, _ = env.step({"type": "HU"})
    # remaining reactors pass to resolve
    obs, _, _, _ = env.step({"type": "PASS"})  # P2
    _, _, done, _ = env.step({"type": "PASS"})  # P3
    assert done
    assert env.winner == 1 and env.win_source == "RON"
    assert getattr(env, "win_by_qiang_gang", False) is True
    # Original PONG should remain (not upgraded)
    mtypes_p0 = [m.get("type") for m in env.players[0]["melds"]]
    assert "PONG" in mtypes_p0 and "KAKAN" not in mtypes_p0


def test_scoring_flags_qiang_gang_and_gang_shang():
    # Build a scoring context to validate flags application without full env flow
    env = Mahjong16Env(Ruleset(include_flowers=False), seed=0)
    env.reset()
    # Winner P0 baseline setup
    pid = 0
    env.winner = pid
    env.turn = pid
    env.phase = "DONE"
    env.players[pid]["melds"] = []
    env.players[pid]["flowers"] = []
    env.players[pid]["river"] = []
    # Case 1: qiang_gang (RON)
    env.win_source = "RON"
    env.win_tile = int(Tile.D3)
    env.win_by_qiang_gang = True
    # Give a trivially valid concealed 17 to avoid other scores
    env.players[pid]["hand"] = [int(Tile.W1), int(Tile.W2), int(Tile.W3), int(Tile.W4), int(Tile.W5), int(Tile.W6), int(Tile.W7), int(Tile.W8), int(Tile.W9), int(Tile.D1), int(Tile.D2), int(Tile.D3), int(Tile.D4), int(Tile.D5), int(Tile.D6), int(Tile.E)]
    env.players[pid]["drawn"] = None
    table = load_scoring_assets(env.rules.scoring_profile, env.rules.scoring_overrides_path)
    rewards, bd = score_with_breakdown(ScoringContext.from_env(env, table))
    # expect qiang_gang contributes positive points per table
    items = [i for i in bd[pid] if i.get("key") == "qiang_gang"]
    assert items and sum(i.get("points", 0) for i in items) == table.get("qiang_gang", 1)

    # Case 2: gang_shang (TSUMO) with menqing via ANGANG only
    env.win_source = "TSUMO"
    env.win_by_qiang_gang = False
    env.win_by_gang_draw = True
    env.players[pid]["melds"] = [{"type": "ANGANG", "tiles": [int(Tile.D7)]*4}]
    env.players[pid]["hand"] = [
        int(Tile.W1), int(Tile.W2), int(Tile.W3),
        int(Tile.W4), int(Tile.W5), int(Tile.W6),
        int(Tile.W7), int(Tile.W8), int(Tile.W9),
        int(Tile.D1), int(Tile.D2), int(Tile.D3),
        int(Tile.E), int(Tile.E)
    ]
    env.players[pid]["drawn"] = int(Tile.D4)
    rewards, bd = score_with_breakdown(ScoringContext.from_env(env, table))
    keys = [i.get("key") for i in bd[pid]]
    assert "gang_shang" in keys
    # 槓上自摸含自摸：不得同時加『自摸』；門清仍可加，但不可使用『門清自摸』
    assert ("menqing" in keys) and ("zimo" not in keys) and ("menqing_zimo" not in keys)
