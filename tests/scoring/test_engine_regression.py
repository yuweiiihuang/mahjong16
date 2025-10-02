from core import Mahjong16Env
from core.ruleset import Ruleset
from core.scoring.engine import compute_payments, score_with_breakdown
from core.scoring.tables import load_scoring_assets
from core.scoring.types import ScoringContext
from core.tiles import Tile


def _prepare_env():
    rules = Ruleset(
        include_flowers=False,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        enable_wind_flower_scoring=False,
    )
    env = Mahjong16Env(rules, seed=7)
    env.reset()
    table = load_scoring_assets(rules.scoring_profile, rules.scoring_overrides_path)
    return env, table


def _set_winner(env, pid=0, source="TSUMO"):
    env.winner = pid
    env.win_source = source
    env.turn = pid
    env.phase = "DONE"
    player = env.players[pid]
    player["hand"] = player.get("hand", [])
    player["drawn"] = None
    player["melds"] = player.get("melds", [])
    player["flowers"] = player.get("flowers", [])
    player["river"] = player.get("river", [])


def test_score_and_payment_consistency_for_menqing_tsumo():
    env, table = _prepare_env()
    _set_winner(env, 0, "TSUMO")
    p0 = env.players[0]
    p0["melds"] = []
    p0["hand"] = (
        [int(Tile.W1)] * 4
        + [int(Tile.W2)] * 4
        + [int(Tile.W3)] * 4
        + [int(Tile.D4)] * 3
        + [int(Tile.E)]
    )
    p0["drawn"] = int(Tile.E)
    env.wall = [0] * (env.rules.dead_wall_base + 5)

    ctx = ScoringContext.from_env(env, table)
    rewards, breakdown = score_with_breakdown(ctx)
    total_from_breakdown = sum(item["points"] for item in breakdown[0])
    assert rewards[0] == total_from_breakdown

    payments, bd = compute_payments(
        ctx,
        env.rules.base_points,
        env.rules.tai_points,
        rewards=rewards,
        breakdown=breakdown,
    )
    assert payments[0] > 0
    assert sum(payments) == 0
    assert bd == breakdown


def _points(breakdown, key: str) -> int:
    for item in breakdown:
        if item["key"] == key:
            return item["points"]
    return 0


def test_peng_peng_hu_breakdown_matches_table():
    env, table = _prepare_env()
    _set_winner(env, 0, "TSUMO")

    p0 = env.players[0]
    p0["flowers"] = []
    p0["melds"] = []
    p0["hand"] = (
        [int(Tile.W1)] * 3
        + [int(Tile.W2)] * 3
        + [int(Tile.D3)] * 3
        + [int(Tile.D4)] * 3
        + [int(Tile.B5)] * 3
        + [int(Tile.W9)]
    )
    p0["drawn"] = int(Tile.W9)
    env.wall = [int(Tile.W9)] * (env.rules.dead_wall_base + 4)

    ctx = ScoringContext.from_env(env, table)
    rewards, breakdown = score_with_breakdown(ctx)
    bd0 = breakdown[0]

    assert _points(bd0, "peng_peng_hu") == table.get("peng_peng_hu", 0)
    assert _points(bd0, "ping_hu") == 0
    assert rewards[0] >= table.get("peng_peng_hu", 0)
