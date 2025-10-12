from __future__ import annotations

from typing import Iterable, Sequence

from domain.rules import Ruleset
from domain.scoring.breakdown import ScoreAccumulator
from domain.scoring.common import is_honor
from domain.scoring.rules.base import apply_base_rules
from domain.scoring.rules.flowers import apply_flowers_rules
from domain.scoring.rules.honors import apply_honors_rules
from domain.scoring.rules.patterns import apply_patterns_rules
from domain.scoring.rules.timings import apply_timings_rules
from domain.scoring.rules.waits import apply_waits_rules
from domain.scoring.state import DerivedScoringState, HandState, WinState
from domain.scoring.types import Meld, PlayerView, ScoringContext, ScoringTable
from domain.tiles import tile_to_str


SCORING_VALUES = {
    "menqing": 1,
    "menqing_zimo": 3,
    "zimo": 1,
    "hai_di": 1,
    "he_di": 1,
    "gang_shang": 2,
    "qiang_gang": 2,
    "dealer": 1,
    "ba_xian": 8,
    "qi_qiang_yi": 7,
    "zheng_hua": 1,
    "hua_gang": 2,
    "dragon_pung": 1,
    "xiao_san_yuan": 6,
    "da_san_yuan": 8,
    "xiao_si_xi": 8,
    "da_si_xi": 13,
    "quan_feng_ke": 1,
    "men_feng_ke": 1,
    "zi_yi_se": 10,
    "qing_yi_se": 6,
    "hun_yi_se": 4,
    "peng_peng_hu": 4,
    "san_an_ke": 3,
    "si_an_ke": 6,
    "wu_an_ke": 10,
    "quan_qiu_ren": 5,
    "ting": 1,
    "du_ting": 2,
    "ping_hu": 2,
    "tian_ting": 1,
    "di_ting": 1,
    "tian_hu": 3,
    "di_hu": 2,
    "ren_hu": 1,
}

SCORING_TABLE = ScoringTable(values=SCORING_VALUES, labels={k: k for k in SCORING_VALUES})


def _tid(label: str) -> int:
    for i in range(64):
        if tile_to_str(i) == label:
            return i
    raise AssertionError(f"Unknown tile label: {label}")


def _blank_players(n: int) -> list[PlayerView]:
    return [
        PlayerView(
            id=i,
            hand=[],
            drawn=None,
            melds=[],
            flowers=[],
            river=[],
            declared_ting=False,
        )
        for i in range(n)
    ]


def _make_context(
    *,
    rules: Ruleset | None = None,
    players: Sequence[PlayerView] | None = None,
    winner: int = 0,
    win_source: str = "TSUMO",
    wall_len: int | None = None,
    last_discard: dict | None = None,
    turn_at_win: int | None = None,
    flower_win_type: str | None = None,
    winner_is_dealer: bool = False,
    dealer_streak: int = 0,
    win_by_gang_draw: bool = False,
    win_by_qiang_gang: bool = False,
    quan_feng: str | None = None,
    seat_winds: Sequence[str] | None = None,
    discard_count: int = 0,
    open_meld_count: int = 0,
    dealer_pid: int | None = None,
) -> ScoringContext:
    rules = rules or Ruleset()
    players = list(players or _blank_players(rules.n_players))
    wall_len = wall_len if wall_len is not None else rules.dead_wall_base + 10
    return ScoringContext(
        rules=rules,
        players=players,
        winner=winner,
        win_source=win_source,
        win_tile=None,
        last_discard=last_discard,
        turn_at_win=turn_at_win,
        wall_len=wall_len,
        n_gang=0,
        table=SCORING_TABLE,
        winner_is_dealer=winner_is_dealer,
        win_by_gang_draw=win_by_gang_draw,
        win_by_qiang_gang=win_by_qiang_gang,
        discard_count=discard_count,
        open_meld_count=open_meld_count,
        quan_feng=quan_feng,
        seat_winds=list(seat_winds) if seat_winds is not None else None,
        dealer_pid=dealer_pid,
        dealer_streak=dealer_streak,
        flower_win_type=flower_win_type,
    )


