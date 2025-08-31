# file: ui/console.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.columns import Columns
from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED

# 依你專案的 tiles 工具取字串
from core.tiles import tile_to_str

console = Console()

# ---------- 小工具：牌面排序 / 著色 ----------

def _suit_of_id(t: int) -> int:
    # 0:萬, 1:筒, 2:條, 3:字
    if 0 <= t <= 8: return 0
    if 9 <= t <= 17: return 1
    if 18 <= t <= 26: return 2
    return 3

def _rank_of_id(t: int) -> int:
    # 萬/筒/條回傳 1..9；字牌回 0
    if 0 <= t <= 8: return t - 0 + 1
    if 9 <= t <= 17: return t - 9 + 1
    if 18 <= t <= 26: return t - 18 + 1
    return 0

_HONOR_ORDER = {"E": 0, "S": 1, "W": 2, "N": 3, "C": 4, "F": 5, "P": 6}
def _honor_index_of_id(t: int) -> int:
    s = tile_to_str(t)
    k = s[0] if s else "?"
    return _HONOR_ORDER.get(k, 99)

def _tile_sort_key(t: int):
    s = _suit_of_id(t)
    return (s, _rank_of_id(t), tile_to_str(t)) if s < 3 else (s, _honor_index_of_id(t), tile_to_str(t))

def _style_for_tile(t: int) -> str:
    s = tile_to_str(t)
    if not s:
        return ""
    if len(s) == 1:       # 字牌
        return "magenta"
    suit = s[-1]          # W/D/B
    return {"W": "red", "D": "blue", "B": "green"}.get(suit, "")

def _text_tile(t: int, *, highlight: bool = False, dim: bool = False) -> Text:
    s = tile_to_str(t)
    style = _style_for_tile(t)
    txt = Text(s, style=style)
    if dim:
        txt.stylize("dim")
    if highlight:
        txt.stylize("reverse bold")
    return txt

def _join_tiles(tiles: List[int], *, highlight_tile: Optional[int] = None) -> Text:
    parts: List[Text] = []
    highlighted = False
    for i, t in enumerate(tiles):
        hl = (not highlighted) and (highlight_tile is not None) and (t == highlight_tile)
        parts.append(_text_tile(t, highlight=hl))
        if hl:
            highlighted = True
        if i != len(tiles) - 1:
            parts.append(Text(" "))
    return Text.assemble(*parts)

def _render_melds(melds: List[Dict[str, Any]]) -> RenderableType:
    if not melds:
        return Text("[]", style="dim")
    # 例如：[PONG 3W-3W-3W] [CHI 6D-7D-8D]
    chunks: List[Text] = []
    for m in melds:
        mtype = (m.get("type") or "").upper()
        tiles = list(m.get("tiles") or [])
        tiles.sort()
        parts: List[Text] = []
        parts.append(Text("[", style="dim"))
        parts.append(Text(mtype or "MELD", style="bold"))
        if tiles:
            parts.append(Text(" ", style="dim"))
            for i, t in enumerate(tiles):
                parts.append(_text_tile(t))
                if i != len(tiles) - 1:
                    parts.append(Text("-", style="dim"))
        parts.append(Text("]", style="dim"))
        chunks.append(Text.assemble(*parts))
        chunks.append(Text(" "))
    if chunks:
        chunks.pop()  # 移除尾端多餘空白
    return Text.assemble(*chunks)

# ---------- 公開視角渲染 ----------

