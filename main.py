# file: main.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple, Protocol
import re
from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str

# 反應優先權：HU > GANG > PONG > CHI
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}

# ========= 共用格式/排序 =========

ANSI_RESET = "\033[0m"
ANSI_RED   = "\033[31m"  # 萬
ANSI_BLUE  = "\033[34m"  # 筒
ANSI_GREEN = "\033[32m"  # 條
ANSI_MAG   = "\033[35m"  # 字（風/箭）

def _colorize_label(s: str) -> str:
    """上色單一牌面字串（允許尾端 * 標記）。"""
    if not s:
        return s
    # 若以 * 結尾（drawn），先去星上色再補回星號（不上色）
    if s.endswith("*"):
        core = s[:-1]
        return f"{_colorize_label(core)}*"
    ch0 = s[0]
    # 數牌：尾碼判斷花色
    if ch0.isdigit() and len(s) >= 2:
        suit = s[-1]
        if suit == "W":
            return f"{ANSI_RED}{s}{ANSI_RESET}"
        if suit == "D":
            return f"{ANSI_BLUE}{s}{ANSI_RESET}"
        if suit == "B":
            return f"{ANSI_GREEN}{s}{ANSI_RESET}"
    # 字牌：E,S,W,N,C,F,P（單字母）
    if ch0 in "ESWNCFP" and len(s) == 1:
        return f"{ANSI_MAG}{s}{ANSI_RESET}"
    return s

def _colorize_tile(t: int) -> str:
    return _colorize_label(tile_to_str(t))

def fmt_tile(t: int | None) -> str:
    return "None" if t is None else _colorize_tile(t)

# 將一段文字中的所有牌面（1W..9W/1D..9D/1B..9B/E/S/W/N/C/F/P）批次上色
_TILE_TOKEN_RE = re.compile(r'(?<!\w)(?:[1-9][WDB]|[ESWNCFP])(?!\w)')
def _colorize_text_tiles(text: str) -> str:
    def _repl(m: re.Match) -> str:
        return _colorize_label(m.group(0))
    return _TILE_TOKEN_RE.sub(_repl, text)

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
    """字牌排序索引：東(E)→南(S)→西(W)→北(N)→中(C)→發(F)→白(P)。"""
    label = tile_to_str(t)
    key = label[0] if label else "?"
    return _HONOR_ORDER.get(key, 99)

def _tile_sort_key(t: int):
    """顯示用排序鍵：萬→筒→條→字；字牌依 _honor_index。"""
    s = _suit_of(t)
    return (s, _rank_of(t), tile_to_str(t)) if s < 3 else (s, _honor_index(t), tile_to_str(t))

def _sort_tiles_for_display(tiles: List[int]) -> List[int]:
    """顯示時的排序：萬→筒→條→字；同花色點數遞增；字牌依 E,S,W,N,C,F,P。"""
    return sorted(tiles, key=_tile_sort_key)

def render_melds(melds: List[Dict[str, Any]]) -> str:
    """將吃/碰/槓轉為人類可讀字串；每組顯示所有牌。"""
    parts = []
    for m in melds or []:
        mtype = (m.get("type") or "").upper()
        tiles = list(m.get("tiles", []))
        tiles.sort()
        tiles_str = "-".join(_colorize_tile(t) for t in tiles)
        if mtype in ("CHI", "PONG", "GANG"):
            parts.append(f"[{mtype} {tiles_str}]")
        else:
            parts.append(f"[{mtype or 'MELD'} {tiles_str}]")
    return " ".join(parts) if parts else "[]"

# ========= Formatter（統一輸出） =========

