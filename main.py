# main.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str, hand_to_str

# 反應優先權：HU > GANG > PONG > CHI
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}

def fmt_tile(t: int | None) -> str:
    return "None" if t is None else tile_to_str(t)

def _suit_of(t: int) -> int:
    """0:萬, 1:筒, 2:條, 3:字（風/箭）；依專案慣例 0..8/9..17/18..26/其他。"""
    if 0 <= t <= 8: return 0
    if 9 <= t <= 17: return 1
    if 18 <= t <= 26: return 2
    return 3

def _rank_of(t: int) -> int:
    """萬/筒/條回傳 1..9；字牌回 0（字牌僅用來放在三花色後面，不再細分）。"""
    if 0 <= t <= 8: return t - 0 + 1
    if 9 <= t <= 17: return t - 9 + 1
    if 18 <= t <= 26: return t - 18 + 1
    return 0

_HONOR_ORDER = {"E": 0, "S": 1, "W": 2, "N": 3, "C": 4, "F": 5, "P": 6}
def _honor_index(t: int) -> int:
    """字牌排序索引：東(E)→南(S)→西(W)→北(N)→中(C)→發(F)→白(P)"""
    label = tile_to_str(t)
    key = label[0] if label else "?"
    return _HONOR_ORDER.get(key, 99)

def _tile_sort_key(t: int):
    """通用顯示用排序鍵：萬→筒→條→字；字牌依 _honor_index。"""
    s = _suit_of(t)
    return (s, _rank_of(t), tile_to_str(t)) if s < 3 else (s, _honor_index(t), tile_to_str(t))

def _sort_tiles_for_display(tiles: List[int]) -> List[int]:
    """依牌型排序用於顯示：萬→筒→條→字；同花色以點數遞增；字牌依 E,S,W,N,C,F,P。"""
    return sorted(tiles, key=_tile_sort_key)

def render_melds(melds: List[Dict[str, Any]]) -> str:
    """將吃/碰/槓的組合轉為可讀字串；每組顯示所有牌。"""
    parts = []
    for m in melds or []:
        mtype = (m.get("type") or "").upper()
        tiles = list(m.get("tiles", []))
        tiles.sort()
        tiles_str = "-".join(tile_to_str(t) for t in tiles)
        if mtype in ("CHI", "PONG", "GANG"):
            parts.append(f"[{mtype} {tiles_str}]")
        else:
            parts.append(f"[{mtype or 'MELD'} {tiles_str}]")
    return " ".join(parts) if parts else "[]"

def choose_action(obs: Dict[str, Any]) -> Dict[str, Any]:
    """示範決策：
    - REACTION：執行最高優先的非 PASS
    - TURN：可 HU（自摸）則 HU；否則丟 drawn；再不然丟第一個可丟
    """
    acts = obs.get("legal_actions", [])
    phase = obs.get("phase")

    if phase == "REACTION":
        cand = [a for a in acts if a.get("type") != "PASS"]
        if not cand:
            return {"type": "PASS"}
        cand.sort(key=lambda a: PRIORITY.get(a.get("type", ""), -1), reverse=True)
        return cand[0]

    # TURN 期
    hu = next((a for a in acts if a.get("type") == "HU"), None)
    if hu is not None:
        return hu

    drawn_discard = next(
        (a for a in acts if a.get("type") == "DISCARD" and a.get("from") == "drawn"),
        None
    )
    if drawn_discard is not None:
        return drawn_discard

    for a in acts:
        if a.get("type") == "DISCARD":
            return a

    return {"type": "PASS"}  # 理論上不會到這裡

def _fmt_action_for_human(idx: int, act: Dict[str, Any], obs: Dict[str, Any]) -> str:
    """將 legal action 轉為可讀字串供人類選擇。"""
    t = (act.get("type") or "").upper()
    if t == "DISCARD":
        src = act.get("from", "hand")
        tile = act.get("tile")
        return f"[{idx}] DISCARD {tile_to_str(tile)} (from={src})"
    if t == "PASS":
        return f"[{idx}] PASS"
    if t in ("PONG", "GANG", "HU"):
        ld = obs.get("last_discard") or {}
        tt = ld.get("tile")
        base = f"[{idx}] {t}"
        return f"{base} {fmt_tile(tt)}" if tt is not None else base
    if t == "CHI":
        use = act.get("use", [])
        ld = obs.get("last_discard") or {}
        tt = ld.get("tile")
        if isinstance(use, list) and len(use) == 2:
            return f"[{idx}] CHI ({tile_to_str(use[0])},{tile_to_str(use[1])})  {fmt_tile(tt)}"
        return f"[{idx}] CHI"
    return f"[{idx}] {t}"

