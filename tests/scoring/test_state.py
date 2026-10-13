import pytest

from domain.rules import Ruleset
from domain.scoring.state import build_state
from domain.scoring.score_types import Meld, PlayerView, ScoringContext, ScoringTable


def _blank_player(pid: int) -> PlayerView:
    return PlayerView(
        id=pid,
        hand=[],
        drawn=None,
        melds=[],
        flowers=[],
        river=[],
        declared_ting=False,
    )


def _make_context(**overrides) -> ScoringContext:
    rules = overrides.pop("rules", Ruleset())
    players = overrides.pop(
        "players",
        [_blank_player(i) for i in range(rules.n_players)],
    )
    table = overrides.pop("table", ScoringTable(values={}, labels={}))
    base = dict(
        rules=rules,
        players=players,
        winner=0,
        win_source="TSUMO",
        win_tile=None,
        last_discard=None,
        turn_at_win=None,
        wall_len=rules.dead_wall_base,
        n_gang=0,
        table=table,
    )
    base.update(overrides)
    return ScoringContext(**base)


def test_build_state_requires_winner():
    ctx = _make_context(winner=None)
    with pytest.raises(ValueError):
        build_state(ctx)


@pytest.mark.parametrize("source,kind,menqing", [
    ("TSUMO", None, True),
    ("RON", None, True),
    ("RON", "CHI", False),
    ("RON", "PONG", False),
    ("RON", "GANG", False),
    ("RON", "KAKAN", False),
    ("RON", "ANGANG", True),
])
def test_build_state_derives_win_tiles_and_meld_contracts(source, kind, menqing):
    ctx = _make_context(win_source=source, last_discard={"tile": 28}, turn_at_win=1)
    player = ctx.players[0]
    player.hand = list(range(12 if kind else 15)) + [26]
    if kind:
        tiles = [18, 19, 20] if kind == "CHI" else [18] * (3 if kind == "PONG" else 4)
        player.melds = [Meld(type=kind, tiles=tiles)]
    if source == "TSUMO":
        player.drawn = 27

    state = build_state(ctx)
    assert state.win.tsumo is (source == "TSUMO")
    assert state.win.drawn == (27 if source == "TSUMO" else None)
    assert state.win.ron_tile == (28 if source == "RON" else None)
    assert state.win.win_tile_id == (27 if source == "TSUMO" else 28)
    assert state.hand.concealed_tiles == player.hand + ([27] if source == "TSUMO" else [])
    assert state.hand.concealed_for_patterns == player.hand + ([27] if source == "TSUMO" else [28])
    assert state.hand.menqing is menqing
    assert state.hand.fixed_melds == int(kind is not None)
    assert state.hand.need == (4 if kind else 5)
    assert state.hand.required_len == (14 if kind else 17)
