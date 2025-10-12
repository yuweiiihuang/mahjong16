from domain.scoring.breakdown import ScoreAccumulator, ScoreItem
from sdk import ScoringTable


TEST_TABLE = ScoringTable(
    values={
        "menqing": 1,
        "zimo": 1,
        "combo": 2,
    },
    labels={
        "menqing": "Menqing",
        "zimo": "Zimo",
        "combo": "Combo",
    },
)


def test_score_accumulator_add_merges_by_key_and_meta():
    acc = ScoreAccumulator(TEST_TABLE, player_id=0, n_players=4)

    assert acc.add("menqing") == 1
    assert acc.add("menqing", count=2) == 2
    assert acc.add("zimo", base=3, meta={"source": "tsumo"}) == 3
    assert acc.add("zimo", base=3, meta={"round": 1}) == 3

    breakdown = acc.to_breakdown()
    assert breakdown[0][0]["points"] == 3  # 1 + 2

    zimo = next(item for item in breakdown[0] if item["key"] == "zimo")
    assert zimo["points"] == 6
    assert zimo["meta"] == {"source": "tsumo", "round": 1}
    assert acc.total() == 9


def test_score_accumulator_extend_accepts_dicts_and_items():
    acc = ScoreAccumulator(TEST_TABLE, player_id=1, n_players=3)

    acc.extend([
        ScoreItem(key="combo", label="Combo", base=2, count=1, points=2),
        {"key": "combo", "label": "Combo", "base": 2, "count": 2, "points": 4},
        {"key": "menqing", "base": 1, "count": 1, "points": 1},
    ])

    breakdown = acc.to_breakdown()
    assert breakdown[1][0]["points"] == 6
    assert breakdown[1][1]["points"] == 1
    assert breakdown[0] == []
    assert acc.total() == 7
