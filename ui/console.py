# file: ui/console.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.columns import Columns
from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED

from core.tiles import tile_to_str, tile_sort_key, is_flower
from core.hand import waits_after_discard_17, waits_for_hand_16
from core import Ruleset
from typing import Tuple

console = Console()

# ---------- 小工具：牌面排序 / 著色 ----------

def _style_for_tile(t: int) -> str:
    s = tile_to_str(t)
    if not s:
        return ""
    if is_flower(t):      # 花牌
        return "yellow"
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


def _format_amount(amount: int | float) -> Text:
    try:
        val = int(amount)
    except Exception:
        val = 0
    style = "green" if val > 0 else "red" if val < 0 else "dim"
    sign = "+" if val > 0 else ""
    return Text(f"{sign}{val}", style=style)

def _render_melds(melds: List[Dict[str, Any]], *, mask_concealed: bool = False) -> RenderableType:
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
                if mask_concealed and mtype == "ANGANG":
                    parts.append(Text("##", style="dim"))
                else:
                    parts.append(_text_tile(t))
                if i != len(tiles) - 1:
                    parts.append(Text("-", style="dim"))
        parts.append(Text("]", style="dim"))
        chunks.append(Text.assemble(*parts))
        chunks.append(Text(" "))
    if chunks:
        chunks.pop()  # 移除尾端多餘空白
    return Text.assemble(*chunks)

# ---------- 互動式選單（HumanStrategy 專用） ----------

def _after_discard(hand0: List[int], drawn0: Optional[int], tile0: int, src0: str) -> List[int]:
    """模擬丟出某張牌後，concealed 手牌的狀態（供 TING 候選剩餘計算用）。"""
    h = list(hand0)
    if (src0 or "hand").lower() == "drawn":
        return h
    if tile0 in h:
        h.remove(tile0)
    if drawn0 is not None:
        h.append(drawn0)
    return h

def _visible_count_global(tile_id: int, obs: Dict[str, Any]) -> int:
    """統計目前桌上可見的該牌數量（手牌+副露+河），用於已宣告 TING 的提示。"""
    cnt = sum(1 for t in (obs.get("hand") or []) if t == tile_id)
    for meld_list in (obs.get("melds_all") or []):
        for m in (meld_list or []):
            for x in (m.get("tiles") or []):
                if x == tile_id:
                    cnt += 1
    for rv in (obs.get("rivers") or []):
        for x in rv:
            if x == tile_id:
                cnt += 1
    return cnt

def _visible_count_after(tile_id: int, hand_after: List[int], obs: Dict[str, Any]) -> int:
    """丟掉某張之後的可見數（手牌 after + 副露 + 各家河）。"""
    cnt = sum(1 for t in hand_after if t == tile_id)
    for meld_list in (obs.get("melds_all") or []):
        for m in (meld_list or []):
            for t in (m.get("tiles") or []):
                if t == tile_id:
                    cnt += 1
    for rv in (obs.get("rivers") or []):
        for t in rv:
            if t == tile_id:
                cnt += 1
    return cnt

