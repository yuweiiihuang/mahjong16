import pytest

from domain import Mahjong16Env
from domain.rules import Ruleset
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.lookup import load_scoring_assets
from domain.scoring.score_types import ScoringContext, ScoringTable
from domain.tiles import Tile
from tests.helpers.tile_pool import TilePool


def _prepare_env():
    rules = Ruleset(
        include_flowers=False,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        enable_wind_flower_scoring=False,
    )
    env = Mahjong16Env(rules, seed=7)
    env.reset()
    for player in env.players:
        player.hand.clear()
        player.melds.clear()
        player.flowers.clear()
        player.river.clear()
        player.drawn = None
    env.wall = TilePool(include_flowers=rules.include_flowers).remaining()
    table = load_scoring_assets(rules.scoring_profile, rules.scoring_overrides_path)
    return env, table


@pytest.mark.parametrize("source,winner,payer,streak,tai,expected", [
    ("TSUMO", 2, None, 0, 2, [-140, -160, 440, -140]),
    ("RON", 2, 0, 0, 2, [-140, 0, 140, 0]),
    ("RON", 2, 1, 0, 2, [0, -160, 160, 0]),
    ("TSUMO", 2, None, 2, 2, [-140, -240, 520, -140]),
    ("RON", 2, 1, 2, 2, [0, -240, 240, 0]),
    # Dealer's five bonus tai are already included in the winner's seven tai.
    ("TSUMO", 1, None, 2, 7, [-240, 720, -240, -240]),
    ("RON", 1, 2, 2, 7, [0, 240, -240, 0]),
])
def test_payments_apply_base_tai_and_dealer_bonus_once(
    source, winner, payer, streak, tai, expected,
):
    ctx = ScoringContext(
        rules=Ruleset(), players=[], winner=winner, win_source=source,
        win_tile=None, last_discard=None, turn_at_win=payer, wall_len=0, n_gang=0,
        table=ScoringTable(values={}, labels={}), dealer_pid=1, dealer_streak=streak,
    )
    rewards = [0] * 4
    rewards[winner] = tai
    breakdown = {pid: [] for pid in range(4)}
    breakdown[winner] = [{"key": "fixture", "points": tai}]

    payments, returned_breakdown = compute_payments(
        ctx, 100, 20, rewards=rewards, breakdown=breakdown,
    )
    assert payments == expected
    assert returned_breakdown == breakdown


def _points(breakdown, key: str) -> int:
    for item in breakdown:
        if item["key"] == key:
            return item["points"]
    return 0


def test_peng_peng_hu_breakdown_matches_table():
    env, table = _prepare_env()
    env.winner = 0
    env.win_source = "TSUMO"

    p0 = env.players[0]
    p0.flowers = []
    p0.melds = []
    pool = TilePool(include_flowers=False)
    p0.hand = pool.take(
        [
            Tile.W1, Tile.W1, Tile.W1,
            Tile.W2, Tile.W2, Tile.W2,
            Tile.D3, Tile.D3, Tile.D3,
            Tile.D4, Tile.D4, Tile.D4,
            Tile.B5, Tile.B5, Tile.B5,
            Tile.W9,
        ]
    )
    p0.drawn = pool.take([Tile.W9])[0]
    env.wall = pool.remaining()

    ctx = ScoringContext.from_env(env, table)
    rewards, breakdown = score_with_breakdown(ctx)
    bd0 = breakdown[0]

    assert _points(bd0, "peng_peng_hu") == table.get("peng_peng_hu", 0)
    assert _points(bd0, "ping_hu") == 0
    assert rewards[0] == sum(item["points"] for item in bd0)