def _player_panel(env, pid: int, pov_pid: int, last_discard: Optional[Dict[str, Any]]) -> Panel:
    """
    - 自己(pov)：顯示完整手牌（排序）、drawn、melds、river。
    - 他家：手牌以「(N tiles)」表示；drawn=Hidden；顯示副露＆棄牌河。
    - 若 last_discard 在該家的河且仍是最後一張，反白顯示。
    """
    pl = env.players[pid]
    is_me = (pid == pov_pid)

    # 標題（玩家/剩餘張數/身份）
    title = f"P{pid} {'(You)' if is_me else ''}"
    try:
        if bool(env.players[pid].get("declared_ting", False)):
            title += " (TING)"
    except Exception:
        pass

    # 手牌/摸牌
    if is_me:
        hand = sorted(list(pl["hand"]), key=_tile_sort_key)
        drawn = pl.get("drawn")
        hand_line = Text.assemble(Text("hand: ", style="bold"), _join_tiles(hand))
        drawn_line = Text.assemble(Text("drawn: ", style="bold"),
                                   _text_tile(drawn) if drawn is not None else Text("None", style="dim"))
    else:
        hand_line = Text.assemble(
            Text("hand: ", style="bold"),
            Text(f"({len(pl['hand'])} tiles)", style="dim"),
        )
        drawn_line = Text.assemble(Text("drawn: ", style="bold"), Text("Hidden", style="dim"))

    # 副露
    melds_line = Text.assemble(Text("melds: ", style="bold"), _render_melds(pl.get("melds") or []))

    # 河牌（若最後一張等於 last_discard 且此家就是丟牌者，反白）
    river = list(pl.get("river") or [])
    river_line = Text("river: ", style="bold")
    if river:
        # 決定是否反白最後一張
        highlight_idx = None
        if last_discard and last_discard.get("pid") == pid and river[-1] == last_discard.get("tile"):
            highlight_idx = len(river) - 1
        for i, t in enumerate(river):
            river_line.append(_text_tile(t, highlight=(i == highlight_idx)))
            if i != len(river) - 1:
                river_line.append(Text(" "))
    else:
        river_line.append(Text("(empty)", style="dim"))

    body = Table.grid(padding=(0, 1))
    body.add_row(hand_line)
    body.add_row(drawn_line)
    body.add_row(melds_line)
    body.add_row(river_line)

    return Panel(body, title=title, box=ROUNDED, padding=(0, 1))

def _top_bar(env, *, did: Optional[int], last_action: Optional[Dict[str, Any]]) -> Panel:
    """Build the top status panel with turn, remaining tiles, deadwall, and last action."""
    n_rem = len(env.wall)
    # 牆尾留置
    mode = getattr(env.rules, "dead_wall_mode", "fixed")
    base = getattr(env.rules, "dead_wall_base", 16)
    if mode == "gang_plus_one":
        reserved = base + getattr(env, "n_gang", 0)
    else:
        reserved = base

    # 最後動作顯示（可選）
    if last_action:
        la = last_action
        la_txt = Text.assemble(
            Text(f"{la.get('who','?')} "),
            Text(la.get("type",""), style="bold"),
            Text(" "),
            Text(la.get("detail",""), style="italic"),
        )
    else:
        la_txt = Text("(no action)", style="dim")

    t = Table.grid(expand=True)
    t.add_column(justify="left"); t.add_column(justify="center"); t.add_column(justify="right")
    t.add_row(
        Text(f"Turn: P{env.turn}  Phase: {env.phase}"),
        Text(f"Remaining: {n_rem}  |  DeadWall: {reserved}"),
        Text(f"D{did:03d}" if isinstance(did, int) else ""),
    )
    t.add_row(la_txt, Text(""), Text(""))
    return Panel(t, title="Status", box=ROUNDED)

def _win_marker_line(env, pid: int) -> Optional[Text]:
    """為攤牌面板建立胡牌標示行：TSUMO/RON 與最後一張牌；榮和會附上放槍者。"""
    winner = getattr(env, "winner", None)
    if winner is None or pid != winner:
        return None
    win_src  = (getattr(env, "win_source", None) or "").upper()
    win_tile = getattr(env, "win_tile", None)
    from_pid = getattr(env, "turn_at_win", None) if win_src == "RON" else None
    if win_tile is None:
        return None
    line = Text.assemble(Text("win: ", style="bold"))
    if win_src == "TSUMO":
        line.append("TSUMO ")
        line.append(_text_tile(win_tile, highlight=True))
    elif win_src == "RON":
        line.append("RON ")
        line.append(_text_tile(win_tile, highlight=True))
        if from_pid is not None:
            line.append(Text(f" from P{from_pid}", style="italic"))
    else:
        # 不明來源時也至少標出牌
        line.append(_text_tile(win_tile, highlight=True))
    return line