def human_choose_action(obs: Dict[str, Any]) -> Dict[str, Any]:
    """
    互動式選擇行動：
    - TURN：橫向列出可丟牌，按牌型排序（萬→筒→條→字，點數遞增）；drawn 一律置於最後並以 * 標示。
            可輸入「索引」或「牌面字串」(例如 7W)。
    - REACTION：橫向列出選項，依優先度排序 HU>GANG>PONG>CHI>PASS；輸入索引。
    - 僅允許在當前 legal_actions 範圍內選擇。
    """
    acts = obs.get("legal_actions", []) or []
    player = obs.get("player")
    phase = obs.get("phase")

    # 若沒有可選動作（理論上不會），預設 PASS
    if not acts:
        print("\n[auto] No legal actions → PASS")
        return {"type": "PASS"}

    if phase == "TURN":
        # --- 橫向列出可丟的牌：按牌型排序；drawn 置後並加 * ---
        hand: List[int] = list(obs.get("hand") or [])
        drawn: Optional[int] = obs.get("drawn")
        # 收集所有合法丟牌動作
        discards_all: List[Dict[str, Any]] = [a for a in acts if a.get("type")=="DISCARD"]
        # 以（來源、花色、點數、牌面字串）排序；來源 hand=0、drawn=1 以確保 drawn 在最後
        def key_disc(a: Dict[str, Any]) -> Tuple:
            t = a.get("tile")
            src = a.get("from","hand")
            return (0 if src=="hand" else 1, *_tile_sort_key(t))

        discards_all.sort(key=key_disc)
        # 產生顯示與對應動作
        display_actions: List[Dict[str, Any]] = []
        display_labels: List[str] = []
        for a in discards_all:
            t = a.get("tile")
            lbl = tile_to_str(t)
            if a.get("from") == "drawn":
                lbl += "*"
            display_actions.append(a)
            display_labels.append(lbl)

        # 輸出橫向選單
        print(f"\n=== Your Turn | P{player} ===")
        # 顯示當前手牌與 drawn（供對照）
        hand_s = " ".join(tile_to_str(t) for t in hand)
        print(f"Hand: {hand_s}   Drawn: {fmt_tile(drawn)}")
        # 顯示已公開的吃／碰／槓
        print(f"Melds: {render_melds(obs.get('melds') or [])}")

        line = "  ".join(f"[{i}] {lbl}" for i, lbl in enumerate(display_labels))
        print(f"DISCARD → {line}")

        # 讀取輸入：索引或牌面字串
        while True:
            raw = input("Discard index or tile: ").strip().upper()
            # 先嘗試索引
            if raw.isdigit():
                idx = int(raw)
                if 0 <= idx < len(display_actions):
                    chosen = display_actions[idx]
                    return {k: v for k, v in chosen.items()}
                print("索引超出範圍，請重新輸入。")
                continue
            # 再嘗試以牌面字串比對（允許含尾端 *）
            key = raw.rstrip("*")
            # 找到第一個相同牌面的選項
            pick = None
            for a, lbl in zip(display_actions, display_labels):
                if lbl.rstrip("*").upper() == key:
                    pick = a
                    break
            if pick is not None:
                return {k: v for k, v in pick.items()}
            print("無效輸入，請輸入索引或合法牌面（例如 7W）。")

    else:
        # --- REACTION：橫向列出，依優先度排序（HU>GANG>PONG>CHI>PASS），索引選擇 ---
        prio = {"HU":0, "GANG":1, "PONG":2, "CHI":3, "PASS":9}
        ld = obs.get("last_discard") or {}
        ld_tile = ld.get("tile")
        def key_react(a: Dict[str, Any]):
            t = (a.get("type") or "").upper()
            if t == "CHI":
                use = a.get("use", [])
                # 以 use 的兩張字面排序，確保橫向穩定
                s = []
                if isinstance(use, list):
                    for x in use:
                        s.append(tile_to_str(x))
                return (prio[t], s)
            return (prio.get(t, 9), tile_to_str(ld_tile) if ld_tile is not None else "")
        reacts = list(acts)
        reacts.sort(key=key_react)
        # 構造橫向顯示文字
        labels: List[str] = []
        for a in reacts:
            t = (a.get("type") or "").upper()
            if t in ("HU","PONG","GANG"):
                labels.append(t if ld_tile is None else f"{t} {tile_to_str(ld_tile)}")
            elif t == "CHI":
                use = a.get("use", [])
                if isinstance(use, list) and len(use) == 2:
                    labels.append(f"CHI {tile_to_str(use[0])}-{tile_to_str(use[1])}  {tile_to_str(ld_tile) if ld_tile is not None else ''}".strip())
                else:
                    labels.append("CHI")
            else:
                labels.append("PASS")
        print(f"\n=== Your Reaction | P{player} → to {fmt_tile(ld_tile)} ===")
        line = "  ".join(f"[{i}] {lbl}" for i, lbl in enumerate(labels))
        print(line)
        # 索引輸入
        while True:
            raw = input("Select action index: ").strip()
            if raw.isdigit():
                idx = int(raw)
                if 0 <= idx < len(reacts):
                    chosen = reacts[idx]
                    return {k: v for k, v in chosen.items()}
                print("索引超出範圍，請重新輸入。")
                continue
            print("請輸入數字索引。")

