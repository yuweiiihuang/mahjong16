from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from domain import Mahjong16Env
from domain.tiles import tile_to_str

from app.logging import HandLogWriter, write_hand_log
from app.session import HandSummaryPort, ScoreState, StepEvent, TableViewPort
from ui.console import render_public_view, render_reveal, render_winners_summary


def _summarize_resolved_claim(info: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not info or "resolved_claim" not in info:
        return None
    resolved = info["resolved_claim"]
    claim_type = (resolved.get("type") or "").upper()
    pid = resolved.get("pid")
    tile = resolved.get("tile")
    detail = ""
    if claim_type == "CHI":
        use = resolved.get("use", [])
        if isinstance(use, list) and len(use) == 2:
            detail = f"{tile_to_str(use[0])}-{tile_to_str(use[1])} + {tile_to_str(tile)}"
    elif claim_type in {"PONG", "GANG", "HU"}:
        detail = tile_to_str(tile) or ""
    return {"who": f"P{pid}", "type": claim_type, "detail": detail}


def _update_ui(
    env: Mahjong16Env,
    human_pid: Optional[int],
    discard_id: int,
    *,
    last_action: Optional[Dict[str, Any]] = None,
    score_state: Optional[ScoreState] = None,
) -> None:
    pov = human_pid if human_pid is not None else 0
    render_public_view(
        env,
        pov_pid=pov,
        did=discard_id,
        last_action=last_action,
        score_state=score_state,
    )


class ConsoleUIAdapter(TableViewPort, HandSummaryPort):
    """Rich console implementation for session events."""

    def __init__(
        self,
        *,
        human_pid: Optional[int],
        n_players: int,
        log_dir: Optional[str] = None,
        emit_logs: bool = True,
    ) -> None:
        self.human_pid = human_pid
        self.n_players = n_players
        self.log_dir = log_dir
        self.emit_logs = emit_logs

        self._log_writer: Optional[HandLogWriter] = None
        self._log_writer_path = None
        self._log_writer_failed = False
        self._finalize_written_path: Optional[str] = None
        self._finalize_write_error: Optional[str] = None

        self._discard_id = 0
        self._last_seen_discard: Optional[Tuple[Optional[int], Any]] = None

    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        self._reset_hand_state()
        if self.emit_logs:
            print("=== mahjong16 demo（Rich Console UI） ===")

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self._reset_hand_state()
        if not self.emit_logs:
            return
        print(
            "--- Hand {hand} | Jang={jang} | Quan={quan} | Dealer=P{dealer} | Streak={streak} ---".format(
                hand=hand_index,
                jang=jang_index,
                quan=getattr(env, "quan_feng", "?"),
                dealer=getattr(env, "dealer_pid", 0),
                streak=getattr(env, "dealer_streak", 0),
            )
        )

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        if not self.emit_logs:
            return

        claim_event = _summarize_resolved_claim(event.info)
        if claim_event:
            _update_ui(
                env,
                self.human_pid,
                self._discard_id,
                last_action=claim_event,
                score_state=score_state,
            )

        if event.action_type == "DISCARD" and event.discarded_tile is not None:
            self._discard_id += 1
            self._last_seen_discard = (event.acting_pid, event.discarded_tile)
            _update_ui(
                env,
                self.human_pid,
                self._discard_id,
                last_action={
                    "who": f"P{event.acting_pid}",
                    "type": "DISCARD",
                    "detail": tile_to_str(event.discarded_tile),
                },
                score_state=score_state,
            )

        if (
            event.observation.get("phase") == "REACTION"
            and self.human_pid is not None
            and event.observation.get("player") == self.human_pid
        ):
            last_discard = getattr(env, "last_discard", None)
            if isinstance(last_discard, dict) and last_discard.get("tile") is not None:
                key = (last_discard.get("pid"), last_discard.get("tile"))
                if key != self._last_seen_discard:
                    self._discard_id += 1
                    self._last_seen_discard = key
                    _update_ui(
                        env,
                        self.human_pid,
                        self._discard_id,
                        last_action={
                            "who": f"P{last_discard.get('pid')}",
                            "type": "DISCARD",
                            "detail": tile_to_str(last_discard.get("tile")),
                        },
                        score_state=score_state,
                    )

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        if not self.emit_logs:
            return
        render_reveal(
            env,
            breakdown=breakdown,
            payments=payments,
            base_points=getattr(env.rules, "base_points", None),
            tai_points=getattr(env.rules, "tai_points", None),
            totals=list(score_state.get("totals", [])),
        )

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        if self.emit_logs and summaries:
            render_winners_summary(summaries)

        if self.emit_logs:
            if self._finalize_write_error is not None:
                print(self._finalize_write_error)
            elif self._finalize_written_path is not None:
                print(f"[log] wrote per-hand summary to {self._finalize_written_path}")
            if self._log_writer_path is not None:
                print(f"[log] appended per-hand summary to {self._log_writer_path}")
            print("=== demo finished ===")

    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        if self.log_dir is None or self._log_writer_failed:
            return
        try:
            if self._log_writer is None:
                self._log_writer = HandLogWriter(
                    self.log_dir,
                    max_players=self.n_players,
                )
            self._log_writer.append(summary)
            if self._log_writer_path is None:
                self._log_writer_path = self._log_writer.path
        except Exception as exc:
            self._log_writer_failed = True
            self._log_writer = None
            if self.emit_logs:
                print(f"[warn] failed to append log in {self.log_dir}: {exc}")

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        finalize_log_dir: Optional[str] = None
        self._finalize_written_path = None
        self._finalize_write_error = None
        if self._log_writer is not None:
            try:
                self._log_writer.close()
            finally:
                self._log_writer = None
        if self.log_dir is not None:
            if self._log_writer_failed or self._log_writer_path is None:
                finalize_log_dir = self.log_dir

        if finalize_log_dir is not None:
            if self.emit_logs:
                try:
                    written = write_hand_log(summaries, finalize_log_dir)
                    if written is not None:
                        self._finalize_written_path = str(written)
                except Exception as exc:
                    self._finalize_write_error = f"[warn] failed to write log in {finalize_log_dir}: {exc}"
            else:
                write_hand_log(summaries, finalize_log_dir)

    def _reset_hand_state(self) -> None:
        self._discard_id = 0
        self._last_seen_discard = None

