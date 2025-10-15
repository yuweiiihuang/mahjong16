"""Graphical Mahjong table inspired by Tenhou for interactive play."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pygame

from domain import Mahjong16Env
from domain.tiles import tile_sort_key, tile_to_str

from app.session import HandSummaryPort, ScoreState, StepEvent, TableViewPort
from ui.interface import HumanInputProvider

Color = Tuple[int, int, int]


@dataclass
class InteractionOption:
    """Clickable option rendered in the action overlay."""

    action: Dict[str, Any]
    label: str
    kind: str = "button"
    tile: Optional[int] = None
    annotation: Optional[str] = None
    rect: Optional[pygame.Rect] = None


class MahjongPygameUI(TableViewPort, HandSummaryPort, HumanInputProvider):
    """Interactive pygame UI featuring graphical tiles and mouse controls."""

    width: int = 1280
    height: int = 800
    top_panel_height: int = 120
    bottom_panel_height: int = 220
    side_panel_width: int = 240
    overlay_height: int = 200

    tile_width: int = 54
    tile_height: int = 78
    tile_gap: int = 6
    small_tile_width: int = 40
    small_tile_height: int = 58
    small_tile_gap: int = 4

    table_color: Color = (9, 71, 34)
    panel_color: Color = (28, 36, 40)
    panel_outline: Color = (58, 76, 88)
    status_bg: Color = (18, 22, 26)
    text_color: Color = (236, 242, 248)
    accent_color: Color = (255, 206, 92)
    alert_color: Color = (240, 99, 90)

    def __init__(
        self,
        *,
        human_pid: Optional[int],
        n_players: int,
        log_dir: Optional[str] = None,
        emit_logs: bool = True,
    ) -> None:
        self.human_pid = human_pid if human_pid is not None else 0
        self.n_players = max(1, n_players)
        self.log_dir = log_dir
        self.emit_logs = emit_logs

        pygame.init()
        try:
            self.screen = pygame.display.set_mode((self.width, self.height))
        except pygame.error as exc:  # pragma: no cover - depends on host environment
            raise RuntimeError(
                "Unable to initialise Mahjong GUI window. "
                "If running in a headless environment set SDL_VIDEODRIVER=dummy."
            ) from exc
        pygame.display.set_caption("Mahjong16 GUI")
        self.clock = pygame.time.Clock()

        self.font = self._create_font(20)
        self.small_font = self._create_font(16)
        self.large_font = self._create_font(24, bold=True)
        self.tile_font = self._create_font(26, bold=True)
        self.tile_small_font = self._create_font(20, bold=True)

        self.env: Optional[Mahjong16Env] = None
        self.score_state: Optional[ScoreState] = None
        self.banner_text: str = "Mahjong16 GUI"
        self.hand_summaries: List[Dict[str, Any]] = []

        self.pending_options: List[InteractionOption] = []
        self.selection: Optional[Dict[str, Any]] = None
        self.interaction_prompt: Optional[str] = None
        self.last_action: Optional[Dict[str, Any]] = None
        self.discard_counter: int = 0
        self.last_seen_discard: Optional[Tuple[Optional[int], Any]] = None
        self.mouse_pos: Tuple[int, int] = (0, 0)

        self._update_display()

    # ------------------------------------------------------------------
    # SessionPort implementations

    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        self.env = env
        self.score_state = score_state
        self.banner_text = "Mahjong16 GUI session"
        self._reset_hand_state()
        self._update_display()

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.env = env
        self.score_state = score_state
        self.banner_text = f"Hand {hand_index} start · Jang {jang_index}"
        self._reset_hand_state()
        self._update_display()

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.env = env
        self.score_state = score_state

        claim_event = self._summarize_claim(event.info)
        if claim_event:
            self.last_action = claim_event

        if event.action_type == "DISCARD" and event.discarded_tile is not None:
            self.discard_counter += 1
            self.last_seen_discard = (event.acting_pid, event.discarded_tile)
            self.last_action = {
                "who": f"P{event.acting_pid}",
                "type": "DISCARD",
                "detail": tile_to_str(event.discarded_tile),
            }

        if (
            event.observation.get("phase") == "REACTION"
            and self.human_pid is not None
            and event.observation.get("player") == self.human_pid
        ):
            last_discard = getattr(env, "last_discard", None)
            if isinstance(last_discard, dict) and last_discard.get("tile") is not None:
                key = (last_discard.get("pid"), last_discard.get("tile"))
                if key != self.last_seen_discard:
                    self.discard_counter += 1
                    self.last_seen_discard = key
                    self.last_action = {
                        "who": f"P{last_discard.get('pid')}",
                        "type": "DISCARD",
                        "detail": tile_to_str(last_discard.get("tile")),
                    }

        self._update_display()

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.env = env
        self.score_state = score_state
        winner = getattr(env, "winner", None)
        if winner is not None:
            src = (getattr(env, "win_source", "") or "").upper()
            tile = getattr(env, "win_tile", None)
            tile_str = tile_to_str(tile) if isinstance(tile, int) else "?"
            self.banner_text = f"Hand {hand_index}: P{winner} {src} {tile_str}"
        else:
            self.banner_text = f"Hand {hand_index}: Draw"
        if payments:
            pay_parts = ", ".join(f"P{pid}:{amt:+}" for pid, amt in enumerate(payments))
            self.banner_text += f" · {pay_parts}"
        self._update_display()

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.env = env
        self.score_state = score_state
        self.hand_summaries = list(summaries)
        self.banner_text = "Session complete · close window to exit"
        self._update_display()
        self._await_window_close()

    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        self.hand_summaries.append(summary)

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        self.hand_summaries = list(summaries)

    # ------------------------------------------------------------------
    # HumanInputProvider implementation

    def choose_turn_action(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        options = self._build_turn_options(obs)
        prompt = "你的回合：點擊要執行的操作"
        return self._wait_for_action(options, prompt)

    def choose_reaction_action(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        options = self._build_reaction_options(obs)
        prompt = "他家出牌：請選擇回應"
        return self._wait_for_action(options, prompt)

    # ------------------------------------------------------------------
    # Internal helpers

    def _create_font(self, size: int, bold: bool = False) -> pygame.font.Font:
        candidates = ["Noto Sans CJK TC", "Microsoft YaHei", "Arial Unicode MS", "arial"]
        for name in candidates:
            try:
                font = pygame.font.SysFont(name, size, bold=bold)
                if font is not None:
                    return font
            except Exception:  # pragma: no cover - defensive fallback
                continue
        return pygame.font.Font(None, size)

    def _reset_hand_state(self) -> None:
        self.pending_options = []
        self.selection = None
        self.interaction_prompt = None
        self.last_action = None
        self.discard_counter = 0
        self.last_seen_discard = None

    def _await_window_close(self) -> None:
        while True:
            try:
                self._update_display()
            except SystemExit:
                break
            self.clock.tick(30)
        pygame.quit()

    def _handle_events(self, allow_selection: bool) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit("Mahjong GUI closed")
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                pygame.quit()
                raise SystemExit("Mahjong GUI terminated")
            if event.type == pygame.MOUSEMOTION:
                self.mouse_pos = event.pos
            if allow_selection and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for opt in self.pending_options:
                    if opt.rect and opt.rect.collidepoint(event.pos):
                        self.selection = dict(opt.action)
                        return

    def _wait_for_action(
        self,
        options: List[InteractionOption],
        prompt: str,
    ) -> Dict[str, Any]:
        if not options:
            return {"type": "PASS"}
        self.pending_options = options
        self.interaction_prompt = prompt
        self.selection = None
        while self.selection is None:
            self._update_display(allow_selection=True)
            self.clock.tick(60)
        action = dict(self.selection)
        self.pending_options = []
        self.interaction_prompt = None
        self.selection = None
        return action

    def _build_turn_options(self, obs: Dict[str, Any]) -> List[InteractionOption]:
        legal = list(obs.get("legal_actions") or [])
        discards = [a for a in legal if (a.get("type") or "").upper() == "DISCARD"]
        others = [a for a in legal if (a.get("type") or "").upper() != "DISCARD"]
        discards.sort(key=lambda a: self._tile_sort_key(a.get("tile")))
        options: List[InteractionOption] = []
        for act in discards:
            tile = act.get("tile")
            annotation = "drawn" if (act.get("from") or "hand") == "drawn" else None
            label = tile_to_str(tile) if isinstance(tile, int) else str(tile)
            options.append(
                InteractionOption(
                    action=dict(act),
                    label=label,
                    kind="tile",
                    tile=tile,
                    annotation=annotation,
                )
            )
        button_priority = {"HU": 0, "TING": 1, "ANGANG": 2, "KAKAN": 3}
        others.sort(key=lambda a: button_priority.get((a.get("type") or "").upper(), 10))
        options.extend(self._convert_to_buttons(others))
        return options

    def _build_reaction_options(self, obs: Dict[str, Any]) -> List[InteractionOption]:
        legal = list(obs.get("legal_actions") or [])
        priority = {"HU": 0, "GANG": 1, "PONG": 2, "CHI": 3, "PASS": 10}
        legal.sort(key=lambda a: priority.get((a.get("type") or "").upper(), 50))
        return self._convert_to_buttons(legal)

    def _convert_to_buttons(self, actions: Sequence[Dict[str, Any]]) -> List[InteractionOption]:
        options: List[InteractionOption] = []
        for act in actions:
            options.append(InteractionOption(action=dict(act), label=self._format_action_label(act)))
        return options

    def _format_action_label(self, act: Dict[str, Any]) -> str:
        kind = (act.get("type") or "").upper()
        tile = act.get("tile")
        if kind == "PASS":
            return "PASS"
        if kind == "CHI":
            use = act.get("use") or []
            tiles: List[int] = []
            if isinstance(use, Iterable):
                for value in use:
                    try:
                        tiles.append(int(value))
                    except Exception:
                        continue
            if len(tiles) == 2 and tile is not None:
                return f"CHI {tile_to_str(tiles[0])}-{tile_to_str(tiles[1])}+{tile_to_str(tile)}"
        if tile is not None:
            return f"{kind} {tile_to_str(tile)}"
        return kind or "?"

    def _tile_sort_key(self, tile: Any) -> Tuple[int, int, int]:
        if isinstance(tile, int):
            return tile_sort_key(tile)
        return (99, 99, 99)

    def _summarize_claim(self, info: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
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
            if tile is not None:
                detail = tile_to_str(tile)
        return {"who": f"P{pid}", "type": claim_type, "detail": detail}

    # ------------------------------------------------------------------
    # Rendering helpers

    def _update_display(self, allow_selection: bool = False) -> None:
        self._handle_events(allow_selection)
        self.screen.fill(self.table_color)
        self._draw_status_panel()
        if self.env is not None:
            for pid in range(self.n_players):
                self._draw_player_region(pid)
        if self.pending_options:
            self._draw_interaction_overlay()
        pygame.display.flip()

    def _draw_status_panel(self) -> None:
        rect = pygame.Rect(0, 0, self.width, self.top_panel_height)
        pygame.draw.rect(self.screen, self.status_bg, rect)
        pygame.draw.rect(self.screen, self.panel_outline, rect, width=1)
        if self.env is None:
            return
        qmap = {"E": "東", "S": "南", "W": "西", "N": "北"}
        qf = getattr(self.env, "quan_feng", "?")
        dealer_pid = getattr(self.env, "dealer_pid", None)
        seat_winds = getattr(self.env, "seat_winds", [])
        dealer_wind = None
        if (
            isinstance(dealer_pid, int)
            and isinstance(seat_winds, list)
            and 0 <= dealer_pid < len(seat_winds)
        ):
            dealer_wind = seat_winds[dealer_pid]
        dealer_label = f"P{dealer_pid}" if dealer_pid is not None else "?"
        if isinstance(dealer_wind, str):
            dealer_label += f"({qmap.get(dealer_wind.upper(), dealer_wind)})"
        if self.large_font:
            line1 = self.large_font.render(
                f"圈風: {qmap.get(str(qf).upper(), str(qf))}    莊家: {dealer_label}",
                True,
                self.text_color,
            )
            self.screen.blit(line1, (20, 14))
        remaining = len(getattr(self.env, "wall", []))
        mode = getattr(self.env.rules, "dead_wall_mode", "fixed")
        base = getattr(self.env.rules, "dead_wall_base", 16)
        reserved = base + getattr(self.env, "n_gang", 0) if mode == "gang_plus_one" else base
        turn = getattr(self.env, "turn", "?")
        phase = getattr(self.env, "phase", "?")
        if self.font:
            line2 = self.font.render(
                f"Turn: P{turn}  Phase: {phase}    Remaining: {remaining}   DeadWall: {reserved}",
                True,
                self.text_color,
            )
            self.screen.blit(line2, (20, 54))
        if self.discard_counter and self.small_font:
            disc = self.small_font.render(f"D{self.discard_counter:03d}", True, self.text_color)
            self.screen.blit(disc, (self.width - disc.get_width() - 20, 54))
        if self.score_state and self.small_font:
            totals = list(self.score_state.get("totals") or [])
            if totals:
                parts = "  ".join(f"P{idx}={total}" for idx, total in enumerate(totals))
                line3 = self.small_font.render(f"Points: {parts}", True, self.accent_color)
                self.screen.blit(line3, (20, 84))
        if self.last_action and self.small_font:
            detail = self.last_action.get("detail", "")
            last = self.small_font.render(
                f"Last: {self.last_action.get('who', '?')} {self.last_action.get('type', '')} {detail}",
                True,
                self.text_color,
            )
            self.screen.blit(last, (self.width - last.get_width() - 20, 84))
        if self.banner_text and self.small_font:
            banner = self.small_font.render(self.banner_text, True, self.accent_color)
            self.screen.blit(banner, (self.width - banner.get_width() - 20, 18))

    def _draw_player_region(self, pid: int) -> None:
        rel = (pid - self.human_pid) % self.n_players
        bottom_rect = pygame.Rect(0, self.height - self.bottom_panel_height, self.width, self.bottom_panel_height)
        top_rect = pygame.Rect(
            self.side_panel_width,
            self.top_panel_height + 10,
            self.width - 2 * self.side_panel_width,
            200,
        )
        side_height = self.height - self.top_panel_height - self.bottom_panel_height - 20
        left_rect = pygame.Rect(10, self.top_panel_height + 10, self.side_panel_width - 20, side_height)
        right_rect = pygame.Rect(
            self.width - self.side_panel_width + 10,
            self.top_panel_height + 10,
            self.side_panel_width - 20,
            side_height,
        )
        if rel == 0:
            self._draw_self_panel(pid, bottom_rect)
        elif rel == 1:
            if self.n_players == 2:
                self._draw_opposite_panel(pid, top_rect)
            else:
                self._draw_side_panel(pid, right_rect)
        elif rel == 2:
            if self.n_players <= 3:
                self._draw_side_panel(pid, left_rect)
            else:
                self._draw_opposite_panel(pid, top_rect)
        else:
            self._draw_side_panel(pid, left_rect)

    def _draw_self_panel(self, pid: int, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.panel_color, rect, border_radius=10)
        pygame.draw.rect(self.screen, self.panel_outline, rect, width=2, border_radius=10)
        assets = self._player_assets(pid)
        header = self._player_header_text(pid)
        color = self.accent_color if getattr(self.env, "turn", None) == pid else self.text_color
        if self.large_font:
            text = self.large_font.render(header, True, color)
            self.screen.blit(text, (rect.x + 18, rect.y + 12))
        info_parts: List[str] = []
        if assets["drawn"] is not None:
            info_parts.append(f"Drawn {tile_to_str(assets['drawn'])}")
        if assets.get("declared_ting"):
            info_parts.append("TING declared")
        if assets["flowers"]:
            info_parts.append(f"Flowers {len(assets['flowers'])}")
        if info_parts and self.small_font:
            info = self.small_font.render(" · ".join(info_parts), True, self.text_color)
            self.screen.blit(info, (rect.x + 18, rect.y + 50))
        meld_y = rect.y + 76
        if assets["melds"]:
            self._draw_melds(assets["melds"], (rect.x + 18, meld_y), max_width=rect.x + rect.width - 20)
            meld_y += self.small_tile_height + 16
        if assets["flowers"]:
            flowers = assets["flowers"]
            width = len(flowers) * (self.small_tile_width + self.small_tile_gap) - self.small_tile_gap
            start_x = rect.right - width - 20
            self._draw_tile_sequence(flowers, (start_x, rect.y + 76), tiles_per_row=8, small=True)
        river = assets["river"]
        river_highlight = self._river_highlight(pid, river)
        river_y = rect.bottom - self.tile_height - self.small_tile_height - 48
        if river_y < rect.y + 140:
            river_y = rect.y + 140
        self._draw_tile_sequence(river, (rect.x + 18, river_y), tiles_per_row=12, small=True, highlight_index=river_highlight)
        hand_tiles = [int(t) for t in assets["hand"]]
        hand_tiles.sort(key=tile_sort_key)
        hand_repr = [(tile, False) for tile in hand_tiles]
        if assets["drawn"] is not None:
            try:
                hand_repr.append((int(assets["drawn"]), True))
            except Exception:
                pass
        if hand_repr:
            total_width = len(hand_repr) * (self.tile_width + self.tile_gap) - self.tile_gap
            start_x = rect.x + max(18, (rect.width - total_width) // 2)
            hand_y = rect.bottom - self.tile_height - 24
            for tile, highlight in hand_repr:
                tile_rect = pygame.Rect(start_x, hand_y, self.tile_width, self.tile_height)
                self._draw_tile(tile_rect, tile, highlight=highlight)
                start_x += self.tile_width + self.tile_gap

    def _draw_opposite_panel(self, pid: int, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.panel_color, rect, border_radius=10)
        pygame.draw.rect(self.screen, self.panel_outline, rect, width=2, border_radius=10)
        assets = self._player_assets(pid)
        header = self._player_header_text(pid)
        color = self.accent_color if getattr(self.env, "turn", None) == pid else self.text_color
        if self.large_font:
            text = self.large_font.render(header, True, color)
            self.screen.blit(text, (rect.x + 18, rect.y + 12))
        total_tiles = len(assets["hand"]) + (1 if assets["drawn"] is not None else 0)
        extras: List[str] = [f"Hand {total_tiles} tiles"]
        if assets["melds"]:
            extras.append(f"{len(assets['melds'])} melds")
        if assets["flowers"]:
            extras.append(f"Flowers {len(assets['flowers'])}")
        if assets.get("declared_ting"):
            extras.append("TING")
        if self.small_font:
            info = self.small_font.render(" · ".join(extras), True, self.text_color)
            self.screen.blit(info, (rect.x + 18, rect.y + 52))
        hidden_y = rect.y + 82
        self._draw_hidden_tiles(total_tiles, (rect.x + 18, hidden_y), per_row=14)
        meld_y = hidden_y + self.small_tile_height + 12
        if assets["melds"]:
            self._draw_melds(assets["melds"], (rect.x + 18, meld_y), max_width=rect.x + rect.width - 20)
            meld_y += self.small_tile_height + 14
        river = assets["river"]
        highlight = self._river_highlight(pid, river)
        river_y = rect.bottom - self.small_tile_height - 16
        self._draw_tile_sequence(river, (rect.x + 18, river_y), tiles_per_row=14, small=True, highlight_index=highlight)
        if assets["flowers"]:
            width = len(assets["flowers"]) * (self.small_tile_width + self.small_tile_gap) - self.small_tile_gap
            start_x = rect.right - width - 20
            self._draw_tile_sequence(assets["flowers"], (start_x, rect.y + 82), tiles_per_row=8, small=True)

    def _draw_side_panel(self, pid: int, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.panel_color, rect, border_radius=10)
        pygame.draw.rect(self.screen, self.panel_outline, rect, width=2, border_radius=10)
        assets = self._player_assets(pid)
        header = self._player_header_text(pid)
        color = self.accent_color if getattr(self.env, "turn", None) == pid else self.text_color
        if self.large_font:
            text = self.large_font.render(header, True, color)
            self.screen.blit(text, (rect.x + 12, rect.y + 12))
        total_tiles = len(assets["hand"]) + (1 if assets["drawn"] is not None else 0)
        extras: List[str] = [f"Hand {total_tiles} tiles"]
        if assets["melds"]:
            extras.append(f"{len(assets['melds'])} melds")
        if assets["flowers"]:
            extras.append(f"Flowers {len(assets['flowers'])}")
        if assets.get("declared_ting"):
            extras.append("TING")
        if self.small_font:
            info = self.small_font.render(" · ".join(extras), True, self.text_color)
            self.screen.blit(info, (rect.x + 12, rect.y + 44))
        y = rect.y + 70
        if total_tiles:
            rows = self._draw_hidden_tiles(total_tiles, (rect.x + 12, y), per_row=3)
            y += rows * (self.small_tile_height + self.small_tile_gap) + 8
        if assets["melds"]:
            y = self._draw_melds(assets["melds"], (rect.x + 12, y), max_width=rect.x + rect.width - 12)
            y += 8
        river = assets["river"]
        highlight = self._river_highlight(pid, river)
        y = self._draw_tile_sequence(river, (rect.x + 12, y), tiles_per_row=3, small=True, highlight_index=highlight)
        if assets["flowers"]:
            self._draw_tile_sequence(assets["flowers"], (rect.x + 12, y + 6), tiles_per_row=3, small=True)

    def _player_assets(self, pid: int) -> Dict[str, Any]:
        empty = {
            "hand": [],
            "drawn": None,
            "melds": [],
            "flowers": [],
            "river": [],
            "declared_ting": False,
        }
        if self.env is None:
            return dict(empty)
        players = getattr(self.env, "players", None)
        if players is None or isinstance(players, (str, bytes)):
            return dict(empty)
        try:
            player = players[pid]
        except (TypeError, IndexError, KeyError):
            return dict(empty)
        if player is None:
            return dict(empty)

        if isinstance(player, dict):
            getter = player.get
        else:
            getter = lambda key, default=None: getattr(player, key, default)

        def _iterable(value: Any) -> Iterable[Any]:
            if value is None:
                return []
            if isinstance(value, (list, tuple)):
                return value
            if isinstance(value, set):
                return list(value)
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                return list(value)
            return []

        def _tile_list(value: Any) -> List[int]:
            tiles: List[int] = []
            for item in _iterable(value):
                if item is None:
                    continue
                try:
                    tiles.append(int(item))
                except (TypeError, ValueError):
                    continue
            return tiles

        hand = _tile_list(getter("hand"))
        hand.sort(key=tile_sort_key)
        melds_raw = getter("melds") or []
        melds = list(_iterable(melds_raw))
        flowers = _tile_list(getter("flowers"))
        flowers.sort(key=tile_sort_key)
        river = _tile_list(getter("river"))
        drawn = getter("drawn")
        try:
            drawn = int(drawn) if drawn is not None else None
        except (TypeError, ValueError):
            drawn = None

        return {
            "hand": hand,
            "drawn": drawn,
            "melds": melds,
            "flowers": flowers,
            "river": river,
            "declared_ting": bool(getter("declared_ting", False)),
        }

    def _player_header_text(self, pid: int) -> str:
        label = f"P{pid}"
        if pid == self.human_pid:
            label += " · You"
        seat_winds = getattr(self.env, "seat_winds", [])
        qmap = {"E": "東", "S": "南", "W": "西", "N": "北"}
        if isinstance(seat_winds, list) and 0 <= pid < len(seat_winds):
            wind = seat_winds[pid]
            if isinstance(wind, str) and wind:
                label += f" · {qmap.get(wind.upper(), wind)}"
        totals = []
        if self.score_state:
            totals = list(self.score_state.get("totals") or [])
        if totals and 0 <= pid < len(totals):
            label += f" · {totals[pid]} pts"
        return label

    def _draw_tile(self, rect: pygame.Rect, tile: Optional[int], *, highlight: bool = False, face_down: bool = False, small: bool = False) -> None:
        base = (245, 245, 245) if not face_down else (160, 160, 160)
        pygame.draw.rect(self.screen, base, rect, border_radius=6)
        pygame.draw.rect(self.screen, (40, 40, 40), rect, width=2, border_radius=6)
        if highlight:
            pygame.draw.rect(self.screen, self.accent_color, rect, width=4, border_radius=6)
        if face_down:
            inner = rect.inflate(-10, -10)
            pygame.draw.rect(self.screen, (100, 100, 100), inner, border_radius=4)
            return
        if tile is None:
            return
        label = tile_to_str(tile)
        font = self.tile_small_font if small else self.tile_font
        if font is None:
            return
        text = font.render(label, True, (30, 30, 30))
        self.screen.blit(
            text,
            (rect.x + (rect.width - text.get_width()) // 2, rect.y + (rect.height - text.get_height()) // 2),
        )

    def _draw_hidden_tiles(self, count: int, start: Tuple[int, int], *, per_row: int) -> int:
        if count <= 0:
            return 0
        x, y = start
        width = self.small_tile_width
        height = self.small_tile_height
        rows = 0
        for idx in range(count):
            rect = pygame.Rect(x, y, width, height)
            self._draw_tile(rect, None, face_down=True, small=True)
            x += width + self.small_tile_gap
            if (idx + 1) % per_row == 0:
                rows += 1
                x = start[0]
                y += height + self.small_tile_gap
        if count % per_row:
            rows += 1
        return rows

    def _draw_melds(
        self,
        melds: Sequence[Any],
        start: Tuple[int, int],
        *,
        max_width: Optional[int] = None,
    ) -> int:
        if not melds:
            return start[1]
        x, y = start
        width = self.small_tile_width
        height = self.small_tile_height
        gap = self.small_tile_gap
        for meld in melds:
            tiles = self._iter_meld_tiles(meld)
            for tile in tiles:
                if max_width is not None and x + width > max_width:
                    x = start[0]
                    y += height + gap
                rect = pygame.Rect(x, y, width, height)
                self._draw_tile(rect, tile, small=True)
                x += width + gap
            x += gap * 2
        return y + height

    def _draw_tile_sequence(
        self,
        tiles: Sequence[int],
        start: Tuple[int, int],
        *,
        tiles_per_row: int,
        small: bool = True,
        highlight_index: Optional[int] = None,
    ) -> int:
        if not tiles:
            return start[1]
        width = self.small_tile_width if small else self.tile_width
        height = self.small_tile_height if small else self.tile_height
        gap = self.small_tile_gap if small else self.tile_gap
        x, y = start
        for idx, tile in enumerate(tiles):
            rect = pygame.Rect(x, y, width, height)
            highlight = highlight_index is not None and idx == highlight_index
            self._draw_tile(rect, tile, highlight=highlight, small=small)
            x += width + gap
            if (idx + 1) % tiles_per_row == 0:
                x = start[0]
                y += height + gap
        if len(tiles) % tiles_per_row:
            y += height
        return y

    def _iter_meld_tiles(self, meld: Any) -> List[int]:
        tiles: List[int] = []
        values: Iterable[Any]
        if isinstance(meld, dict):
            values = meld.get("tiles") or []
        else:
            try:
                values = list(meld)
            except Exception:
                values = []
        for val in values:
            try:
                tiles.append(int(val))
            except Exception:
                continue
        tiles.sort(key=tile_sort_key)
        return tiles

    def _river_highlight(self, pid: int, river: Sequence[int]) -> Optional[int]:
        last = getattr(self.env, "last_discard", None)
        if isinstance(last, dict) and last.get("pid") == pid:
            tile = last.get("tile")
            for idx in range(len(river) - 1, -1, -1):
                if river[idx] == tile:
                    return idx
        return None

    def _draw_interaction_overlay(self) -> None:
        overlay_rect = pygame.Rect(0, self.height - self.overlay_height, self.width, self.overlay_height)
        surface = pygame.Surface((overlay_rect.width, overlay_rect.height), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 180))
        self.screen.blit(surface, overlay_rect.topleft)
        if self.interaction_prompt and self.large_font:
            prompt = self.large_font.render(self.interaction_prompt, True, self.text_color)
            self.screen.blit(prompt, (overlay_rect.x + 24, overlay_rect.y + 18))
        tile_opts = [opt for opt in self.pending_options if opt.kind == "tile"]
        button_opts = [opt for opt in self.pending_options if opt.kind != "tile"]
        base_y = overlay_rect.y + 64
        if tile_opts:
            total = len(tile_opts) * (self.tile_width + self.tile_gap) - self.tile_gap
            start_x = max(overlay_rect.x + 24, overlay_rect.x + (overlay_rect.width - total) // 2)
            for opt in tile_opts:
                rect = pygame.Rect(start_x, base_y, self.tile_width, self.tile_height)
                hover = rect.collidepoint(self.mouse_pos)
                opt.rect = rect
                self._draw_tile(rect, opt.tile, highlight=hover, small=False)
                if opt.annotation and self.small_font:
                    ann = self.small_font.render(opt.annotation, True, self.accent_color)
                    self.screen.blit(ann, (rect.centerx - ann.get_width() // 2, rect.bottom + 6))
                start_x += self.tile_width + self.tile_gap
            base_y += self.tile_height + 28
        if button_opts:
            x = overlay_rect.x + 30
            y = max(base_y, overlay_rect.y + overlay_rect.height - 70)
            for opt in button_opts:
                text = self.font.render(opt.label, True, self.text_color)
                width = text.get_width() + 28
                rect = pygame.Rect(x, y, width, 48)
                hover = rect.collidepoint(self.mouse_pos)
                opt.rect = rect
                fill = self.panel_outline if not hover else self.accent_color
                pygame.draw.rect(self.screen, fill, rect, border_radius=8)
                pygame.draw.rect(self.screen, self.text_color, rect, width=2, border_radius=8)
                self.screen.blit(
                    text,
                    (
                        rect.x + (rect.width - text.get_width()) // 2,
                        rect.y + (rect.height - text.get_height()) // 2,
                    ),
                )
                x += width + 16


__all__ = ["MahjongPygameUI"]