def _hand_state(
    *,
    concealed_tiles: Iterable[int] | None = None,
    concealed_for_patterns: Iterable[int] | None = None,
    counts34: Sequence[int] | None = None,
    counts34_concealed: Sequence[int] | None = None,
    counts16: Sequence[int] | None = None,
    base_hand_for_waits: Iterable[int] | None = None,
    fixed_melds: int = 0,
    fixed_melds_pungs: int = 0,
    fixed_melds_chis: int = 0,
    need: int = -1,
    required_len: int | None = None,
    menqing: bool = True,
) -> HandState:
    concealed_tiles = list(concealed_tiles or [])
    concealed_for_patterns = list(concealed_for_patterns or concealed_tiles)
    base_hand_for_waits = list(base_hand_for_waits or concealed_tiles)
    counts34 = list(counts34 or [0] * 34)
    counts34_concealed = list(counts34_concealed or counts34)
    counts16 = list(counts16 or [0] * 34)
    return HandState(
        concealed_tiles=concealed_tiles,
        concealed_for_patterns=concealed_for_patterns,
        counts34=counts34,
        counts34_concealed=counts34_concealed,
        counts16=counts16,
        base_hand_for_waits=base_hand_for_waits,
        fixed_melds=fixed_melds,
        fixed_melds_pungs=fixed_melds_pungs,
        fixed_melds_chis=fixed_melds_chis,
        need=need,
        required_len=required_len,
        menqing=menqing,
    )


def _win_state(
    *,
    tsumo: bool = True,
    win_source: str = "TSUMO",
    drawn: int | None = None,
    ron_tile: int | None = None,
    ron_tile_idx: int | None = None,
    win_tile_id: int | None = None,
    tenpai_before_draw: bool = False,
    waits_for_du: Sequence[int] | None = None,
) -> WinState:
    waits = list(waits_for_du or [])
    return WinState(
        tsumo=tsumo,
        win_source=win_source,
        drawn=drawn,
        ron_tile=ron_tile,
        ron_tile_idx=ron_tile_idx,
        win_tile_id=win_tile_id,
        tenpai_before_draw=tenpai_before_draw,
        waits_for_du=waits,
        waits_for_du_set=set(waits),
    )


def _state(
    ctx: ScoringContext,
    *,
    hand: HandState,
    win: WinState,
    melds: Sequence[Meld] | None = None,
    flowers: Sequence[int] | None = None,
) -> DerivedScoringState:
    melds = list(melds or [])
    flowers = list(flowers or [])
    player = ctx.players[ctx.winner]
    player.hand = list(hand.concealed_tiles)
    player.drawn = win.drawn
    player.melds = list(melds)
    player.flowers = list(flowers)
    all_tiles = list(hand.concealed_for_patterns)
    for meld in melds:
        all_tiles.extend(meld.tiles)
    has_honor_total = any(is_honor(t) for t in all_tiles)
    return DerivedScoringState(
        ctx=ctx,
        player=player,
        melds=list(melds),
        melds_dicts=[{"type": m.type, "tiles": list(m.tiles)} for m in melds],
        flowers=list(flowers),
        has_flowers_total=bool(flowers),
        flower_win_type=ctx.flower_win_type,
        hand=hand,
        win=win,
        all_tiles=all_tiles,
        has_honor_total=has_honor_total,
    )


def _acc(ctx: ScoringContext) -> ScoreAccumulator:
    return ScoreAccumulator(SCORING_TABLE, ctx.winner or 0, ctx.rules.n_players)


def _points(breakdown: list[dict], key: str) -> int:
    for item in breakdown:
        if item["key"] == key:
            return item["points"]
    return 0


def test_apply_base_rules_prefers_menqing_zimo():
    ctx = _make_context(win_source="TSUMO")
    concealed = (
        [_tid("1W")] * 4
        + [_tid("2W")] * 4
        + [_tid("3W")] * 4
        + [_tid("4W")] * 3
        + [_tid("5W")]
    )
    hand = _hand_state(concealed_tiles=concealed, menqing=True)
    win = _win_state(tsumo=True, drawn=_tid("4W"), win_tile_id=_tid("4W"))
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_base_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]

    assert _points(breakdown, "menqing_zimo") == SCORING_VALUES["menqing_zimo"]
    assert _points(breakdown, "menqing") == 0
    assert _points(breakdown, "zimo") == 0


def test_apply_base_rules_handles_tail_and_dealer_bonus():
    rules = Ruleset(dead_wall_base=16)
    ctx = _make_context(
        rules=rules,
        win_source="RON",
        wall_len=rules.dead_wall_base,
        winner_is_dealer=True,
        dealer_streak=2,
        turn_at_win=1,
    )
    concealed = (
        [_tid("1W")] * 3
        + [_tid("2W")] * 3
        + [_tid("3W")] * 3
        + [_tid("4W")] * 3
        + [_tid("5W")] * 2
    )
    hand = _hand_state(concealed_tiles=concealed, menqing=False)
    win = _win_state(tsumo=False, win_source="RON", ron_tile=_tid("2W"), win_tile_id=_tid("2W"))
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_base_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "he_di") == SCORING_VALUES["he_di"]
    assert _points(breakdown, "dealer") == 2 * 2 + 1