def print_action_line(act: Dict[str, Any], obs: Dict[str, Any]) -> None:
    """輸出非 PASS 的動作行（HU/GANG/PONG/CHI）。不處理 DISCARD。"""
    t = (act.get("type") or "").upper()
    pid = obs.get("player")
    if t == "HU":
        src = act.get("source", "unknown")
        if obs.get("phase") == "REACTION":
            ld = obs.get("last_discard") or {}
            tt = ld.get("tile")
            print(f"P{pid} HU (source={src}, tile={fmt_tile(tt)})")
        else:
            print(f"P{pid} HU (source={src}, tile={fmt_tile(obs.get('drawn'))})")
    elif t in ("GANG", "PONG"):
        ld = obs.get("last_discard") or {}
        tt = ld.get("tile")
        print(f"P{pid} {t} {fmt_tile(tt)}")
    elif t == "CHI":
        use = act.get("use", [])
        ld = obs.get("last_discard") or {}
        tt = ld.get("tile")
        if isinstance(use, list) and len(use) == 2:
            print(f"P{pid} CHI ({tile_to_str(use[0])},{tile_to_str(use[1])}) + {fmt_tile(tt)}")
        else:
            print(f"P{pid} CHI {fmt_tile(tt)}")

def print_discard_line(did: int, pid: int, tile: int, pre_drawn: int | None, env: Mahjong16Env) -> None:
    """輸出丟牌列（含步數 D###），並附上該玩家的 hand/melds，drawn 使用 step 前快取。"""
    me = env.players[pid]
    sorted_hand = _sort_tiles_for_display(me["hand"])
    hand_s = " ".join(tile_to_str(t) for t in sorted_hand)

    melds_s = render_melds(me["melds"])
    print(f"[D{did:03d}]P{pid} DISCARD {tile_to_str(tile)} | hand={hand_s} | melds={melds_s} | drawn={fmt_tile(pre_drawn)}")

def print_table_snapshot(env: Mahjong16Env, discarder_pid: int, pre_drawn: int | None) -> None:
    """在丟牌後輸出四家快照；丟牌者那行帶 step 前的 drawn，其餘不顯示 drawn。"""
    for p in range(env.rules.n_players):
        pl = env.players[p]
        sorted_hand = _sort_tiles_for_display(pl["hand"])
        hand_s = " ".join(tile_to_str(t) for t in sorted_hand)

        melds_s = render_melds(pl["melds"])
        if p == discarder_pid:
            print(f"      P{p} | hand={hand_s} | melds={melds_s} | drawn={fmt_tile(pre_drawn)}")
        else:
            print(f"      P{p} | hand={hand_s} | melds={melds_s}")

def run_demo(seed=None, human_pid: Optional[int] = 0):
    rules = Ruleset(
        include_flowers=True,
        dead_wall_mode="fixed",   # 或 "kong_plus_one"
        dead_wall_base=16
    )
    env = Mahjong16Env(rules, seed=seed)

    print("=== mahjong16 demo（精簡輸出：隱藏 PASS；丟牌才遞增步數；每次丟牌後列四家快照） ===")

    obs = env.reset()
    discard_id = 0  # 僅在丟牌進河時遞增

    while True:
        act = choose_action(obs)
        # 若設定為人類操控，且輪到該玩家，改由互動式選擇
        if human_pid is not None and obs.get("player") == human_pid:
            act = human_choose_action(obs)
        else:
            act = choose_action(obs)

        # 非 PASS 動作行（DISCARD 另行處理）
        atype = (act.get("type") or "").upper()
        if atype in ("HU", "GANG", "PONG", "CHI"):
            print_action_line(act, obs)

        # 在 step 前快取必要資訊（避免 drawn 被環境清空）
        pre_pid = obs.get("player")
        pre_phase = obs.get("phase")
        pre_drawn = obs.get("drawn")  # 這個就是要印的 drawn
        pre_tile = act.get("tile") if atype == "DISCARD" else None

        # 前進環境
        obs, rew, done, info = env.step(act)

        # 若是丟牌：印丟牌列 + 快照（使用 step 前的 pre_drawn）
        if atype == "DISCARD" and pre_tile is not None:
            discard_id += 1
            print_discard_line(discard_id, pre_pid, pre_tile, pre_drawn, env)
            print_table_snapshot(env, pre_pid, pre_drawn)

        if done:
            print("=== round end ===")
            print(f"rewards: {rew}")
            break

        # 避免極端情況無限循環
        if discard_id > 2000:
            print("=== stop (safety break) ===")
            break

if __name__ == "__main__":
        # human_pid=None 可切回全自動；預設 0 由你手動操控 P0
        run_demo(human_pid=2)
