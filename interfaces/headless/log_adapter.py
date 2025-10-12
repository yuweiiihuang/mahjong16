from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from app.logging import HandLogWriter, write_hand_log
from application.session_service import HandSummaryPort, ProgressPort


class HeadlessLogAdapter(ProgressPort, HandSummaryPort):
    """Headless adapter handling progress updates and log persistence."""

    def __init__(
        self,
        *,
        n_players: int,
        log_dir: Optional[str] = None,
        emit_logs: bool = True,
        hand_progress_cb: Optional[Callable[[int], None]] = None,
    ) -> None:
        self.n_players = n_players
        self.log_dir = log_dir
        self.emit_logs = emit_logs
        self.hand_progress_cb = hand_progress_cb

        self._log_writer: Optional[HandLogWriter] = None
        self._log_writer_path = None
        self._log_writer_failed = False

        self._progress_manager: Optional[Progress] = None
        self._progress: Optional[Progress] = None
        self._progress_task: Optional[int] = None
        self._finalize_written_path: Optional[str] = None
        self._finalize_write_error: Optional[str] = None

    # ProgressPort implementation -------------------------------------------------
    def on_session_start(self, total_hands: Optional[int]) -> None:
        if not self.emit_logs:
            return

        self._progress_manager = self._build_progress_manager(total_hands)
        if self._progress_manager is not None:
            self._progress = self._progress_manager.__enter__()
            total = None
            if total_hands is not None and total_hands > 0:
                total = total_hands
            if self._progress is not None:
                self._progress_task = self._progress.add_task("Hands", total=total)
        self._print("=== mahjong16 demo（Headless） ===")

    def on_hand_complete(self, hand_index: int) -> None:
        if self.emit_logs and self._progress is not None and self._progress_task is not None:
            self._progress.advance(self._progress_task, 1)
        if self.hand_progress_cb is not None:
            self.hand_progress_cb(hand_index)

    def on_session_end(self) -> None:
        if self._progress_manager is not None:
            try:
                self._progress_manager.__exit__(None, None, None)
            finally:
                self._progress_manager = None
                self._progress = None
                self._progress_task = None

    # HandSummaryPort implementation ---------------------------------------------
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
                self._print(f"[warn] failed to append log in {self.log_dir}: {exc}")

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

        if self.emit_logs:
            if self._finalize_write_error is not None:
                self._print(self._finalize_write_error)
            elif self._finalize_written_path is not None:
                self._print(f"[log] wrote per-hand summary to {self._finalize_written_path}")
            if self._log_writer_path is not None:
                self._print(f"[log] appended per-hand summary to {self._log_writer_path}")
            self._print("=== demo finished ===")

    # ---------------------------------------------------------------------------
    def _print(self, message: str) -> None:
        if not self.emit_logs:
            return
        if self._progress is not None:
            self._progress.console.print(message)
        else:
            print(message)

    def _build_progress_manager(self, total_hands: Optional[int]) -> Progress:
        if total_hands is not None and total_hands > 0:
            return Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("{task.completed} hands"),
            TimeElapsedColumn(),
        )