def test_apply_flowers_rules_short_circuits_on_flower_win():
    ctx = _make_context(flower_win_type="ba_xian")
    hand = _hand_state()
    win = _win_state()
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    keep_going = apply_flowers_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]

    assert keep_going is False
    assert _points(breakdown, "ba_xian") == SCORING_VALUES["ba_xian"]
    assert acc.total() == SCORING_VALUES["ba_xian"]


def test_apply_flowers_rules_short_circuits_on_qi_qiang_yi():
    ctx = _make_context(flower_win_type="qi_qiang_yi")
    state = _state(ctx, hand=_hand_state(), win=_win_state())
    acc = _acc(ctx)

    keep_going = apply_flowers_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]

    assert keep_going is False
    assert _points(breakdown, "qi_qiang_yi") == SCORING_VALUES["qi_qiang_yi"]


def test_apply_flowers_rules_counts_regular_flowers(monkeypatch):
    rules = Ruleset(enable_wind_flower_scoring=True)
    seat_winds = ["E", "S", "W", "N"]
    flowers = list(range(34, 42))
    ctx = _make_context(rules=rules, seat_winds=seat_winds)
    ctx.seat_winds = seat_winds
    hand = _hand_state()
    win = _win_state()
    state = _state(ctx, hand=hand, win=win, flowers=flowers)
    acc = _acc(ctx)

    monkeypatch.setattr(
        "domain.scoring.rules.flowers._flower_no",
        lambda tile: tile - 33,
    )

    keep_going = apply_flowers_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]

    assert keep_going is True
    assert _points(breakdown, "zheng_hua") == 2
    assert _points(breakdown, "hua_gang") == 4
    assert _points(breakdown, "ba_xian") == SCORING_VALUES["ba_xian"]


def test_apply_flowers_rules_requires_flower_win_for_qi_qiang_yi():
    flowers = [_tid(f"F{i}") for i in range(1, 8)]

    ctx = _make_context()
    state = _state(ctx, hand=_hand_state(), win=_win_state(), flowers=flowers)
    acc = _acc(ctx)

    keep_going = apply_flowers_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]

    assert keep_going is True
    assert _points(breakdown, "qi_qiang_yi") == 0

    ctx_no_flower_win = _make_context(rules=Ruleset(enable_flower_wins=False))
    state_no_flower_win = _state(
        ctx_no_flower_win,
        hand=_hand_state(),
        win=_win_state(),
        flowers=flowers,
    )
    acc_no_flower_win = _acc(ctx_no_flower_win)

    keep_going_no_flower_win = apply_flowers_rules(
        ctx_no_flower_win, state_no_flower_win, acc_no_flower_win
    )
    breakdown_no_flower_win = acc_no_flower_win.to_breakdown()[
        ctx_no_flower_win.winner
    ]

    assert keep_going_no_flower_win is True
    assert _points(breakdown_no_flower_win, "qi_qiang_yi") == SCORING_VALUES[
        "qi_qiang_yi"
    ]


def test_apply_honors_rules_detects_dragons():
    tiles = (
        [_tid("C")] * 3
        + [_tid("F")] * 3
        + [_tid("P")] * 2
        + [_tid("1W")] * 2
        + [_tid("2W")] * 2
        + [_tid("3W")] * 2
        + [_tid("4W")] * 2
    )
    hand = _hand_state(concealed_tiles=tiles, concealed_for_patterns=tiles, need=4, required_len=len(tiles))
    win = _win_state(tsumo=True, win_tile_id=_tid("1W"))
    ctx = _make_context()
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_honors_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "xiao_san_yuan") == SCORING_VALUES["xiao_san_yuan"]
    assert _points(breakdown, "dragon_pung") == 0


def test_apply_honors_rules_wind_and_dealer_bonus():
    rules = Ruleset(enable_wind_flower_scoring=True)
    seat_winds = ["E", "S", "W", "N"]
    tiles = (
        [_tid("E")] * 3
        + [_tid("1W")] * 2
        + [_tid("2W")] * 2
        + [_tid("3W")] * 2
        + [_tid("4W")] * 2
        + [_tid("5W")] * 2
        + [_tid("6W")] * 2
        + [_tid("7W")]
    )
    hand = _hand_state(concealed_tiles=tiles, concealed_for_patterns=tiles, need=4, required_len=len(tiles))
    win = _win_state(tsumo=True, win_tile_id=_tid("1W"))
    ctx = _make_context(rules=rules, quan_feng="E", seat_winds=seat_winds)
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_honors_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "quan_feng_ke") == SCORING_VALUES["quan_feng_ke"]
    assert _points(breakdown, "men_feng_ke") == SCORING_VALUES["men_feng_ke"]


