from ui.human_common import build_reaction_context, build_turn_context
from domain.tiles import Tile


def _hand_tiles() -> list[int]:
    return [
        int(Tile.W1),
        int(Tile.W2),
        int(Tile.W3),
        int(Tile.W4),
        int(Tile.W5),
        int(Tile.W6),
        int(Tile.W7),
        int(Tile.W8),
        int(Tile.W9),
        int(Tile.D5),
        int(Tile.D5),
        int(Tile.D5),
        int(Tile.B7),
        int(Tile.B8),
        int(Tile.B9),
        int(Tile.E),
    ]


def test_build_turn_context_populates_actions() -> None:
    obs = {
        "phase": "TURN",
        "player": 0,
        "hand": _hand_tiles(),
        "drawn": int(Tile.W1),
        "melds": [],
        "flowers": [],
        "declared_ting": False,
        "legal_actions": [
            {"type": "DISCARD", "tile": int(Tile.W1), "from": "hand"},
            {"type": "DISCARD", "tile": int(Tile.W2), "from": "hand"},
            {"type": "DISCARD", "tile": int(Tile.W1), "from": "drawn"},
            {"type": "ANGANG", "tile": int(Tile.D5)},
            {"type": "HU"},
        ],
    }

    context = build_turn_context(obs)

    assert context.player == 0
    assert len(context.hand) == len(_hand_tiles())
    # two unique discard options due to hand/drawn sources
    assert len(context.discard_options) == 3
    discard_types = {opt.source for opt in context.discard_options}
    assert {"hand", "drawn"}.issubset(discard_types)
    assert context.hu_action is not None
    assert context.angang_actions and context.angang_actions[0]["type"].upper() == "ANGANG"


def test_build_reaction_context_orders_by_priority() -> None:
    obs = {
        "phase": "REACTION",
        "player": 1,
        "last_discard": {"tile": int(Tile.W1)},
        "legal_actions": [
            {"type": "PASS"},
            {"type": "CHI", "use": [int(Tile.W2), int(Tile.W3)]},
            {"type": "PONG", "tile": int(Tile.W1)},
            {"type": "HU", "tile": int(Tile.W1)},
        ],
    }

    context = build_reaction_context(obs)

    assert context.player == 1
    assert context.last_discard_tile == int(Tile.W1)
    # PASS should remain first
    assert context.menu[0].action["type"].upper() == "PASS"
    # HU should outrank PONG/CHI
    types = [item.action["type"].upper() for item in context.menu]
    assert types.index("HU") < types.index("PONG")