class Formatter:
    @staticmethod
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
                print(f"P{pid} CHI ({_colorize_tile(use[0])},{_colorize_tile(use[1])}) + {fmt_tile(tt)}")
            else:
                print(f"P{pid} CHI {fmt_tile(tt)}")

    @staticmethod
    def print_discard_line(did: int, pid: int, tile: int, pre_drawn: int | None, env: Mahjong16Env) -> None:
        """輸出丟牌列（含步數 D###），並附上該玩家的 hand/melds；drawn 使用 step 前快取。"""
        me = env.players[pid]
        sorted_hand = _sort_tiles_for_display(me["hand"])
        hand_s = " ".join(_colorize_tile(t) for t in sorted_hand)
        melds_s = render_melds(me["melds"])
        print(f"[D{did:03d}]P{pid} DISCARD {_colorize_tile(tile)} | hand={hand_s} | melds={melds_s} | drawn={fmt_tile(pre_drawn)}")

    @staticmethod
    def print_table_snapshot(env: Mahjong16Env, discarder_pid: int, pre_drawn: int | None) -> None:
        """在丟牌後輸出四家快照；丟牌者那行帶 step 前的 drawn，其餘不顯示 drawn；手牌排序顯示。"""
        for p in range(env.rules.n_players):
            pl = env.players[p]
            sorted_hand = _sort_tiles_for_display(pl["hand"])
            hand_s = " ".join(_colorize_tile(t) for t in sorted_hand)
            melds_s = render_melds(pl["melds"])
            if p == discarder_pid:
                print(f"      P{p} | hand={hand_s} | melds={melds_s} | drawn={fmt_tile(pre_drawn)}")
            else:
                print(f"      P{p} | hand={hand_s} | melds={melds_s}")

# ========= Strategy 介面與實作 =========

class Strategy(Protocol):
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]: ...

class AutoStrategy:
    """維持原本自動策略邏輯。"""
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        acts = obs.get("legal_actions", []) or []
        phase = obs.get("phase")

        if phase == "REACTION":
            cand = [a for a in acts if (a.get("type") or "").upper() != "PASS"]
            if not cand:
                return {"type": "PASS"}
            cand.sort(key=lambda a: PRIORITY.get((a.get("type") or "").upper(), -1), reverse=True)
            return cand[0]

        # TURN 期
        hu = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
        if hu is not None:
            return hu

        drawn_discard = next(
            (a for a in acts if (a.get("type") or "").upper() == "DISCARD" and a.get("from") == "drawn"),
            None
        )
        if drawn_discard is not None:
            return drawn_discard

        for a in acts:
            if (a.get("type") or "").upper() == "DISCARD":
                return a

        return {"type": "PASS"}  # 理論上不會到這裡

class HumanStrategy:
    """維持原本互動式輸入與橫式菜單格式。"""
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        acts = obs.get("legal_actions", []) or []
        player = obs.get("player")
        phase = obs.get("phase")

        if not acts:
            print("\n[auto] No legal actions → PASS")
            return {"type": "PASS"}

        if phase == "TURN":
            hand: List[int] = list(obs.get("hand") or [])
            drawn: Optional[int] = obs.get("drawn")
            # 可自摸？
            hu_action = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)

            # 收集並排序所有可丟
            discards_all: List[Dict[str, Any]] = [a for a in acts if (a.get("type") or "").upper() == "DISCARD"]

            def key_disc(a: Dict[str, Any]) -> Tuple:
                t = a.get("tile")
                src = a.get("from", "hand")
                return (0 if src == "hand" else 1, *_tile_sort_key(t))

            discards_all.sort(key=key_disc)

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
            hand_s = " ".join(tile_to_str(t) for t in hand)
            print(f"Hand: {' '.join(_colorize_tile(t) for t in hand)}   Drawn: {fmt_tile(drawn)}")
            print(f"Melds: {render_melds(obs.get('melds') or [])}")

            if hu_action is not None:
                print("ACTIONS → [H] HU")
            # 列印時加色，但比對輸入仍用未上色的 display_labels
            line = "  ".join(f"[{i}] {_colorize_label(lbl)}" for i, lbl in enumerate(display_labels))
            print(f"DISCARD → {line}")

            while True:
                raw = input("Discard index or tile: ").strip().upper()
                # 自摸快捷
                if hu_action is not None and raw in ("H", "HU"):
                    return dict(hu_action)
                # 索引
                if raw.isdigit():
                    idx = int(raw)
                    if 0 <= idx < len(display_actions):
                        return dict(display_actions[idx])
                    print("索引超出範圍，請重新輸入。")
                    continue
                # 牌面字串（允許尾端 *）
                key = raw.rstrip("*")
                for a, lbl in zip(display_actions, display_labels):
                    if lbl.rstrip("*").upper() == key:
                        return dict(a)
                print("無效輸入，請輸入索引或合法牌面（例如 7W）。")

        else:
            # REACTION：依優先度排序
            prio = {"HU": 0, "GANG": 1, "PONG": 2, "CHI": 3, "PASS": 9}
            ld = obs.get("last_discard") or {}
            ld_tile = ld.get("tile")

            def key_react(a: Dict[str, Any]):
                t = (a.get("type") or "").upper()
                if t == "CHI":
                    use = a.get("use", [])
                    s = [tile_to_str(x) for x in (use or [])]
                    return (prio[t], s)
                return (prio.get(t, 9), tile_to_str(ld_tile) if ld_tile is not None else "")

            reacts = sorted(list(acts), key=key_react)

            labels: List[str] = []
            for a in reacts:
                t = (a.get("type") or "").upper()
                if t in ("HU", "PONG", "GANG"):
                    labels.append(t if ld_tile is None else f"{t} {tile_to_str(ld_tile)}")
                elif t == "CHI":
                    use = a.get("use", [])
                    if isinstance(use, list) and len(use) == 2:
                        labels.append(
                            f"CHI {tile_to_str(use[0])}-{tile_to_str(use[1])}  {tile_to_str(ld_tile) if ld_tile is not None else ''}".strip()
                        )
                    else:
                        labels.append("CHI")
                else:
                    labels.append("PASS")

            print(f"\n=== Your Reaction | P{player} → to {fmt_tile(ld_tile)} ===")
            # 反應選單包含多個牌面（如 'CHI 6D-8D  7D'），需以正則逐一上色
            print("  ".join(f"[{i}] {_colorize_text_tiles(lbl)}" for i, lbl in enumerate(labels)))

            while True:
                raw = input("Select action index: ").strip()
                if raw.isdigit():
                    idx = int(raw)
                    if 0 <= idx < len(reacts):
                        return dict(reacts[idx])
                    print("索引超出範圍，請重新輸入。")
                    continue
                print("請輸入數字索引。")

