from core import Mahjong16Env, Ruleset
from core.scoring.engine import compute_payments, score_with_breakdown
from core.scoring.tables import load_scoring_assets
from core.scoring.types import ScoringContext
from core.tiles import tile_to_str


def _tid(label: str) -> int:
    for i in range(128):
        if tile_to_str(i) == label:
            return i
    raise AssertionError(label)


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
        [_tid("1W")] * 4
        + [_tid("2W")] * 4
        + [_tid("3W")] * 4
        + [_tid("4D")] * 3
        + [_tid("E")]
    )
    p0["drawn"] = _tid("E")
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
