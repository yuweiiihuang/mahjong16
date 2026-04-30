from __future__ import annotations

from app.web.controller import InvalidActionError, WebSessionController
from app.web.serialize import sort_hand_tiles_for_web, tile_id_to_web_label


def _build_controller_waiting_for_human() -> WebSessionController:
    for seed in range(64):
        controller = WebSessionController(seed=seed, human_pid=0)
        snapshot = controller.snapshot("test-session")
        if snapshot["status"] == "awaiting_action":
            return controller
    raise AssertionError("failed to find a deterministic seed that reaches a human decision point")


def _play_until_hand_boundary(controller: WebSessionController) -> dict:
    for _ in range(512):
        snapshot = controller.snapshot("test-session")
        if snapshot["status"] in {"hand_result", "finished"}:
            return snapshot
        assert snapshot["status"] == "awaiting_action"
        action = snapshot["legalActions"][0]
        controller.submit_action(action)
    raise AssertionError("controller did not finish the hand within 512 human actions")


def test_tile_id_to_web_label_covers_suits_honors_and_flowers() -> None:
    assert tile_id_to_web_label(0) == "一萬"
    assert tile_id_to_web_label(9) == "一筒"
    assert tile_id_to_web_label(18) == "一條"
    assert tile_id_to_web_label(27) == "東"
    assert tile_id_to_web_label(34) == "花1"


def test_sort_hand_tiles_for_web_uses_wan_tiao_tong_honor_order() -> None:
    tiles = [13, 31, 0, 20, 29, 9, 3, 24]
    assert sort_hand_tiles_for_web(tiles) == [0, 3, 20, 24, 9, 13, 29, 31]


def test_controller_stops_at_human_decision_and_serializes_live_table() -> None:
    controller = _build_controller_waiting_for_human()

    snapshot = controller.snapshot("test-session")

    assert snapshot["status"] == "awaiting_action"
    assert snapshot["meta"]["activeSeat"] == "User"
    assert len(snapshot["table"]["players"]) == 4
    assert set(player["seat"] for player in snapshot["table"]["players"]) == {
        "User",
        "Right",
        "Opponent",
        "Left",
    }
    assert len(snapshot["table"]["selfHand"]) == len(snapshot["table"]["selfHandTileIds"])
    assert snapshot["meta"]["phase"] == controller.current_observation["phase"]
    assert snapshot["legalActions"]


def test_serialize_table_counts_opponent_drawn_tile_as_hidden_tile() -> None:
    controller = _build_controller_waiting_for_human()
    opponent_pid = next(
        player["pid"]
        for player in controller.snapshot("test-session")["table"]["players"]
        if player["seat"] == "Opponent"
    )

    for player in controller.env.players:
        player.drawn = None
    controller.env.players[opponent_pid].drawn = 0

    snapshot = controller.snapshot("test-session")

    assert snapshot["table"]["drawSeat"] == "Opponent"
    assert len(snapshot["table"]["oppHand"]) == len(controller.env.players[opponent_pid].hand) + 1


def test_controller_rejects_illegal_action() -> None:
    controller = _build_controller_waiting_for_human()

    try:
        controller.submit_action({"type": "DISCARD", "tile": 999, "from": "hand"})
    except InvalidActionError:
        return
    raise AssertionError("expected InvalidActionError for an illegal action")


def test_controller_pauses_at_hand_boundary_and_can_continue() -> None:
    controller = _build_controller_waiting_for_human()

    result_snapshot = _play_until_hand_boundary(controller)

    assert result_snapshot["status"] in {"hand_result", "finished"}
    assert result_snapshot["result"] is not None

    if result_snapshot["status"] == "hand_result":
        controller.continue_after_result()
        next_snapshot = controller.snapshot("test-session")
        assert next_snapshot["status"] in {"awaiting_action", "hand_result", "finished"}
