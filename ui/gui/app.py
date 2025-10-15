"""Interactive Mahjong GUI built with pygame."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pygame

from domain import Mahjong16Env
from domain.analysis import simulate_after_discard, visible_count_after, visible_count_global
from domain.gameplay import Action, Observation
from domain.rules import Ruleset
from domain.rules.hands import waits_after_discard_17, waits_for_hand_16
from domain.tiles import tile_sort_key, tile_to_str

from app.session.adapters import ConsoleUIAdapter
from app.session.ports import HandSummaryPort, ScoreState, TableViewPort
from bots.policies import HumanInterface


@dataclass
class TileWait:
    tile: int
    remaining: int


@dataclass
class DiscardOption:
    action: Action
    tile: Optional[int]
    source: str
    waits: List[TileWait] = field(default_factory=list)

    @property
    def from_drawn(self) -> bool:
        return (self.source or "hand") == "drawn"


@dataclass
class PlayerView:
    pid: int
    wind: Optional[str]
    is_dealer: bool
    is_human: bool
    hand_tiles: List[int]
    drawn_tile: Optional[int]
    melds: List[Tuple[str, List[int]]]
    flowers: List[int]
    river: List[int]
    declared_ting: bool
    auto_mode: bool

    @property
    def concealed_count(self) -> int:
        return len(self.hand_tiles)


@dataclass
class TableState:
    quan: Optional[str]
    dealer_pid: Optional[int]
    seat_winds: List[Optional[str]]
    turn_pid: Optional[int]
    phase: str
    remaining_tiles: int
    dead_wall_reserved: int
    discard_id: int
    last_action: Optional[Dict[str, str]]
    last_discard: Optional[Dict[str, Any]]
    players: List[PlayerView]
    totals: List[int]
    deltas: List[int]
    winner: Optional[int]
    win_source: Optional[str]
    win_tile: Optional[int]


@dataclass
class TurnContext:
    hand: List[int]
    drawn: Optional[int]
    melds: List[Any]
    flowers: List[int]
    declared_ting: bool
    discard_options: List[DiscardOption]
    ting_candidates: List[DiscardOption]
    ting_actions: List[Action]
    hu_action: Optional[Action]
    angangs: List[Action]
    kakans: List[Action]
    waits_now: List[TileWait]


@dataclass
class ReactionOption:
    label: str
    action: Action
    priority: int


def _coerce_sequence(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _sorted_tiles(values: Any) -> List[int]:
    tiles: List[int] = []
    for tile in _coerce_sequence(values):
        try:
            tiles.append(int(tile))
        except (TypeError, ValueError):
            continue
    return sorted(tiles, key=tile_sort_key)


def _resolve_player_field(player: Any, field: str) -> Any:
    if isinstance(player, dict):
        return player.get(field)
    return getattr(player, field, None)


def _extract_melds(raw: Any) -> List[Tuple[str, List[int]]]:
    result: List[Tuple[str, List[int]]] = []
    for meld in _coerce_sequence(raw):
        kind = ""
        tiles: List[int] = []
        if isinstance(meld, dict):
            kind = (meld.get("type") or "").upper()
            source_tiles = meld.get("tiles") or meld.get("meld") or meld.get("cards")
            tiles = _sorted_tiles(source_tiles)
        else:
            kind = getattr(meld, "type", "")
            to_dict = getattr(meld, "to_dict", None)
            if callable(to_dict):
                try:
                    data = to_dict()
                except Exception:
                    data = None
                if isinstance(data, dict):
                    kind = (data.get("type") or kind or "").upper()
                    tiles = _sorted_tiles(data.get("tiles") or data.get("meld"))
            if not tiles:
                seq = getattr(meld, "tiles", None) or getattr(meld, "meld", None)
                tiles = _sorted_tiles(seq)
            if not kind:
                kind = str(getattr(meld, "meld_type", "")).upper()
        result.append((kind, tiles))
    return result


def _wind_label(wind: Optional[str]) -> Optional[str]:
    if not wind:
        return None
    mapping = {"E": "東", "S": "南", "W": "西", "N": "北"}
    key = str(wind).upper()
    return mapping.get(key, key)


def _format_tiles(tiles: Sequence[int]) -> str:
    parts = [tile_to_str(t) or "?" for t in tiles]
    return " ".join(parts)


def _format_waits(waits: Sequence[TileWait]) -> str:
    return ", ".join(f"{tile_to_str(w.tile) or '?'}({w.remaining})" for w in waits)


class MahjongGuiAdapter(TableViewPort, HandSummaryPort, HumanInterface):
    """Graphical TableViewPort implementation that also prompts for human input."""

    WINDOW_SIZE: Tuple[int, int] = (1280, 800)
    TOP_PANEL_HEIGHT = 150
    BOTTOM_PANEL_HEIGHT = 240
    TILE_SIZE = (44, 64)
    SMALL_TILE_SIZE = (32, 48)
    TILE_MARGIN = 6
    BUTTON_HEIGHT = 48
    FPS = 60

    def __init__(
        self,
        *,
        human_pid: Optional[int],
        n_players: int,
        log_dir: Optional[str] = None,
        enable_logging: bool = True,
    ) -> None:
        self.human_pid = human_pid
        self.n_players = n_players
        self.enable_logging = enable_logging
        self.log_adapter: Optional[ConsoleUIAdapter] = None
        if log_dir is not None:
            self.log_adapter = ConsoleUIAdapter(
                human_pid=human_pid,
                n_players=n_players,
                log_dir=log_dir,
                emit_logs=False,
            )

        self.screen = None
        self.clock = None
        self.font_small = None
        self.font_medium = None
        self.font_large = None
        self.font_tile = None
        self.font_tile_small = None

        self.theme = {
            "bg": (18, 36, 54),
            "panel": (36, 60, 90),
            "panel_alt": (44, 72, 108),
            "text": (234, 240, 255),
            "dim": (165, 180, 204),
            "highlight": (255, 196, 0),
            "warning": (232, 98, 80),
            "accent": (96, 196, 255),
            "tile_face": (250, 250, 248),
            "tile_back": (120, 130, 150),
            "tile_border": (40, 40, 40),
        }

        self.table_state: Optional[TableState] = None
        self.turn_context: Optional[TurnContext] = None
        self.reaction_options: List[ReactionOption] = []
        self.action_button_defs: List[Tuple[Action, str]] = []
        self.action_buttons: List[Tuple[pygame.Rect, Action, str]] = []
        self.tile_hitboxes: List[Tuple[pygame.Rect, Action]] = []
        self.hand_tiles_layout: List[Dict[str, Any]] = []
        self.pending_selection: Optional[Action] = None
        self.prompt_message: str = ""
        self.prompt_mode: Optional[str] = None
        self.hand_overlay: Optional[Dict[str, Any]] = None

        self.discard_counter = 0
        self.last_action_summary: Optional[Dict[str, str]] = None
        self._last_seen_discard: Optional[Tuple[Optional[int], Any]] = None
        self.session_results: List[Dict[str, Any]] = []
        self.running = True
        self._needs_full_redraw = True

        self._init_pygame()
        self._render_background()
        pygame.display.flip()

    # ------------------------------------------------------------------
    # Session lifecycle hooks
    # ------------------------------------------------------------------

    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        self._reset_session_state()
        if self.log_adapter is not None:
            self.log_adapter.on_session_start(env=env, score_state=score_state)
        self._capture_table_state(env, score_state)
        self._render()

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.discard_counter = 0
        self.last_action_summary = None
        self._last_seen_discard = None
        self.hand_overlay = None
        if self.log_adapter is not None:
            self.log_adapter.on_hand_start(
                hand_index=hand_index,
                jang_index=jang_index,
                env=env,
                score_state=score_state,
            )
        self._capture_table_state(env, score_state)
        self._render()

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        if self.log_adapter is not None:
            self.log_adapter.on_step(event=event, env=env, score_state=score_state)
        claim_event = self._summarize_claim(event.info)
        if claim_event:
            self.last_action_summary = claim_event
        if event.action_type == "DISCARD" and event.discarded_tile is not None:
            self.discard_counter += 1
            self._last_seen_discard = (event.acting_pid, event.discarded_tile)
            self.last_action_summary = {
                "who": f"P{event.acting_pid}",
                "type": "DISCARD",
                "detail": tile_to_str(event.discarded_tile),
            }
        else:
            last_discard = getattr(env, "last_discard", None)
            if isinstance(last_discard, dict) and last_discard.get("tile") is not None:
                key = (last_discard.get("pid"), last_discard.get("tile"))
                if key != self._last_seen_discard:
                    self.discard_counter += 1
                    self._last_seen_discard = key
                    self.last_action_summary = {
                        "who": f"P{last_discard.get('pid')}",
                        "type": "DISCARD",
                        "detail": tile_to_str(last_discard.get("tile")),
                    }
        self._capture_table_state(env, score_state)
        self._render()

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        if self.log_adapter is not None:
            self.log_adapter.on_hand_scored(
                hand_index=hand_index,
                breakdown=breakdown,
                payments=payments,
                env=env,
                score_state=score_state,
            )
        self.hand_overlay = {
            "hand_index": hand_index,
            "breakdown": breakdown,
            "payments": payments,
            "totals": list(score_state.get("totals", [])),
            "base": getattr(env.rules, "base_points", None),
            "tai": getattr(env.rules, "tai_points", None),
        }
        self.session_results.append(
            {
                "hand_index": hand_index,
                "breakdown": breakdown,
                "payments": payments,
                "totals": list(score_state.get("totals", [])),
            }
        )
        self._capture_table_state(env, score_state)
        self._render()

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        if self.log_adapter is not None:
            self.log_adapter.on_session_end(summaries=summaries, env=env, score_state=score_state)
        self.session_results = summaries
        self._capture_table_state(env, score_state)
        self._render(show_final_summary=True)

    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        if self.log_adapter is not None:
            self.log_adapter.on_hand_summary(summary)

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        if self.log_adapter is not None:
            self.log_adapter.finalize(summaries)

    # ------------------------------------------------------------------
    # HumanInterface implementation
    # ------------------------------------------------------------------

    def prompt_turn_action(self, obs: Observation) -> Action:
        self.prompt_mode = "TURN"
        self.turn_context = self._build_turn_context(obs)
        self.reaction_options = []
        self.pending_selection = None
        self.prompt_message = "Your turn: click a tile to discard or pick an action."
        self._prepare_turn_controls()
        return self._wait_for_action()

    def prompt_reaction_action(self, obs: Observation) -> Action:
        self.prompt_mode = "REACTION"
        self.turn_context = None
        self.pending_selection = None
        self.reaction_options = self._build_reaction_options(obs)
        last = obs.get("last_discard") if isinstance(obs, dict) else None
        if isinstance(last, dict) and last.get("tile") is not None:
            tile_text = tile_to_str(last.get("tile")) or "?"
            self.prompt_message = f"Respond to P{last.get('pid')} discard {tile_text}."
        else:
            self.prompt_message = "Choose a reaction action."
        self._prepare_reaction_controls()
        return self._wait_for_action()

    # ------------------------------------------------------------------
    # Internal helpers for session state and rendering
    # ------------------------------------------------------------------

    def _reset_session_state(self) -> None:
        self.discard_counter = 0
        self.last_action_summary = None
        self._last_seen_discard = None
        self.hand_overlay = None
        self.table_state = None
        self.turn_context = None
        self.reaction_options = []
        self.action_button_defs = []
        self.pending_selection = None
        self.prompt_mode = None
        self.prompt_message = ""

    def _init_pygame(self) -> None:
        pygame.init()
        pygame.display.set_caption("Mahjong16 GUI")
        self.screen = pygame.display.set_mode(self.WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.font_small = self._load_font(16)
        self.font_medium = self._load_font(20)
        self.font_large = self._load_font(28, bold=True)
        self.font_tile = self._load_font(24, bold=True)
        self.font_tile_small = self._load_font(18)

    def _load_font(self, size: int, bold: bool = False) -> pygame.font.Font:
        try:
            font = pygame.font.SysFont("Microsoft YaHei UI", size, bold=bold)
            if font is None:
                raise ValueError("fallback")
            return font
        except Exception:
            return pygame.font.SysFont(pygame.font.get_default_font(), size, bold=bold)

    def _render_background(self) -> None:
        if self.screen is None:
            return
        self.screen.fill(self.theme["bg"])

    def _draw_status_bar(self, state: TableState) -> None:
        assert self.screen is not None
        rect = pygame.Rect(0, 0, self.WINDOW_SIZE[0], self.TOP_PANEL_HEIGHT)
        pygame.draw.rect(self.screen, self.theme["panel"], rect)

        padding_x = 24
        y = rect.top + 12

        quan_label = _wind_label(state.quan) or str(state.quan or "?")
        dealer_text = "?"
        if isinstance(state.dealer_pid, int):
            dealer_text = f"P{state.dealer_pid}"
            if 0 <= state.dealer_pid < len(state.seat_winds):
                seat = state.seat_winds[state.dealer_pid]
                if seat:
                    dealer_text += f"({seat})"

        header = f"圈風: {quan_label}   莊家: {dealer_text}"
        header_surface = self.font_large.render(header, True, self.theme["text"])
        self.screen.blit(header_surface, (padding_x, y))
        y += header_surface.get_height() + 6

        turn_text = "?" if state.turn_pid is None else f"P{state.turn_pid}"
        phase_line = f"Turn: {turn_text}  Phase: {state.phase}"
        phase_surface = self.font_medium.render(phase_line, True, self.theme["text"])
        self.screen.blit(phase_surface, (padding_x, y))

        remaining_line = f"Remaining: {state.remaining_tiles}  |  DeadWall: {state.dead_wall_reserved}"
        remaining_surface = self.font_medium.render(remaining_line, True, self.theme["text"])
        self.screen.blit(remaining_surface, (padding_x + 400, y))

        did_text = f"D{state.discard_id:03d}"
        did_surface = self.font_medium.render(did_text, True, self.theme["dim"])
        self.screen.blit(did_surface, (rect.right - did_surface.get_width() - padding_x, y))
        y += phase_surface.get_height() + 4

        if state.totals:
            parts = []
            for pid, total in enumerate(state.totals):
                parts.append(f"P{pid}={total}")
            points_line = "  ".join(parts)
            points_surface = self.font_medium.render(points_line, True, self.theme["text"])
            self.screen.blit(points_surface, (padding_x, y))
            y += points_surface.get_height() + 4

        if state.last_action:
            action_line = f"{state.last_action.get('who', '?')} {state.last_action.get('type', '')} {state.last_action.get('detail', '')}".strip()
        else:
            action_line = "(no action)"
        action_surface = self.font_medium.render(action_line, True, self.theme["dim"])
        self.screen.blit(action_surface, (padding_x, y))

    def _handle_events(self, allow_selection: bool = False) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                raise KeyboardInterrupt("GUI closed")
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
                raise KeyboardInterrupt("GUI closed")
            if allow_selection and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._process_click(event.pos)

    def _process_click(self, position: Tuple[int, int]) -> None:
        if self.pending_selection is not None:
            return
        for rect, action in self.tile_hitboxes:
            if rect.collidepoint(position):
                self.pending_selection = dict(action)
                return
        for rect, action, _ in self.action_buttons:
            if rect.collidepoint(position):
                self.pending_selection = dict(action)
                return

    def _draw_table_area(self, state: TableState) -> None:
        assert self.screen is not None
        board_rect = pygame.Rect(
            0,
            self.TOP_PANEL_HEIGHT,
            self.WINDOW_SIZE[0],
            self.WINDOW_SIZE[1] - self.TOP_PANEL_HEIGHT - self.BOTTOM_PANEL_HEIGHT,
        )
        pygame.draw.rect(self.screen, self.theme["panel_alt"], board_rect)

        rects = self._player_rects(board_rect)
        for orientation, player in self._ordered_players(state):
            target_rect = rects.get(orientation)
            if target_rect is None:
                continue
            self._draw_player_panel(state, player, orientation, target_rect)

    def _ordered_players(self, state: TableState) -> List[Tuple[str, PlayerView]]:
        mapping = {player.pid: player for player in state.players}
        if not mapping:
            return []
        n = len(mapping)
        orientations = ["south", "west", "north", "east"]

        def starting_pid() -> int:
            if self.human_pid is not None and self.human_pid in mapping:
                return self.human_pid
            if isinstance(state.dealer_pid, int) and state.dealer_pid in mapping:
                return state.dealer_pid
            return min(mapping.keys())

        start = starting_pid()
        ordered: List[Tuple[str, PlayerView]] = []
        for offset in range(min(4, n)):
            pid = (start + offset) % n
            player = mapping.get(pid)
            if player is None:
                continue
            ordered.append((orientations[offset % 4], player))

        if len(ordered) < n:
            remaining = [pid for pid in mapping.keys() if pid not in {p.pid for _, p in ordered}]
            for pid in remaining:
                orientation = orientations[len(ordered) % 4]
                ordered.append((orientation, mapping[pid]))
        return ordered

    def _player_rects(self, board_rect: pygame.Rect) -> Dict[str, pygame.Rect]:
        width = board_rect.width
        height = board_rect.height
        rects: Dict[str, pygame.Rect] = {
            "south": pygame.Rect(
                board_rect.left + 200,
                board_rect.bottom - 150,
                max(200, width - 400),
                130,
            ),
            "north": pygame.Rect(
                board_rect.left + 200,
                board_rect.top + 20,
                max(200, width - 400),
                130,
            ),
            "west": pygame.Rect(
                board_rect.left + 20,
                board_rect.top + 30,
                180,
                max(200, height - 60),
            ),
            "east": pygame.Rect(
                board_rect.right - 200,
                board_rect.top + 30,
                180,
                max(200, height - 60),
            ),
        }
        return rects

    def _draw_player_panel(
        self,
        state: TableState,
        player: PlayerView,
        orientation: str,
        rect: pygame.Rect,
    ) -> None:
        assert self.screen is not None
        pygame.draw.rect(self.screen, self.theme["panel"], rect, border_radius=12)
        inner = rect.inflate(-12, -12)

        header_parts = [f"P{player.pid}"]
        seat_label = None
        if 0 <= player.pid < len(state.seat_winds):
            seat_label = state.seat_winds[player.pid]
        if seat_label:
            header_parts.append(f"[{seat_label}]")
        if player.is_dealer:
            header_parts.append("(莊)")
        if player.is_human:
            header_parts.append("(You)")
        title = " ".join(header_parts)

        title_surface = self.font_medium.render(title, True, self.theme["text"])
        self.screen.blit(title_surface, (inner.left, inner.top))
        status_x = inner.left
        status_y = inner.top + title_surface.get_height() + 4

        status_tags: List[str] = []
        if player.declared_ting:
            status_tags.append("TING")
        if player.auto_mode:
            status_tags.append("AUTO")
        if status_tags:
            status_line = "  ".join(status_tags)
            status_surface = self.font_small.render(status_line, True, self.theme["highlight"])
            self.screen.blit(status_surface, (status_x, status_y))
            status_y += status_surface.get_height() + 4

        hand_info_y = status_y
        if orientation != "south":
            concealed_rect = pygame.Rect(inner.left, hand_info_y, inner.width, 40)
            self._draw_concealed_tiles(concealed_rect, player.concealed_count)
            hand_info_y = concealed_rect.bottom + 6
        elif self.turn_context is None:
            # Idle state: show the human hand count even if bottom panel will render tiles.
            info_line = f"Hand: {player.concealed_count} tiles"
            info_surface = self.font_small.render(info_line, True, self.theme["dim"])
            self.screen.blit(info_surface, (inner.left, hand_info_y))
            hand_info_y += info_surface.get_height() + 4

        meld_rect = pygame.Rect(inner.left, hand_info_y, inner.width, 60)
        self._draw_melds(meld_rect, player.melds)
        hand_info_y = meld_rect.bottom + 6

        river_rect = pygame.Rect(inner.left, hand_info_y, inner.width, inner.bottom - hand_info_y - 24)
        self._draw_river(river_rect, player, state)

        flowers_rect = pygame.Rect(inner.left, inner.bottom - 20, inner.width, 20)
        self._draw_flowers(flowers_rect, player.flowers)

    def _draw_concealed_tiles(self, rect: pygame.Rect, count: int) -> None:
        assert self.screen is not None
        if count <= 0:
            info_surface = self.font_small.render("Hand: (empty)", True, self.theme["dim"])
            self.screen.blit(info_surface, (rect.left, rect.top))
            return
        tile_width, tile_height = self.SMALL_TILE_SIZE
        spacing = self.TILE_MARGIN
        max_per_row = max(1, rect.width // (tile_width + spacing))
        x = rect.left
        y = rect.top
        for idx in range(count):
            tile_rect = pygame.Rect(x, y, tile_width, tile_height)
            self._draw_tile_surface(tile_rect, None, face_down=True, small=True)
            x += tile_width + spacing
            if max_per_row and (idx + 1) % max_per_row == 0:
                x = rect.left
                y += tile_height + spacing

    def _draw_melds(self, rect: pygame.Rect, melds: List[Tuple[str, List[int]]]) -> None:
        assert self.screen is not None
        x = rect.left
        y = rect.top
        spacing = self.TILE_MARGIN
        for kind, tiles in melds:
            label = kind or "MELD"
            label_surface = self.font_small.render(label, True, self.theme["dim"])
            self.screen.blit(label_surface, (x, y))
            y_inner = y + label_surface.get_height() + 2
            for tile in tiles:
                tile_rect = pygame.Rect(x, y_inner, self.SMALL_TILE_SIZE[0], self.SMALL_TILE_SIZE[1])
                self._draw_tile_surface(tile_rect, tile, small=True)
                x += self.SMALL_TILE_SIZE[0] + spacing
            x += spacing * 2
            if x + self.SMALL_TILE_SIZE[0] > rect.right:
                x = rect.left
                y = y_inner + self.SMALL_TILE_SIZE[1] + spacing
            else:
                y = rect.top

    def _draw_river(self, rect: pygame.Rect, player: PlayerView, state: TableState) -> None:
        assert self.screen is not None
        tiles = player.river
        if not tiles:
            label_surface = self.font_small.render("River: (empty)", True, self.theme["dim"])
            self.screen.blit(label_surface, (rect.left, rect.top))
            return
        highlight_idx = None
        last = state.last_discard
        if last and last.get("pid") == player.pid:
            try:
                target_tile = int(last.get("tile"))
            except (TypeError, ValueError):
                target_tile = None
            if target_tile is not None:
                for idx in range(len(tiles) - 1, -1, -1):
                    if tiles[idx] == target_tile:
                        highlight_idx = idx
                        break
        x = rect.left
        y = rect.top
        spacing = self.TILE_MARGIN
        per_row = max(1, rect.width // (self.SMALL_TILE_SIZE[0] + spacing))
        for idx, tile in enumerate(tiles):
            tile_rect = pygame.Rect(x, y, self.SMALL_TILE_SIZE[0], self.SMALL_TILE_SIZE[1])
            highlight = highlight_idx is not None and idx == highlight_idx
            self._draw_tile_surface(tile_rect, tile, highlight=highlight, small=True)
            x += self.SMALL_TILE_SIZE[0] + spacing
            if per_row and (idx + 1) % per_row == 0:
                x = rect.left
                y += self.SMALL_TILE_SIZE[1] + spacing

    def _draw_flowers(self, rect: pygame.Rect, flowers: List[int]) -> None:
        assert self.screen is not None
        if not flowers:
            return
        label_surface = self.font_small.render("Flowers:", True, self.theme["dim"])
        self.screen.blit(label_surface, (rect.left, rect.top))
        x = rect.left + label_surface.get_width() + 8
        for tile in flowers:
            tile_rect = pygame.Rect(x, rect.top, self.SMALL_TILE_SIZE[0] // 2 + 6, self.SMALL_TILE_SIZE[1] // 2)
            self._draw_tile_surface(tile_rect, tile, small=True)
            x += tile_rect.width + 4

    def _draw_tile_surface(
        self,
        rect: pygame.Rect,
        tile: Optional[int],
        *,
        face_down: bool = False,
        highlight: bool = False,
        small: bool = False,
    ) -> None:
        assert self.screen is not None
        color = self.theme["tile_back"] if face_down else self.theme["tile_face"]
        pygame.draw.rect(self.screen, color, rect, border_radius=6)
        border_color = self.theme["highlight"] if highlight else self.theme["tile_border"]
        pygame.draw.rect(self.screen, border_color, rect, width=2, border_radius=6)
        if not face_down and tile is not None:
            label = tile_to_str(tile) or "?"
            font = self.font_tile_small if small else self.font_tile
            text = font.render(label, True, self.theme["tile_border"])
            text_rect = text.get_rect(center=rect.center)
            self.screen.blit(text, text_rect)

    def _draw_bottom_panel(self, state: TableState) -> None:
        assert self.screen is not None
        rect = pygame.Rect(
            0,
            self.WINDOW_SIZE[1] - self.BOTTOM_PANEL_HEIGHT,
            self.WINDOW_SIZE[0],
            self.BOTTOM_PANEL_HEIGHT,
        )
        pygame.draw.rect(self.screen, self.theme["panel"], rect)
        inner = rect.inflate(-24, -18)

        player = self._resolve_bottom_player(state)
        if player is None:
            return

        header_parts = [f"P{player.pid}"]
        if 0 <= player.pid < len(state.seat_winds):
            seat = state.seat_winds[player.pid]
            if seat:
                header_parts.append(f"[{seat}]")
        if player.is_dealer:
            header_parts.append("(莊)")
        if player.is_human:
            header_parts.append("(You)")
        header_text = " ".join(header_parts)
        header_surface = self.font_medium.render(header_text, True, self.theme["text"])
        self.screen.blit(header_surface, (inner.left, inner.top))

        if state.totals and player.pid < len(state.totals):
            points_text = f"Points: {state.totals[player.pid]}"
            points_surface = self.font_small.render(points_text, True, self.theme["text"])
            self.screen.blit(points_surface, (inner.left + header_surface.get_width() + 20, inner.top + 4))

        tile_area_top = inner.top + header_surface.get_height() + 8
        tile_area_height = self.TILE_SIZE[1] + 10
        tile_area = pygame.Rect(inner.left, tile_area_top, int(inner.width * 0.7), tile_area_height)
        info_area = pygame.Rect(tile_area.right + 16, tile_area_top, inner.right - tile_area.right - 16, tile_area.height + 70)

        interactive = self.prompt_mode == "TURN" and self.turn_context is not None
        layout = self.hand_tiles_layout if interactive and self.hand_tiles_layout else self._build_passive_hand_layout(player)
        self.tile_hitboxes = []
        self._draw_hand_tiles(tile_area, layout, interactive)

        self._draw_hand_info(info_area, player, state, interactive)

        buttons_top = tile_area.bottom + 24
        self._draw_action_buttons(inner, buttons_top)

    def _resolve_bottom_player(self, state: TableState) -> Optional[PlayerView]:
        target_pid: Optional[int] = self.human_pid
        if target_pid is None:
            target_pid = state.turn_pid if isinstance(state.turn_pid, int) else None
        if target_pid is None and state.players:
            target_pid = state.players[0].pid
        for player in state.players:
            if player.pid == target_pid:
                return player
        return state.players[0] if state.players else None

    def _build_passive_hand_layout(self, player: PlayerView) -> List[Dict[str, Any]]:
        layout: List[Dict[str, Any]] = []
        for tile in sorted(player.hand_tiles, key=tile_sort_key):
            layout.append({"tile": tile, "source": "hand", "action": None, "waits": []})
        if player.drawn_tile is not None:
            layout.append({"tile": player.drawn_tile, "source": "drawn", "action": None, "waits": []})
        return layout

    def _draw_hand_tiles(self, area: pygame.Rect, layout: List[Dict[str, Any]], interactive: bool) -> None:
        assert self.screen is not None
        if not layout:
            msg_surface = self.font_small.render("Hand: (empty)", True, self.theme["dim"])
            self.screen.blit(msg_surface, (area.left, area.top))
            return
        tile_width, tile_height = self.TILE_SIZE
        spacing = self.TILE_MARGIN
        total_width = len(layout) * tile_width + (len(layout) - 1) * spacing
        start_x = area.left + max(0, (area.width - total_width) // 2)
        x = start_x
        y = area.top
        for entry in layout:
            rect = pygame.Rect(x, y, tile_width, tile_height)
            entry["rect"] = rect
            highlight = interactive and entry.get("action") is not None
            self._draw_tile_surface(rect, entry.get("tile"), highlight=highlight)
            if entry.get("source") == "drawn":
                self._draw_drawn_indicator(rect)
            if interactive and entry.get("action") is not None:
                self.tile_hitboxes.append((rect.copy(), entry["action"]))
            x += tile_width + spacing

    def _draw_drawn_indicator(self, rect: pygame.Rect) -> None:
        assert self.screen is not None
        points = [
            (rect.right - 12, rect.top + 4),
            (rect.right - 4, rect.top + 4),
            (rect.right - 4, rect.top + 12),
        ]
        pygame.draw.polygon(self.screen, self.theme["accent"], points)

    def _draw_hand_info(
        self,
        area: pygame.Rect,
        player: PlayerView,
        state: TableState,
        interactive: bool,
    ) -> None:
        assert self.screen is not None
        lines: List[str] = []
        if interactive and self.turn_context is not None:
            ctx = self.turn_context
            if ctx.declared_ting and ctx.waits_now:
                lines.append("TING waits: " + _format_waits(ctx.waits_now))
            if ctx.ting_candidates:
                lines.append("Discard → waits:")
                for option in ctx.ting_candidates:
                    waits_text = _format_waits(option.waits)
                    tile_text = tile_to_str(option.tile) or "?"
                    marker = "(drawn)" if option.from_drawn else ""
                    lines.append(f"  {tile_text}{marker}: {waits_text}")
            if ctx.angangs or ctx.kakans:
                kong_labels = []
                for action in ctx.angangs:
                    kong_labels.append(f"ANGANG {tile_to_str(action.get('tile'))}")
                for action in ctx.kakans:
                    kong_labels.append(f"KAKAN {tile_to_str(action.get('tile'))}")
                lines.append("Kong options: " + ", ".join(filter(None, kong_labels)))
            if ctx.flowers:
                lines.append("Flowers: " + _format_tiles(ctx.flowers))
        else:
            meld_texts = []
            for kind, tiles in player.melds:
                meld_desc = f"{kind}: {_format_tiles(tiles)}" if tiles else kind
                meld_texts.append(meld_desc)
            if meld_texts:
                lines.append("Melds: " + "; ".join(meld_texts))
            if player.flowers:
                lines.append("Flowers: " + _format_tiles(player.flowers))

        if self.prompt_message:
            if lines:
                lines.append("")
            lines.append(self.prompt_message)

        y = area.top
        for line in lines:
            surface = self.font_small.render(line, True, self.theme["text"])
            self.screen.blit(surface, (area.left, y))
            y += surface.get_height() + 4

    def _draw_action_buttons(self, inner: pygame.Rect, y_top: int) -> None:
        assert self.screen is not None
        self.action_buttons = []
        if not self.action_button_defs:
            return
        button_width = 150
        spacing = 12
        x = inner.left
        y = y_top
        for action, label in self.action_button_defs:
            rect = pygame.Rect(x, y, button_width, self.BUTTON_HEIGHT)
            pygame.draw.rect(self.screen, self.theme["panel_alt"], rect, border_radius=10)
            border_color = self.theme["highlight"] if self.prompt_mode == "REACTION" and action.get("type") == "HU" else self.theme["tile_border"]
            pygame.draw.rect(self.screen, border_color, rect, width=2, border_radius=10)
            text_surface = self.font_small.render(label, True, self.theme["text"])
            text_rect = text_surface.get_rect(center=rect.center)
            self.screen.blit(text_surface, text_rect)
            self.action_buttons.append((rect, action, label))
            x += button_width + spacing
            if x + button_width > inner.right:
                x = inner.left
                y += self.BUTTON_HEIGHT + spacing

    def _draw_hand_result_overlay(self, state: TableState) -> None:
        assert self.screen is not None
        if not self.hand_overlay:
            return
        overlay_rect = pygame.Rect(
            80,
            self.TOP_PANEL_HEIGHT + 40,
            self.WINDOW_SIZE[0] - 160,
            160,
        )
        surface = pygame.Surface((overlay_rect.width, overlay_rect.height), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 180))
        self.screen.blit(surface, overlay_rect.topleft)

        title = f"Hand {self.hand_overlay.get('hand_index')} Settlement"
        title_surface = self.font_medium.render(title, True, self.theme["text"])
        self.screen.blit(title_surface, (overlay_rect.left + 16, overlay_rect.top + 12))

        base = self.hand_overlay.get("base")
        tai = self.hand_overlay.get("tai")
        extras: List[str] = []
        if base is not None:
            extras.append(f"base {base}")
        if tai is not None:
            extras.append(f"tai {tai}")
        if extras:
            info_surface = self.font_small.render(", ".join(extras), True, self.theme["text"])
            self.screen.blit(info_surface, (overlay_rect.left + 16, overlay_rect.top + 12 + title_surface.get_height()))

        payments = self.hand_overlay.get("payments") or []
        totals = self.hand_overlay.get("totals") or state.totals
        y = overlay_rect.top + 60
        for pid in range(len(totals)):
            pay = payments[pid] if pid < len(payments) else 0
            total = totals[pid] if pid < len(totals) else 0
            line = f"P{pid}: Δ {pay:+}   total {total}"
            line_surface = self.font_small.render(line, True, self.theme["text"])
            self.screen.blit(line_surface, (overlay_rect.left + 24, y))
            y += line_surface.get_height() + 6

    def _draw_session_summary_overlay(self, state: TableState) -> None:
        assert self.screen is not None
        overlay_rect = pygame.Rect(
            120,
            self.TOP_PANEL_HEIGHT + 80,
            self.WINDOW_SIZE[0] - 240,
            220,
        )
        surface = pygame.Surface((overlay_rect.width, overlay_rect.height), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 200))
        self.screen.blit(surface, overlay_rect.topleft)

        title_surface = self.font_medium.render("Session Complete", True, self.theme["text"])
        self.screen.blit(title_surface, (overlay_rect.left + 16, overlay_rect.top + 12))

        y = overlay_rect.top + 60
        for pid, total in enumerate(state.totals):
            line = f"P{pid}: {total}"
            line_surface = self.font_small.render(line, True, self.theme["text"])
            self.screen.blit(line_surface, (overlay_rect.left + 24, y))
            y += line_surface.get_height() + 6

        if self.session_results:
            summary_line = f"Hands played: {len(self.session_results)}"
            summary_surface = self.font_small.render(summary_line, True, self.theme["text"])
            self.screen.blit(summary_surface, (overlay_rect.left + 24, y + 10))

    def _wait_for_action(self) -> Action:
        while self.pending_selection is None:
            self._render()
            self.clock.tick(self.FPS)
        return dict(self.pending_selection)

    # Placeholder methods (implemented later in the file)
    def _capture_table_state(self, env: Mahjong16Env, score_state: ScoreState) -> None:
        players_raw = getattr(env, "players", [])
        seat_winds_raw = list(getattr(env, "seat_winds", []) or [])

        players: List[PlayerView] = []
        if isinstance(players_raw, Sequence):
            for pid, player in enumerate(players_raw):
                if pid >= self.n_players:
                    break
                hand_tiles = _sorted_tiles(_resolve_player_field(player, "hand"))
                drawn_tile = _resolve_player_field(player, "drawn")
                try:
                    drawn_tile = int(drawn_tile) if drawn_tile is not None else None
                except (TypeError, ValueError):
                    drawn_tile = None
                melds = _extract_melds(_resolve_player_field(player, "melds"))
                flowers = _sorted_tiles(_resolve_player_field(player, "flowers"))
                river = _sorted_tiles(_resolve_player_field(player, "river"))
                declared_ting = bool(_resolve_player_field(player, "declared_ting"))
                auto_mode = bool(
                    _resolve_player_field(player, "auto")
                    or _resolve_player_field(player, "auto_discard")
                )
                wind = None
                if pid < len(seat_winds_raw):
                    wind = seat_winds_raw[pid]
                players.append(
                    PlayerView(
                        pid=pid,
                        wind=wind,
                        is_dealer=(pid == getattr(env, "dealer_pid", None)),
                        is_human=(self.human_pid is not None and pid == self.human_pid),
                        hand_tiles=hand_tiles,
                        drawn_tile=drawn_tile,
                        melds=melds,
                        flowers=flowers,
                        river=river,
                        declared_ting=declared_ting,
                        auto_mode=auto_mode,
                    )
                )

        mode = getattr(env.rules, "dead_wall_mode", "fixed")
        base = getattr(env.rules, "dead_wall_base", 16)
        if mode == "gang_plus_one":
            reserved = base + getattr(env, "n_gang", 0)
        else:
            reserved = base

        last_discard = getattr(env, "last_discard", None)
        last_discard_dict = dict(last_discard) if isinstance(last_discard, dict) else None

        totals = list(score_state.get("totals", [])) if isinstance(score_state, dict) else []
        deltas = list(score_state.get("deltas", [])) if isinstance(score_state, dict) else []

        self.table_state = TableState(
            quan=getattr(env, "quan_feng", None),
            dealer_pid=getattr(env, "dealer_pid", None),
            seat_winds=[_wind_label(w) for w in seat_winds_raw],
            turn_pid=getattr(env, "turn", None),
            phase=str(getattr(env, "phase", "")),
            remaining_tiles=len(getattr(env, "wall", [])),
            dead_wall_reserved=int(reserved),
            discard_id=self.discard_counter,
            last_action=dict(self.last_action_summary) if self.last_action_summary else None,
            last_discard=last_discard_dict,
            players=players,
            totals=totals,
            deltas=deltas,
            winner=getattr(env, "winner", None),
            win_source=getattr(env, "win_source", None),
            win_tile=getattr(env, "win_tile", None),
        )
        self._needs_full_redraw = True

    def _render(self, show_final_summary: bool = False) -> None:
        allow_selection = (
            self.pending_selection is None and self.prompt_mode in {"TURN", "REACTION"}
        )
        self._handle_events(allow_selection=allow_selection)
        if self.screen is None:
            return
        self._render_background()
        if self.table_state is None:
            pygame.display.flip()
            return

        state = self.table_state
        self._draw_status_bar(state)
        self._draw_table_area(state)
        self._draw_bottom_panel(state)

        if show_final_summary:
            self._draw_session_summary_overlay(state)
        elif self.hand_overlay is not None:
            self._draw_hand_result_overlay(state)

        pygame.display.flip()

    def _build_turn_context(self, obs: Observation) -> TurnContext:
        acts: List[Action] = obs.get("legal_actions", []) or []
        hand = list(obs.get("hand") or [])
        drawn = obs.get("drawn")
        melds = list(obs.get("melds") or [])
        flowers = list(obs.get("flowers") or [])
        declared_ting = bool(obs.get("declared_ting"))

        def _to_int(value: Any) -> Optional[int]:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        drawn_tile = _to_int(drawn)

        discard_actions = [a for a in acts if (a.get("type") or "").upper() == "DISCARD"]
        discard_actions.sort(
            key=lambda a: (
                0 if (a.get("from") or "hand") == "hand" else 1,
                *tile_sort_key(_to_int(a.get("tile"))),
            )
        )

        discard_options: List[DiscardOption] = []
        ting_candidates: List[DiscardOption] = []
        rules = Ruleset(include_flowers=False)
        for action in discard_actions:
            tile = _to_int(action.get("tile"))
            source = action.get("from", "hand")
            waits_raw = waits_after_discard_17(
                hand,
                drawn_tile,
                melds,
                tile,
                source,
                rules=rules,
                exclude_exhausted=True,
            )
            waits_list: List[TileWait] = []
            waits_sorted = sorted(waits_raw, key=tile_sort_key)
            for wait_tile in waits_sorted:
                remaining: int
                if declared_ting:
                    visible = visible_count_global(wait_tile, obs)
                    remaining = max(0, 4 - min(4, visible))
                else:
                    hand_after = simulate_after_discard(hand, drawn_tile, tile, source)
                    visible = visible_count_after(wait_tile, hand_after, obs)
                    remaining = max(0, 4 - min(4, visible))
                waits_list.append(TileWait(tile=wait_tile, remaining=remaining))
            option = DiscardOption(action=action, tile=tile, source=source, waits=waits_list)
            discard_options.append(option)
            if waits_list:
                ting_candidates.append(option)

        ting_actions = [a for a in acts if (a.get("type") or "").upper() == "TING"]
        hu_action = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
        angangs = [a for a in acts if (a.get("type") or "").upper() == "ANGANG"]
        kakans = [a for a in acts if (a.get("type") or "").upper() == "KAKAN"]

        waits_now: List[TileWait] = []
        if declared_ting:
            waits_current = waits_for_hand_16(hand, melds, rules, exclude_exhausted=True)
            waits_now = [
                TileWait(tile=w, remaining=max(0, 4 - min(4, visible_count_global(w, obs))))
                for w in sorted(waits_current, key=tile_sort_key)
            ]

        return TurnContext(
            hand=hand,
            drawn=drawn_tile,
            melds=melds,
            flowers=flowers,
            declared_ting=declared_ting,
            discard_options=discard_options,
            ting_candidates=ting_candidates,
            ting_actions=ting_actions,
            hu_action=hu_action,
            angangs=angangs,
            kakans=kakans,
            waits_now=waits_now,
        )

    def _prepare_turn_controls(self) -> None:
        ctx = self.turn_context
        if ctx is None:
            self.hand_tiles_layout = []
            self.action_button_defs = []
            return

        hand_layout: List[Dict[str, Any]] = []
        for tile in sorted(ctx.hand, key=tile_sort_key):
            hand_layout.append({"tile": tile, "source": "hand", "action": None, "waits": []})
        if ctx.drawn is not None:
            hand_layout.append({"tile": ctx.drawn, "source": "drawn", "action": None, "waits": []})

        for option in ctx.discard_options:
            tile = option.tile
            source = option.source or "hand"
            for entry in hand_layout:
                if entry.get("action") is None and entry.get("tile") == tile and entry.get("source") == source:
                    entry["action"] = option.action
                    entry["waits"] = option.waits
                    break

        self.hand_tiles_layout = hand_layout

        button_defs: List[Tuple[Action, str]] = []
        if ctx.hu_action is not None:
            button_defs.append((ctx.hu_action, "HU"))
        for action in ctx.ting_actions:
            label_tile = tile_to_str(action.get("tile")) or ""
            button_defs.append((action, f"TING {label_tile}".strip()))
        for action in ctx.angangs:
            label_tile = tile_to_str(action.get("tile")) or ""
            button_defs.append((action, f"ANGANG {label_tile}".strip()))
        for action in ctx.kakans:
            label_tile = tile_to_str(action.get("tile")) or ""
            button_defs.append((action, f"KAKAN {label_tile}".strip()))

        self.action_button_defs = button_defs

    def _build_reaction_options(self, obs: Observation) -> List[ReactionOption]:
        acts: List[Action] = obs.get("legal_actions", []) or []
        options: List[ReactionOption] = []
        for action in acts:
            kind = (action.get("type") or "").upper()
            label = kind or "?"
            priority = 0
            if kind == "HU":
                label = f"HU {tile_to_str(action.get('tile')) or ''}".strip()
                priority = 4
            elif kind in {"GANG", "ANGANG", "KAKAN"}:
                label = f"{kind} {tile_to_str(action.get('tile')) or ''}".strip()
                priority = 3
            elif kind == "PONG":
                label = f"PONG {tile_to_str(action.get('tile')) or ''}".strip()
                priority = 2
            elif kind == "CHI":
                use = action.get("use") or []
                if isinstance(use, list) and len(use) == 2:
                    label = f"CHI {tile_to_str(use[0])}-{tile_to_str(use[1])} + {tile_to_str(action.get('tile'))}".strip()
                else:
                    label = f"CHI {tile_to_str(action.get('tile')) or ''}".strip()
                priority = 1
            elif kind == "PASS":
                label = "PASS"
                priority = 0
            options.append(ReactionOption(label=label, action=action, priority=priority))
        options.sort(key=lambda opt: opt.priority, reverse=True)
        return options

    def _prepare_reaction_controls(self) -> None:
        if not self.reaction_options:
            self.action_button_defs = []
            return
        self.hand_tiles_layout = []
        self.action_button_defs = [(opt.action, opt.label) for opt in self.reaction_options]

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
            detail = tile_to_str(tile) or ""
        return {"who": f"P{pid}", "type": claim_type, "detail": detail}


# Import placed at bottom to avoid circular during type checking
from app.session.ports import StepEvent  # noqa: E402  pylint: disable=wrong-import-position