def prompt_turn_action(obs: Dict[str, Any]) -> Dict[str, Any]:
    """以 Rich 在命令列提示自己的回合操作（丟牌/胡/宣告聽）。"""
    acts: List[Dict[str, Any]] = obs.get("legal_actions", []) or []
    player = obs.get("player")
    hand: List[int] = list(obs.get("hand") or [])
    drawn: Optional[int] = obs.get("drawn")

    # 取得可選的行動
    hu_action = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
    discards_all: List[Dict[str, Any]] = [a for a in acts if (a.get("type") or "").upper() == "DISCARD"]

    def key_disc(a: Dict[str, Any]) -> Tuple:
        t = a.get("tile")
        src = a.get("from", "hand")
        return (0 if src == "hand" else 1, *tile_sort_key(t))

    discards_all.sort(key=key_disc)

    # 計算每個丟法對應的聽牌
    display_actions: List[Dict[str, Any]] = []
    display_tiles: List[int] = []
    waits_list: List[List[int]] = []
    for a in discards_all:
        t = a.get("tile")
        ws = waits_after_discard_17(
            hand,
            drawn,
            obs.get("melds") or [],
            t,
            a.get("from", "hand"),
            rules=Ruleset(include_flowers=False),
            exclude_exhausted=True,
        )
        display_actions.append(a)
        display_tiles.append(t)
        waits_list.append(ws)

    # 版頭
    console.print(f"\n[bold]=== Your Turn | P{player} ===[/bold]")
    sorted_hand = sorted(hand, key=tile_sort_key)
    hand_line = Text.assemble(Text("Hand: ", style="bold"), _join_tiles(sorted_hand))
    drawn_line = Text.assemble(
        Text("Drawn: ", style="bold"),
        _text_tile(drawn) if drawn is not None else Text("None", style="dim")
    )
    melds_line = Text.assemble(Text("Melds: ", style="bold"), _render_melds(obs.get("melds") or [], mask_concealed=False))
    console.print(hand_line)
    console.print(drawn_line)
    console.print(melds_line)
    # flowers below melds
    flowers = list(obs.get("flowers") or [])
    flowers.sort(key=tile_sort_key)
    flowers_line = Text.assemble(
        Text("Flowers: ", style="bold"),
        _join_tiles(flowers) if flowers else Text("(none)", style="dim"),
    )
    console.print(flowers_line)

    # 若已宣告聽，列出目前等待及剩餘數
    if bool(obs.get("declared_ting", False)):
        waits_now = waits_for_hand_16(hand, obs.get("melds") or [], Ruleset(include_flowers=False), exclude_exhausted=True)
        if waits_now:
            parts: List[Text] = []
            parts.append(Text("TING: ", style="bold"))
            for i, w in enumerate(sorted(waits_now, key=tile_sort_key)):
                vis = _visible_count_global(w, obs)
                rem = max(0, 4 - min(4, vis))
                parts.append(_text_tile(w))
                parts.append(Text(f"({rem})"))
                if i != len(waits_now) - 1:
                    parts.append(Text(" "))
            console.print(Text.assemble(*parts))

    # 收集可進入 TING 的丟法
    ting_candidates: List[Tuple[Dict[str, Any], List[int]]] = [
        (a, ws) for a, ws in zip(display_actions, waits_list) if ws
    ]

    # 若未宣告且存在候選，提供宣告 TING 流程
    if (not bool(obs.get("declared_ting", False))) and ting_candidates:
        # 嘗試找出可 ANGANG / KAKAN
        acts = obs.get("legal_actions", []) or []
        angangs = [a for a in acts if (a.get("type") or "").upper() == "ANGANG"]
        kakans = [a for a in acts if (a.get("type") or "").upper() == "KAKAN"]
        extras = []
        if angangs:
            extras.append("[A] ANGANG")
        if kakans:
            extras.append("[K] KAKAN")
        actions_hdr = ("[H] HU  " if hu_action is not None else "") + (" ".join(extras) + "  " if extras else "") + "[T] TING  [N] PASS"
        console.print(Text("ACTIONS → ", style="bold") + Text(actions_hdr))
        while True:
            raw0 = console.input("Declare TING? (T/N): ").strip().upper()
            if raw0 in ("H", "HU") and hu_action is not None:
                return dict(hu_action)
            if raw0 in ("A", "ANGANG") and angangs:
                if len(angangs) == 1:
                    return dict(angangs[0])
                # 多個暗槓候選 → 選其中之一
                console.print(Text("ANGANG options:", style="bold"))
                for i, a in enumerate(angangs):
                    console.print(Text.assemble(Text(f"  [{i}] ANGANG "), _text_tile(a.get("tile"))))
                while True:
                    sel = console.input("Pick ANGANG index: ").strip()
                    if sel.isdigit():
                        k = int(sel)
                        if 0 <= k < len(angangs):
                            return dict(angangs[k])
                    console.print(Text("索引超出範圍，請重新輸入。", style="red"))
            if raw0 in ("K", "KAKAN") and kakans:
                if len(kakans) == 1:
                    return dict(kakans[0])
                console.print(Text("KAKAN options:", style="bold"))
                for i, a in enumerate(kakans):
                    console.print(Text.assemble(Text(f"  [{i}] KAKAN "), _text_tile(a.get("tile"))))
                while True:
                    sel = console.input("Pick KAKAN index: ").strip()
                    if sel.isdigit():
                        k = int(sel)
                        if 0 <= k < len(kakans):
                            return dict(kakans[k])
                    console.print(Text("索引超出範圍，請重新輸入。", style="red"))
            if raw0 in ("T", "TING", "Y", "YES"):
                # 列出每個 TING 方案
                rows: List[Text] = []
                for i, (a, ws) in enumerate(ting_candidates):
                    t = a.get("tile")
                    src = a.get("from", "hand")
                    hand_after = _after_discard(hand, drawn, t, src)
                    cells: List[Text] = []
                    cells.append(Text(f"[{i}] DISCARD "))
                    cells.append(_text_tile(t))
                    if src == "drawn":
                        cells.append(Text("*", style="dim"))
                    cells.append(Text(" → TING: "))
                    for j, w in enumerate(sorted(ws, key=tile_sort_key)):
                        vis = _visible_count_after(w, hand_after, obs)
                        rem = max(0, 4 - min(4, vis))
                        cells.append(_text_tile(w))
                        cells.append(Text(f"({rem})"))
                        if j != len(ws) - 1:
                            cells.append(Text(" "))
                    rows.append(Text.assemble(*cells))
                console.print(Text("TING OPTIONS →", style="bold"))
                for r in rows:
                    console.print(Text("  ") + r)
                while True:
                    sel = console.input("Pick TING option index: ").strip()
                    if sel.isdigit():
                        k = int(sel)
                        if 0 <= k < len(ting_candidates):
                            a, _ = ting_candidates[k]
                            return {"type": "TING", "tile": a.get("tile"), "from": a.get("from", "hand")}
                    console.print(Text("索引超出範圍，請重新輸入。", style="red"))
            if raw0 in ("N", "NO", "P", "PASS"):
                break
            console.print(Text("請輸入 T 或 N。", style="yellow"))

    # 丟牌/胡/暗槓/加槓 選單
    if hu_action is not None:
        console.print(Text("ACTIONS → ", style="bold") + Text("[H] HU"))
    acts = obs.get("legal_actions", []) or []
    angangs = [a for a in acts if (a.get("type") or "").upper() == "ANGANG"]
    kakans = [a for a in acts if (a.get("type") or "").upper() == "KAKAN"]
    if angangs or kakans:
        extra_parts: List[Text] = []
        if angangs:
            extra_parts.append(Text(" [A] ANGANG"))
        if kakans:
            extra_parts.append(Text(" [K] KAKAN"))
        console.print(Text("KONGS → ", style="bold") + Text.assemble(*extra_parts))
    line_parts: List[Text] = []
    for i, tid in enumerate(display_tiles):
        star = (display_actions[i].get("from") == "drawn")
        cell = Text.assemble(Text(f"[{i}] "), _text_tile(tid))
        if star:
            cell.append(Text("*", style="dim"))
        line_parts.append(cell)
        if i != len(display_tiles) - 1:
            line_parts.append(Text("  "))
    console.print(Text("DISCARD → ", style="bold") + Text.assemble(*line_parts))

    while True:
        raw = console.input("Discard index or tile: ").strip().upper()
        if hu_action is not None and raw in ("H", "HU"):
            return dict(hu_action)
        if raw in ("A", "ANGANG") and angangs:
            if len(angangs) == 1:
                return dict(angangs[0])
            console.print(Text("ANGANG options:", style="bold"))
            for i, a in enumerate(angangs):
                console.print(Text.assemble(Text(f"  [{i}] ANGANG "), _text_tile(a.get("tile"))))
            sel = console.input("Pick ANGANG index: ").strip()
            if sel.isdigit() and 0 <= int(sel) < len(angangs):
                return dict(angangs[int(sel)])
            console.print(Text("索引超出範圍。", style="red"))
            continue
        if raw in ("K", "KAKAN") and kakans:
            if len(kakans) == 1:
                return dict(kakans[0])
            console.print(Text("KAKAN options:", style="bold"))
            for i, a in enumerate(kakans):
                console.print(Text.assemble(Text(f"  [{i}] KAKAN "), _text_tile(a.get("tile"))))
            sel = console.input("Pick KAKAN index: ").strip()
            if sel.isdigit() and 0 <= int(sel) < len(kakans):
                return dict(kakans[int(sel)])
            console.print(Text("索引超出範圍。", style="red"))
            continue
        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(display_actions):
                return dict(display_actions[idx])
            console.print(Text("索引超出範圍，請重新輸入。", style="red"))
            continue
        key = raw.rstrip("*")
        for a, tid in zip(display_actions, display_tiles):
            if tile_to_str(tid).upper() == key:
                return dict(a)
        console.print(Text("無效輸入，請輸入索引或合法牌面（例如 7W）。", style="yellow"))


