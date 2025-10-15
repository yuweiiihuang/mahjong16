"""FastAPI application exposing the Mahjong16 web interface."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

from typing import TYPE_CHECKING

try:  # pragma: no cover - optional dependency import
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - allow module import without FastAPI installed
    FastAPI = None  # type: ignore
    HTTPException = WebSocket = WebSocketDisconnect = HTMLResponse = StaticFiles = None  # type: ignore
    BaseModel = None  # type: ignore

from ui.web.bridge import WebSessionBridge


if TYPE_CHECKING:  # pragma: no cover - type checking only
    from app.session import SessionService
    import uvicorn


logger = logging.getLogger(__name__)


if BaseModel is not None:

    class ActionRequest(BaseModel):
        serial: int
        action_id: str

else:  # pragma: no cover - FastAPI missing

    class ActionRequest:  # type: ignore
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("fastapi is required to use ActionRequest")


def create_app(
    *,
    session: "SessionService",
    bridge: WebSessionBridge,
    static_dir: Optional[Path] = None,
) -> FastAPI:
    """Build the FastAPI application serving the Mahjong table."""

    if FastAPI is None or HTTPException is None or HTMLResponse is None:
        raise RuntimeError("fastapi must be installed to create the web application")

    app = FastAPI(title="Mahjong16 Web Demo")
    static_path = (static_dir or Path(__file__).resolve().parent / "static")
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.on_event("startup")
    async def _startup() -> None:
        loop = asyncio.get_running_loop()
        bridge.set_event_loop(loop)

        def _run_session() -> None:
            try:
                session.run()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("session thread terminated unexpectedly")

        threading.Thread(target=_run_session, daemon=True).start()

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html_path = static_path / "index.html"
        if not html_path.exists():
            raise HTTPException(status_code=500, detail="index.html missing")
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/state")
    async def current_state() -> dict:
        return bridge.latest_state() or {}

    @app.post("/action")
    async def submit_action(payload: ActionRequest) -> dict:
        try:
            bridge.submit_action(serial=payload.serial, action_id=payload.action_id)
        except KeyError as exc:  # pragma: no cover - validation surface
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:  # pragma: no cover - validation surface
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_updates(ws: WebSocket) -> None:
        await ws.accept()
        try:
            async for payload in bridge.updates():
                if payload is None:
                    continue
                await ws.send_json(payload)
        except WebSocketDisconnect:  # pragma: no cover - client disconnect
            return

    return app


def run_web_app(
    *,
    session: "SessionService",
    bridge: WebSessionBridge,
    host: str = "0.0.0.0",
    port: int = 8000,
    log_level: str = "info",
) -> None:
    """Launch the FastAPI web server with the provided session."""

    try:
        import uvicorn  # type: ignore
    except ImportError as exc:  # pragma: no cover - missing optional dependency
        raise RuntimeError("uvicorn is required to run the web UI") from exc

    app = create_app(session=session, bridge=bridge)
    uvicorn.run(app, host=host, port=port, log_level=log_level)


__all__ = ["ActionRequest", "create_app", "run_web_app"]
