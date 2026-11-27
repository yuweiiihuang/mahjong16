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


_RON_TRIPLETS = [Tile.D7] * 3 + [Tile.D8] * 3 + [Tile.D9] * 3


@pytest.mark.parametrize("hand,expected_key", [
    pytest.param(
        [Tile.W2, Tile.W2, Tile.W3, Tile.W4] + _RON_TRIPLETS + [Tile.E] * 3,
        "si_an_ke",
        id="discard-used-in-pair-or-chow",
    ),
    pytest.param(
        [Tile.W2, Tile.W2, Tile.B5, Tile.B5] + _RON_TRIPLETS + [Tile.E] * 3,
        "si_an_ke",
        id="discard-completes-triplet-with-four-concealed-triplets",
    ),
    pytest.param(
        [Tile.W2, Tile.W2, Tile.B5, Tile.B5, Tile.B6, Tile.B7, Tile.B8] + _RON_TRIPLETS,
        "san_an_ke",
        id="discard-completes-triplet-with-three-concealed-triplets",
    ),
])
def test_ron_tile_only_spoils_a_triplet_it_completes(hand, expected_key):
    env, table = _prepare_env()
    env.winner = 0
    env.win_source = "RON"
    env.turn_at_win = 1
    pool = TilePool(include_flowers=False)
    env.players[0].hand = pool.take(hand)
    ron_tile = pool.take([Tile.W2])[0]
    env.last_discard = {"pid": 1, "tile": ron_tile}
    env.win_tile = ron_tile
    env.wall = pool.remaining()

    _, breakdown = score_with_breakdown(ScoringContext.from_env(env, table))

    triplet_keys = {"san_an_ke", "si_an_ke", "wu_an_ke"}
    assert {item["key"] for item in breakdown[0]} & triplet_keys == {expected_key}


# Five chows and a pair once 3B-4B is completed; 2B/5B is a two-sided wait.
_ALL_CHOWS = [
    Tile.W1, Tile.W2, Tile.W3, Tile.W4, Tile.W5, Tile.W6,
    Tile.D1, Tile.D2, Tile.D3, Tile.D4, Tile.D5, Tile.D6,
    Tile.B7, Tile.B7, Tile.B3, Tile.B4,
]
_CHI = ("CHI", [Tile.W1, Tile.W2, Tile.W3])


@pytest.mark.parametrize("concealed,melds,expected", [
    (_ALL_CHOWS, [], True),
    (_ALL_CHOWS[3:], [_CHI], True),
    (_ALL_CHOWS[6:], [_CHI, ("ANGANG", [Tile.W9] * 4)], False),
    (_ALL_CHOWS[6:], [_CHI, ("KAKAN", [Tile.W9] * 4)], False),
], ids=["concealed", "open-chi", "concealed-kong", "added-kong"])
def test_ping_hu_needs_no_open_chow_and_counts_every_kong(concealed, melds, expected):
    env, table = _prepare_env()
    env.winner = 0
    env.win_source = "RON"
    env.turn_at_win = 1
    pool = TilePool(include_flowers=False)
    env.players[0].melds = [
        {"type": kind, "tiles": pool.take(tiles), "from_pid": None if kind == "ANGANG" else 1}
        for kind, tiles in melds
    ]
    env.players[0].hand = pool.take(concealed)
    ron_tile = pool.take([Tile.B5])[0]
    env.last_discard = {"pid": 1, "tile": ron_tile}
    env.win_tile = ron_tile
    env.wall = pool.remaining()

    _, breakdown = score_with_breakdown(ScoringContext.from_env(env, table))

    assert ("ping_hu" in {item["key"] for item in breakdown[0]}) is expected


@pytest.mark.parametrize("hand,winning_tile,expected", [
    pytest.param(
        [
            Tile.W5, Tile.W6, Tile.W7, Tile.W8,
            Tile.D1, Tile.D2, Tile.D3, Tile.D4, Tile.D5, Tile.D6,
            Tile.B1, Tile.B2, Tile.B3, Tile.B4, Tile.B5, Tile.B6,
        ],
        Tile.W5, False, id="both-waits-complete-pairs",
    ),
    pytest.param(
        [
            Tile.D2, Tile.D3, Tile.D4, Tile.D6, Tile.D7, Tile.D8,
            Tile.B1, Tile.B2, Tile.B3, Tile.B3, Tile.B4,
            Tile.B4, Tile.B5, Tile.B5, Tile.B6, Tile.B7,
        ],
        Tile.B4, False, id="winning-tile-completes-pair-or-middle-of-chow",
    ),
    pytest.param(_ALL_CHOWS, Tile.B2, True, id="lower-end-of-two-sided-chow"),
])
def test_ping_hu_requires_two_sided_wait_in_chow_only_decomposition(hand, winning_tile, expected):
    env, table = _prepare_env()
    env.winner = 0
    env.win_source = "RON"
    env.turn_at_win = 1
    pool = TilePool(include_flowers=False)
    env.players[0].hand = pool.take(hand)
    ron_tile = pool.take([winning_tile])[0]
    env.last_discard = {"pid": 1, "tile": ron_tile}
    env.win_tile = ron_tile
    env.wall = pool.remaining()

    _, breakdown = score_with_breakdown(ScoringContext.from_env(env, table))

    assert ("ping_hu" in {item["key"] for item in breakdown[0]}) is expected


@pytest.mark.parametrize("ping_hu,triplets,expected_key,expected_total", [
    (2, 2, "san_an_ke", 3),
    (3, 2, "ping_hu", 4),
    (2, 3, "san_an_ke", 4),
], ids=["tie-keeps-triplets", "ping-hu-higher", "triplets-higher"])
def test_ping_hu_and_concealed_triplets_use_one_decomposition(
    ping_hu, triplets, expected_key, expected_total,
):
    env, table = _prepare_env()
    table = ScoringTable(
        values={**table.values, "ping_hu": ping_hu, "san_an_ke": triplets}, labels=table.labels,
    )
    env.winner = 0
    env.win_source = "RON"
    env.turn_at_win = 1
    env.discard_count = 6
    pool = TilePool(include_flowers=False)
    # 111222333W can be three triplets or three copies of the 123W chow.
    env.players[0].hand = pool.take(
        [Tile.W1] * 3 + [Tile.W2] * 3 + [Tile.W3] * 3
        + [Tile.D4, Tile.D5, Tile.D6, Tile.D8, Tile.D8, Tile.B6, Tile.B7]
    )
    ron_tile = pool.take([Tile.B8])[0]
    env.last_discard = {"pid": 1, "tile": ron_tile}
    env.win_tile = ron_tile
    env.wall = pool.remaining()

    rewards, breakdown = score_with_breakdown(ScoringContext.from_env(env, table))

    assert {item["key"] for item in breakdown[0]} == {"menqing", expected_key}
    assert rewards[0] == expected_total