def prompt_reaction_action(obs: Dict[str, Any]) -> Dict[str, Any]:
    """以 Rich 在命令列提示反應（HU/GANG/PONG/CHI/PASS）。"""
    acts = obs.get("legal_actions", []) or []
    player = obs.get("player")
    prio = {"HU": 0, "GANG": 1, "PONG": 2, "CHI": 3, "PASS": 9}
    ld = obs.get("last_discard") or {}
    ld_tile = ld.get("tile")

    def key_react(a: Dict[str, Any]):
        t = (a.get("type") or "").upper()
        if t == "CHI":
            use = a.get("use", [])
            s = [tile_to_str(x) for x in (use or [])]
            return (prio[t], s)
        return (prio.get(t, 99),)

    pass_action: Dict[str, Any] = next((a for a in acts if (a.get("type") or "").upper() == "PASS"), {"type": "PASS"})
    others_sorted = sorted([a for a in acts if (a.get("type") or "").upper() != "PASS"], key=key_react)

    def label_for(a: Dict[str, Any]) -> Text:
        t = (a.get("type") or "").upper()
        if t == "PASS":
            return Text("PASS")
        if t == "CHI":
            use = a.get("use", [])
            if isinstance(use, list) and len(use) == 2:
                txt = Text("CHI ")
                txt.append(_text_tile(use[0])); txt.append(Text("-")); txt.append(_text_tile(use[1]))
                if ld_tile is not None:
                    txt.append(Text("  "))
                    txt.append(_text_tile(ld_tile))
                return txt
            return Text("CHI")
        if t in ("PONG", "GANG", "HU"):
            txt = Text(f"{t} ")
            if ld_tile is not None:
                txt.append(_text_tile(ld_tile))
            return txt
        return Text("PASS")

    menu_actions: List[Dict[str, Any]] = [pass_action] + others_sorted
    labels: List[Text] = [label_for(a) for a in menu_actions]

    console.print(f"\n[bold]=== Your Reaction | P{player} → to [/bold]", _text_tile(ld_tile) if ld_tile is not None else Text("?"))
    menu_line = Text.assemble(*[Text.assemble(Text(f"[{i}] "), labels[i], Text("  ")) for i in range(len(labels))])
    console.print(menu_line)

    while True:
        raw = console.input("Select action index: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(menu_actions):
                return dict(menu_actions[idx])
            console.print(Text("索引超出範圍，請重新輸入。", style="red"))
            continue
        console.print(Text("請輸入數字索引。", style="yellow"))

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
    # 顯示門風與莊家
    try:
        sw = None
        seat_winds = getattr(env, "seat_winds", None)
        if isinstance(seat_winds, list) and 0 <= pid < len(seat_winds):
            sw = seat_winds[pid]
        if isinstance(sw, str) and sw:
            title += f" [{sw}]"
        if pid == getattr(env, "dealer_pid", -1):
            title += " (莊)"
    except Exception:
        pass
    try:
        if bool(env.players[pid].get("declared_ting", False)):
            title += " (TING)"
    except Exception:
        pass

    # 手牌/摸牌
    if is_me:
        hand = sorted(list(pl["hand"]), key=tile_sort_key)
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
    melds_line = Text.assemble(
        Text("melds: ", style="bold"),
        _render_melds(pl.get("melds") or [], mask_concealed=(not is_me))
    )

    # 花牌（公開資訊，放在副露之下）
    flowers = list(pl.get("flowers") or [])
    flowers.sort(key=tile_sort_key)
    flowers_line = Text.assemble(
        Text("flowers: ", style="bold"),
        _join_tiles(flowers) if flowers else Text("(empty)", style="dim"),
    )

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
    body.add_row(flowers_line)
    body.add_row(river_line)

    return Panel(body, title=title, box=ROUNDED, padding=(0, 1))

def _top_bar(
    env,
    *,
    did: Optional[int],
    last_action: Optional[Dict[str, Any]],
    score_state: Optional[Dict[str, Any]] = None,
) -> Panel:
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
    # 圈風 / 莊家資訊
    try:
        qf = (getattr(env, "quan_feng", None) or "?")
        dealer_pid = getattr(env, "dealer_pid", None)
        seat_winds = getattr(env, "seat_winds", None)
        dw = None
        if isinstance(dealer_pid, int) and isinstance(seat_winds, list) and 0 <= dealer_pid < len(seat_winds):
            dw = seat_winds[dealer_pid]
        qmap = {"E": "東", "S": "南", "W": "西", "N": "北"}
        qcn = qmap.get(str(qf).upper(), str(qf))
        dcn = f"P{dealer_pid}" if isinstance(dealer_pid, int) else "?"
        if isinstance(dw, str) and dw:
            dcn += f"({qmap.get(dw.upper(), dw)})"
        t.add_row(Text(f"圈風: {qcn}   莊家: {dcn}"), Text(""), Text(""))
    except Exception:
        pass
    t.add_row(
        Text(f"Turn: P{env.turn}  Phase: {env.phase}"),
        Text(f"Remaining: {n_rem}  |  DeadWall: {reserved}"),
        Text(f"D{did:03d}" if isinstance(did, int) else ""),
    )
    if score_state:
        totals = list(score_state.get("totals") or [])
        if totals:
            parts: List[Text] = []
            for pid, total in enumerate(totals):
                if pid != 0:
                    parts.append(Text("  "))
                parts.append(Text(f"P{pid}=", style="bold"))
                parts.append(Text(str(total), style="cyan"))
            t.add_row(Text.assemble(Text("points: ", style="bold"), *parts), Text(""), Text(""))
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
    score_state: Optional[Dict[str, Any]] = None,
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
    console.print(_top_bar(env, did=did, last_action=last_action, score_state=score_state))

    # 四家面板：依東南西北順序排列
    seat_winds = getattr(env, "seat_winds", None)
    dealer_pid = getattr(env, "dealer_pid", None)
    dealer_pid = getattr(env, "dealer_pid", None)
    dealer_pid = getattr(env, "dealer_pid", None)
    order_pids = []
    try:
        if isinstance(seat_winds, list):
            for w in ("E", "S", "W", "N"):
                if w in seat_winds:
                    order_pids.append(seat_winds.index(w))
    except Exception:
        order_pids = list(range(env.rules.n_players))
    if not order_pids:
        order_pids = list(range(env.rules.n_players))
    panels = [ _player_panel(env, pid, pov_pid, last_discard) for pid in order_pids ]
    
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

def render_reveal(
    env,
    breakdown: Optional[Dict[int, List[Dict[str, Any]]]] = None,
    *,
    payments: Optional[List[int]] = None,
    base_points: Optional[int] = None,
    tai_points: Optional[int] = None,
    totals: Optional[List[int]] = None,
) -> None:
    """終局亮牌（4x1 直向）：依序列出 P0→P3，每家一個獨立面板。

    Args:
      env: 遊戲環境。
      breakdown: 可選的計分明細，鍵為玩家 pid，值為該玩家的明細列表。
      payments: Optional net payouts per player（正負顯示）。
      base_points: 底分，用於標註支付公式。
      tai_points: 台分，顯示每台金額。
    """
    console.rule("[bold]reveal hands")
    if payments is not None and (base_points is not None or tai_points is not None):
        msg = "settlement"
        if base_points is not None and tai_points is not None:
            msg += f" | base {base_points} | tai {tai_points}"
        elif base_points is not None:
            msg += f" | base {base_points}"
        elif tai_points is not None:
            msg += f" | tai {tai_points}"
        console.print(Text(msg, style="dim"))
    winner: Optional[int] = getattr(env, "winner", None)
    win_src: Optional[str] = getattr(env, "win_source", None)
    win_tile: Optional[int] = getattr(env, "win_tile", None)
    turn_at_win: Optional[int] = getattr(env, "turn_at_win", None)

    # 依東南西北順序列出
    seat_winds = getattr(env, "seat_winds", None)
    dealer_pid = getattr(env, "dealer_pid", None)
    order_pids: List[int] = []
    try:
        if isinstance(seat_winds, list):
            for w in ("E", "S", "W", "N"):
                if w in seat_winds:
                    order_pids.append(seat_winds.index(w))
    except Exception:
        order_pids = list(range(env.rules.n_players))
    if not order_pids:
        order_pids = list(range(env.rules.n_players))
    for pid in order_pids:
        pl = env.players[pid]
        # hand / melds / river
        hand = sorted(list(pl["hand"]), key=tile_sort_key)
        hand_txt = Text.assemble(Text("hand: ", style="bold"),
                                 _join_tiles(hand) if hand else Text("(empty)", style="dim"))
        melds_txt = Text.assemble(Text("melds: ", style="bold"),
                                  _render_melds(pl.get("melds") or []))
        flowers = sorted(list(pl.get("flowers") or []), key=tile_sort_key)
        flowers_txt = Text.assemble(Text("flowers: ", style="bold"),
                                    _join_tiles(flowers) if flowers else Text("(empty)", style="dim"))
        river = list(pl.get("river") or [])
        river_txt = Text.assemble(Text("river: ", style="bold"),
                                  _join_tiles(river) if river else Text("(empty)", style="dim"))

        body = Table.grid(padding=(0, 1))
        body.add_row(hand_txt)
        body.add_row(melds_txt)
        body.add_row(flowers_txt)
        body.add_row(river_txt)

        # 若是贏家，附上胡牌資訊與（若提供）計分明細
        title = f"P{pid}"
        seat_tag = None
        try:
            if isinstance(seat_winds, list) and 0 <= pid < len(seat_winds):
                sw = seat_winds[pid]
                if isinstance(sw, str) and sw:
                    seat_tag = sw.upper()
        except Exception:
            seat_tag = None
        if seat_tag:
            title += f" [{seat_tag}]"
        if pid == dealer_pid:
            title += " (莊)"
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

            # 若有提供該局的 breakdown，依 winners summary 的格式顯示在贏家面板中
            if breakdown and isinstance(breakdown.get(pid), list) and breakdown.get(pid):
                body.add_row(Text("breakdown:", style="bold"))
                total = 0
                for item in breakdown.get(pid) or []:
                    label = item.get("label", item.get("key"))
                    base = int(item.get("base", 0))
                    count = int(item.get("count", 1))
                    points = int(item.get("points", base * count))
                    total += points
                    body.add_row(Text(f"  - {label}: {base} x {count} = {points}"))
                body.add_row(Text(f"  total = {total}"))

        point_parts: List[Text] = []
        if isinstance(payments, (list, tuple)) and pid < len(payments):
            point_parts.append(Text("Δ=", style="dim"))
            point_parts.append(_format_amount(payments[pid]))
        if isinstance(totals, (list, tuple)) and pid < len(totals):
            if point_parts:
                point_parts.append(Text("  "))
            point_parts.append(Text("total=", style="dim"))
            point_parts.append(Text(str(totals[pid]), style="cyan"))
        if point_parts:
            body.add_row(Text.assemble(Text("points: ", style="bold"), *point_parts))

        panel = Panel(body, title=title, box=ROUNDED, padding=(0, 1))
        console.print(panel)


def render_winners_summary(records: List[Dict[str, Any]]) -> None:
    """Render a post-session winners summary using Rich.

    Each record expects keys: hand_index, winner, win_source, ron_from, win_tile,
    hand (List[int]), melds (List[dict]), flowers (List[int]), breakdown (List[items]).
    """
    if not records:
        return
    console.rule("[bold]winners summary")
    for rec in records:
        hid = rec.get("hand_index")
        wpid = rec.get("winner")
        src = (rec.get("win_source") or "").upper()
        ron_from = rec.get("ron_from")
        wt = rec.get("win_tile")
        qf = rec.get("quan_feng")
        dealer_pid = rec.get("dealer_pid")
        dealer_wind = rec.get("dealer_wind")
        winner_wind = rec.get("winner_wind")

        # Build Quan/Dealer line
        qmap = {"E": "東", "S": "南", "W": "西", "N": "北"}
        qcn = qmap.get(str(qf).upper(), str(qf) if qf is not None else "?")
        dcn = f"P{dealer_pid}" if isinstance(dealer_pid, int) else "?"
        if isinstance(dealer_wind, str) and dealer_wind:
            dcn += f"({qmap.get(dealer_wind.upper(), dealer_wind)})"

        body = Table.grid(padding=(0, 1))
        # Draw/flow case: no winner
        payments = rec.get("payments")
        base_pts = rec.get("base_points")
        tai_pts = rec.get("tai_points")
        totals_after = rec.get("totals_after_hand")

        def add_totals_row() -> None:
            if isinstance(totals_after, (list, tuple)) and totals_after:
                parts: List[Text] = []
                for idx, amt in enumerate(totals_after):
                    if idx != 0:
                        parts.append(Text("  "))
                    parts.append(Text(f"P{idx}=", style="dim"))
                    parts.append(Text(str(amt), style="cyan"))
                body.add_row(Text.assemble(Text("totals: ", style="bold"), *parts))
        if wpid is None or str(rec.get("result")).upper() == "DRAW":
            body.add_row(Text(f"圈風: {qcn}   莊家: {dcn}"))
            body.add_row(Text("流局", style="bold"))
            if isinstance(payments, (list, tuple)):
                prefix = "payments"
                if base_pts is not None and tai_pts is not None:
                    prefix += f" (base {base_pts}, tai {tai_pts})"
                elif base_pts is not None:
                    prefix += f" (base {base_pts})"
                elif tai_pts is not None:
                    prefix += f" (tai {tai_pts})"
                parts: List[Text] = []
                for idx, amt in enumerate(payments):
                    if idx != 0:
                        parts.append(Text("  "))
                    parts.append(Text(f"P{idx}=", style="dim"))
                    parts.append(_format_amount(amt))
                body.add_row(Text.assemble(Text(f"{prefix}: ", style="bold"), *parts))
            add_totals_row()
            panel = Panel(body, title=f"Hand {hid}", box=ROUNDED, padding=(0, 1))
            console.print(panel)
            continue

        # Header line inside the panel for a normal win
        # Quan/Dealer row first
        body.add_row(Text(f"圈風: {qcn}   莊家: {dcn}"))
        prefix = f"Winner P{wpid}"
        if isinstance(winner_wind, str) and winner_wind:
            prefix += f" （{qmap.get(winner_wind.upper(), winner_wind.upper())}）"
        header = Text.assemble(Text(prefix, style="bold"), Text(" | ", style="bold"))
        if src == "RON":
            header.append("RON ")
            if isinstance(wt, int):
                header.append(_text_tile(wt, highlight=True))
            if isinstance(ron_from, int):
                header.append(Text(f" from P{ron_from}", style="italic"))
        elif src == "TSUMO":
            header.append("TSUMO ")
            if isinstance(wt, int):
                header.append(_text_tile(wt, highlight=True))
        else:
            if src:
                header.append(Text(src))
            if isinstance(wt, int):
                header.append(Text(" "))
                header.append(_text_tile(wt, highlight=True))
        body.add_row(header)

        # Hand line
        htiles = sorted(list(rec.get("hand") or []), key=tile_sort_key)
        body.add_row(Text.assemble(Text("hand: ", style="bold"),
                                   _join_tiles(htiles) if htiles else Text("(empty)", style="dim")))

        # Melds line
        melds = rec.get("melds") or []
        if melds:
            body.add_row(Text.assemble(Text("melds: ", style="bold"), _render_melds(melds)))
        else:
            body.add_row(Text.assemble(Text("melds: ", style="bold"), Text("(none)", style="dim")))

        # Flowers line
        flowers = sorted(list(rec.get("flowers") or []), key=tile_sort_key)
        body.add_row(Text.assemble(Text("flowers: ", style="bold"),
                                   _join_tiles(flowers) if flowers else Text("(none)", style="dim")))

        # Breakdown
        items = rec.get("breakdown") or []
        if items:
            body.add_row(Text("breakdown:", style="bold"))
            total = 0
            for item in items:
                label = item.get("label", item.get("key"))
                base = int(item.get("base", 0))
                count = int(item.get("count", 1))
                points = int(item.get("points", base * count))
                total += points
                body.add_row(Text(f"  - {label}: {base} x {count} = {points}"))
            body.add_row(Text(f"  total = {total}"))
        else:
            body.add_row(Text.assemble(Text("breakdown: ", style="bold"), Text("(none)", style="dim")))

        if isinstance(payments, (list, tuple)):
            prefix = "payments"
            if base_pts is not None and tai_pts is not None:
                prefix += f" (base {base_pts}, tai {tai_pts})"
            elif base_pts is not None:
                prefix += f" (base {base_pts})"
            elif tai_pts is not None:
                prefix += f" (tai {tai_pts})"
            parts: List[Text] = []
            for idx, amt in enumerate(payments):
                if idx != 0:
                    parts.append(Text("  "))
                parts.append(Text(f"P{idx}=", style="dim"))
                parts.append(_format_amount(amt))
            body.add_row(Text.assemble(Text(f"{prefix}: ", style="bold"), *parts))

        add_totals_row()

        panel = Panel(body, title=f"Hand {hid}", box=ROUNDED, padding=(0, 1))
        console.print(panel)
