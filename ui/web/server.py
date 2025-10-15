"""FastAPI application serving the interactive mahjong16 web client."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.runtime import SessionService, _build_session_dependencies
from ui.web.manager import WebSessionStateManager, WebTableAdapter
from ui.web.state import static_asset_path
from ui.web.strategy import WebHumanStrategy


class SessionConfig(BaseModel):
    hands: int = Field(1, ge=1)
    seed: Optional[int] = None
    bot: str = Field("greedy", description="Bot type for non-human seats")
    start_points: int = Field(1000, ge=1)
    human_pid: int = Field(0, ge=0, le=3)


class ActionPayload(BaseModel):
    prompt_id: int
    action_id: str


class SessionCoordinator:
    """Orchestrates background demo sessions for the web UI."""

    def __init__(self, human_pid: int = 0) -> None:
        self.manager = WebSessionStateManager(human_pid=human_pid)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running_config: Optional[SessionConfig] = None

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, config: SessionConfig) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Session already running")
            self.manager.human_pid = config.human_pid
            self._running_config = config
            thread = threading.Thread(target=self._run_session, args=(config,), daemon=True)
            self._thread = thread
            thread.start()

    def _run_session(self, config: SessionConfig) -> None:
        try:
            env, table_manager, strategies, scoring_assets = _build_session_dependencies(
                seed=config.seed,
                human_pid=config.human_pid,
                bot=config.bot,
            )
            if not 0 <= config.human_pid < env.rules.n_players:
                raise ValueError("human_pid must be a valid seat index")

            strategies[config.human_pid] = WebHumanStrategy(self.manager)

            adapter = WebTableAdapter(self.manager)

            session = SessionService(
                env=env,
                table_manager=table_manager,
                strategies=strategies,
                scoring_assets=scoring_assets,
                hands=config.hands,
                start_points=config.start_points,
                table_view_port=adapter,
                hand_summary_port=adapter,
            )
            session.run()
        except Exception as exc:  # pragma: no cover - defensive
            self.manager.session_failed(str(exc))
        finally:
            with self._lock:
                self._thread = None
                self._running_config = None

    def submit_action(self, prompt_id: int, action_id: str) -> Dict[str, Any]:
        return self.manager.submit_action(prompt_id, action_id)


def create_app() -> FastAPI:
    coordinator = SessionCoordinator()
    app = FastAPI(title="mahjong16 web client")

    static_dir = Path(static_asset_path("index.html")).parent
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - side effect
        if not coordinator.is_running():
            coordinator.start(SessionConfig())

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_path = static_asset_path("index.html")
        return FileResponse(index_path)

    @app.get("/api/state")
    async def get_state() -> JSONResponse:
        state = coordinator.manager.snapshot()
        return JSONResponse(state)

    @app.post("/api/action")
    async def post_action(payload: ActionPayload) -> JSONResponse:
        try:
            action = coordinator.submit_action(payload.prompt_id, payload.action_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"accepted": True, "action": action})

    @app.post("/api/session/start")
    async def start_session(config: SessionConfig) -> JSONResponse:
        try:
            coordinator.start(config)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse({"status": "started", "config": config.dict()})

    @app.get("/api/session/status")
    async def session_status() -> JSONResponse:
        state = coordinator.manager.snapshot()
        return JSONResponse(state.get("session", {}))

    return app


app = create_app()


__all__ = ["create_app", "app"]