def test_apply_honors_rules_detects_big_four_winds():
    tiles = [_tid("E")] * 3 + [_tid("S")] * 3 + [_tid("W")] * 3 + [_tid("N")] * 3 + [_tid("1W")] * 4
    hand = _hand_state(concealed_tiles=tiles, concealed_for_patterns=tiles, need=4, required_len=len(tiles))
    win = _win_state(tsumo=True, win_tile_id=_tid("1W"))
    ctx = _make_context()
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_honors_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "da_si_xi") == SCORING_VALUES["da_si_xi"]


def test_apply_patterns_rules_detects_color_and_peng_peng_hu():
    tiles = (
        [_tid("1B")] * 3
        + [_tid("2B")] * 3
        + [_tid("3B")] * 3
        + [_tid("4B")] * 3
        + [_tid("5B")] * 2
    )
    counts34 = [0] * 34
    for tile in tiles:
        idx = tile % 34
        counts34[idx] += 1
    hand = _hand_state(
        concealed_tiles=tiles,
        concealed_for_patterns=tiles,
        counts34=counts34,
        counts34_concealed=counts34,
        need=4,
        required_len=len(tiles),
        menqing=True,
    )
    win = _win_state(tsumo=False, win_source="RON", ron_tile=_tid("5B"), win_tile_id=_tid("5B"), ron_tile_idx=_tid("5B") % 34)
    ctx = _make_context(win_source="RON")
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_patterns_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "qing_yi_se") == SCORING_VALUES["qing_yi_se"]
    assert _points(breakdown, "peng_peng_hu") == SCORING_VALUES["peng_peng_hu"]


def test_apply_waits_rules_marks_ting_and_du_ting():
    counts16 = [0] * 34
    counts16[_tid("3W")] = 1
    counts16[_tid("4W")] = 1
    hand = _hand_state(
        concealed_tiles=[_tid("3W"), _tid("4W"), _tid("5W")],
        counts16=counts16,
        fixed_melds_chis=1,
        need=1,
        required_len=3,
        menqing=True,
    )
    win = _win_state(
        tsumo=False,
        win_source="RON",
        ron_tile=_tid("5W"),
        ron_tile_idx=_tid("5W") % 34,
        win_tile_id=_tid("5W"),
        waits_for_du=[_tid("5W")],
    )
    ctx = _make_context(win_source="RON")
    ctx.players[ctx.winner].declared_ting = True
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_waits_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "ting") == SCORING_VALUES["ting"]
    assert _points(breakdown, "du_ting") == SCORING_VALUES["du_ting"]


def test_apply_timings_rules_cover_tian_di_ren():
    ctx = _make_context(win_source="TSUMO", discard_count=0, open_meld_count=0)
    ctx.players[ctx.winner].ting_declared_at = 1
    ctx.players[ctx.winner].ting_declared_open_melds = 0
    hand = _hand_state()
    win = _win_state(tsumo=True, win_source="TSUMO")
    state = _state(ctx, hand=hand, win=win)
    acc = _acc(ctx)

    apply_timings_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "tian_ting") == SCORING_VALUES["tian_ting"]
    assert _points(breakdown, "tian_hu") == SCORING_VALUES["tian_hu"]

    # switch to di ting/di hu
    ctx.win_source = "RON"
    ctx.discard_count = 1
    ctx.players[ctx.winner].ting_declared_at = 5
    state = _state(ctx, hand=hand, win=_win_state(tsumo=False, win_source="RON"))
    acc = _acc(ctx)
    apply_timings_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "di_ting") == SCORING_VALUES["di_ting"]
    assert _points(breakdown, "di_hu") == SCORING_VALUES["di_hu"]

    # ren hu scenario
    ctx.discard_count = ctx.rules.n_players
    ctx.open_meld_count = 0
    state = _state(ctx, hand=hand, win=_win_state(tsumo=False, win_source="RON"))
    acc = _acc(ctx)
    apply_timings_rules(ctx, state, acc)
    breakdown = acc.to_breakdown()[ctx.winner]
    assert _points(breakdown, "ren_hu") == SCORING_VALUES["ren_hu"]