# ========= 主程式迴圈 =========

def run_demo(seed=None, human_pid: Optional[int] = 0):
    rules = Ruleset(
        include_flowers=True,
        dead_wall_mode="fixed",   # 或 "kong_plus_one"
        dead_wall_base=16,
        scoring_profile="gametower_star31",     # 或 "mj888"
        see_flower_see_wind=False,               # 是否採用見花見字（風刻/花牌等定義）
        scoring_overrides_path=None             # 可指向外部 JSON 覆蓋
    )
    env = Mahjong16Env(rules, seed=seed)

    print("=== mahjong16 demo（精簡輸出：隱藏 PASS；丟牌才遞增步數；每次丟牌後列四家快照） ===")

    obs = env.reset()
    discard_id = 0  # 僅在丟牌進河時遞增

    # 建立每位玩家的策略（指定 human_pid 走 HumanStrategy，其餘 AutoStrategy）
    strategies: List[Strategy] = []
    for pid in range(env.rules.n_players):
        if human_pid is not None and pid == human_pid:
            strategies.append(HumanStrategy())
        else:
            strategies.append(AutoStrategy())

    while True:
        # 依玩家策略選擇行動
        act = strategies[obs.get("player")].choose(obs)

        # 非 PASS 動作行（DISCARD 另行處理）
        atype = (act.get("type") or "").upper()
        if atype in ("HU", "GANG", "PONG", "CHI"):
            Formatter.print_action_line(act, obs)

        # step 前快取（避免 drawn 被環境清空）
        pre_pid = obs.get("player")
        pre_drawn = obs.get("drawn")
        pre_tile = act.get("tile") if atype == "DISCARD" else None

        # 前進環境
        obs, rew, done, info = env.step(act)

        # 若是丟牌：印丟牌列 + 快照（使用 step 前的 pre_drawn）
        if atype == "DISCARD" and pre_tile is not None:
            discard_id += 1
            Formatter.print_discard_line(discard_id, pre_pid, pre_tile, pre_drawn, env)
            Formatter.print_table_snapshot(env, pre_pid, pre_drawn)

        if done:
            print("=== round end ===")
            print(f"rewards: {rew}")
            break

        # 安全中止（理論上不會發生）
        if discard_id > 2000:
            print("=== stop (safety break) ===")
            break

if __name__ == "__main__":
    # human_pid=None 可切回全自動；預設 0 由你手動操控 P0
    run_demo(human_pid=2)