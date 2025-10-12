import pytest

from domain.rules import Ruleset
from domain.scoring.state import build_state
from domain.scoring.types import PlayerView, ScoringContext, ScoringTable


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


def test_build_state_populates_tsumo_information():
    rules = Ruleset()
    players = [_blank_player(i) for i in range(rules.n_players)]
    players[0].hand = [
        0, 0, 0, 0,
        1, 1, 1,
        2, 2,
        3, 3,
        4, 4,
        5,
        6,
    ]
    players[0].drawn = 1
    ctx = _make_context(rules=rules, players=players, win_source="TSUMO")

    state = build_state(ctx)
    assert state.win.tsumo is True
    assert state.win.drawn == 1
    assert len(state.hand.concealed_tiles) == 16
    assert state.hand.menqing is True
    assert state.win.win_tile_id == 1


def test_build_state_handles_ron_and_open_melds():
    rules = Ruleset()
    players = [_blank_player(i) for i in range(rules.n_players)]
    players[0].hand = [
        0, 0, 0, 0,
        1, 1, 1, 1,
        2, 2, 2, 2,
        3, 3,
        4, 4,
    ]
    players[0].melds = []
    players[0].drawn = None
    ctx = _make_context(
        rules=rules,
        players=players,
        win_source="RON",
        last_discard={"tile": 5},
        turn_at_win=1,
    )

    state = build_state(ctx)
    assert state.win.tsumo is False
    assert state.win.ron_tile == 5
    assert state.win.win_tile_id == 5
    assert state.hand.menqing is True
    assert 5 in state.hand.concealed_for_patterns
