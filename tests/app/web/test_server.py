from app.web.controller import SessionRegistry
from app.web.server import dispatch_request


def test_session_api_create_get_action_and_continue() -> None:
    registry = SessionRegistry()
    status, created = dispatch_request(registry, "POST", "/api/session")
    assert status == 201
    session_id = created["sessionId"]

    status, fetched = dispatch_request(registry, "GET", f"/api/session/{session_id}")
    assert status == 200
    assert fetched["sessionId"] == session_id

    bad_status, bad_payload = dispatch_request(
        registry,
        "POST",
        f"/api/session/{session_id}/action",
        payload={"action": {"type": "DISCARD", "tile": 999, "from": "hand"}},
    )
    assert bad_status == 400
    assert "legal" in bad_payload["error"]

    snapshot = fetched
    for _ in range(512):
        if snapshot["status"] in {"hand_result", "finished"}:
            break
        assert snapshot["status"] == "awaiting_action"
        action = snapshot["legalActions"][0]
        status, snapshot = dispatch_request(
            registry,
            "POST",
            f"/api/session/{session_id}/action",
            payload={"action": action},
        )
        assert status == 200
    else:
        raise AssertionError("session API did not reach a hand boundary within 512 human actions")

    assert snapshot["result"] is not None

    if snapshot["status"] == "hand_result":
        status, continued = dispatch_request(
            registry,
            "POST",
            f"/api/session/{session_id}/continue",
        )
        assert status == 200
        assert continued["status"] in {"awaiting_action", "hand_result", "finished"}