def render_public_view(
    env,
    pov_pid: int,
    *,
    did: Optional[int] = None,
    last_action: Optional[Dict[str, Any]] = None,
    layout: str = "1x4",   # 預設直向 1 欄 4 列；option: "2x2"
) -> None:
    """
    以「公開視角」渲染全桌面：
      - 自己：全資訊（手牌/摸牌/副露/河）
      - 他家：只顯示 副露＋河（手牌只顯示張數，摸牌 Hidden）
      - 反白：目前桌面上的最後棄牌（若仍在河）
    """
    console.clear()
    last_discard = getattr(env, "last_discard", None)

    # 上方狀態列
    console.print(_top_bar(env, did=did, last_action=last_action))

    # 四家面板
    panels = [
        _player_panel(env, 0, pov_pid, last_discard),
        _player_panel(env, 1, pov_pid, last_discard),
        _player_panel(env, 2, pov_pid, last_discard),
        _player_panel(env, 3, pov_pid, last_discard),
    ]
    
    # 用 Columns 先排成 2 欄，再用 Panel 外框。
    if layout == "2x2":
        # 舊版 2x2 佈局
        left_col  = Panel(Columns([panels[0], panels[2]], expand=True), box=ROUNDED)
        right_col = Panel(Columns([panels[1], panels[3]], expand=True), box=ROUNDED)
        console.print(Columns([left_col, right_col], expand=True))
    else:
        # 新版 1x4 直向排列
        for pan in panels:
            console.print(pan)

def render_reveal(env) -> None:
    """終局亮牌（4x1 直向）：依序列出 P0→P3，每家一個獨立面板。"""
    console.rule("[bold]reveal hands")
    winner: Optional[int] = getattr(env, "winner", None)
    win_src: Optional[str] = getattr(env, "win_source", None)
    win_tile: Optional[int] = getattr(env, "win_tile", None)
    turn_at_win: Optional[int] = getattr(env, "turn_at_win", None)

    for pid in range(env.rules.n_players):
        pl = env.players[pid]
        # hand / melds / river
        hand = sorted(list(pl["hand"]), key=_tile_sort_key)
        hand_txt = Text.assemble(Text("hand: ", style="bold"),
                                 _join_tiles(hand) if hand else Text("(empty)", style="dim"))
        melds_txt = Text.assemble(Text("melds: ", style="bold"),
                                  _render_melds(pl.get("melds") or []))
        river = list(pl.get("river") or [])
        river_txt = Text.assemble(Text("river: ", style="bold"),
                                  _join_tiles(river) if river else Text("(empty)", style="dim"))

        body = Table.grid(padding=(0, 1))
        body.add_row(hand_txt)
        body.add_row(melds_txt)
        body.add_row(river_txt)

        # 若是贏家，附上胡牌資訊
        title = f"P{pid}"
        if winner == pid:
            title += " (WINNER)"
            # 顯示 TSUMO/RON 與胡的那張牌；若為榮和可加註放槍者
            wt = tile_to_str(win_tile) if isinstance(win_tile, int) else "?"
            src = (win_src or "").upper()
            win_line = Text.assemble(Text("win: ", style="bold"),
                                     Text(src if src else "WIN"),
                                     Text(" "),
                                     Text(wt, style=_style_for_tile(win_tile) if isinstance(win_tile, int) else ""))
            # 榮和可附註放槍者（若拿得到）
            if src == "RON" and isinstance(turn_at_win, int):
                win_line.append(Text(f" from P{turn_at_win}", style="dim"))
            body.add_row(win_line)

        panel = Panel(body, title=title, box=ROUNDED, padding=(0, 1))
        console.print(panel)
