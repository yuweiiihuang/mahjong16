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

def _join_tiles(tiles: List[int]) -> Text:
    parts: List[Text] = []
    for i, t in enumerate(tiles):
        parts.append(_text_tile(t))
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

def render_public_view(env, pov_pid: int, *, did: Optional[int] = None, last_action: Optional[Dict[str, Any]] = None) -> None:
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

    # 四家 2x2 佈局
    panels = [
        _player_panel(env, 0, pov_pid, last_discard),
        _player_panel(env, 1, pov_pid, last_discard),
        _player_panel(env, 2, pov_pid, last_discard),
        _player_panel(env, 3, pov_pid, last_discard),
    ]
    # 用 Columns 先排成 2 欄，再用 Panel 外框。或你也能改成 Table grid
    left_col  = Panel(Columns([panels[0], panels[2]], expand=True), box=ROUNDED)
    right_col = Panel(Columns([panels[1], panels[3]], expand=True), box=ROUNDED)
    console.print(Columns([left_col, right_col], expand=True))

def render_reveal(env) -> None:
    """終局亮牌：所有玩家的手牌/副露/河一次列出。"""
    console.rule("[bold]reveal hands")
    rows: List[RenderableType] = []
    for pid in range(env.rules.n_players):
        pl = env.players[pid]
        hand = sorted(list(pl["hand"]), key=_tile_sort_key)
        hand_txt = Text.assemble(Text("hand: ", style="bold"), _join_tiles(hand) if hand else Text("(empty)", style="dim"))
        melds_txt = Text.assemble(Text("melds: ", style="bold"), _render_melds(pl.get("melds") or []))
        river = list(pl.get("river") or [])
        river_txt = Text.assemble(Text("river: ", style="bold"),
                                  _join_tiles(river) if river else Text("(empty)", style="dim"))
        body = Table.grid(padding=(0,1))
        body.add_row(hand_txt)
        body.add_row(melds_txt)
        body.add_row(river_txt)
        rows.append(Panel(body, title=f"P{pid}", box=ROUNDED, padding=(0,1)))
    console.print(Columns(rows, expand=True))