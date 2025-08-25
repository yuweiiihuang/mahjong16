# file: main.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple, Protocol
import re
from bots import GreedyBotStrategy
from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str
from core.judge import score_with_breakdown
from ui.console import render_public_view, render_reveal

# ======================================================================
# 常數與共用
# ======================================================================

# 反應優先權：HU > GANG > PONG > CHI（供 HumanStrategy 顯示排序使用）
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}

# ── ANSI 著色（人機互動提示用；UI 主體在 ui.console）
ANSI_RESET = "\033[0m"
ANSI_RED   = "\033[31m"  # 萬
ANSI_BLUE  = "\033[34m"  # 筒
ANSI_GREEN = "\033[32m"  # 條
ANSI_MAG   = "\033[35m"  # 字（風/箭）

# ======================================================================
# 小工具（字串/牌面）
# ======================================================================

def _colorize_label(s: str) -> str:
    """上色單一牌面字串（允許尾端 * 標記）。"""
    if not s:
        return s
    if s.endswith("*"):
        core = s[:-1]
        return f"{_colorize_label(core)}*"
    ch0 = s[0]
    if ch0.isdigit() and len(s) >= 2:
        suit = s[-1]
        if suit == "W":
            return f"{ANSI_RED}{s}{ANSI_RESET}"
        if suit == "D":
            return f"{ANSI_BLUE}{s}{ANSI_RESET}"
        if suit == "B":
            return f"{ANSI_GREEN}{s}{ANSI_RESET}"
    if ch0 in "ESWNCFP" and len(s) == 1:
        return f"{ANSI_MAG}{s}{ANSI_RESET}"
    return s

def _colorize_tile(t: int) -> str:
    return _colorize_label(tile_to_str(t))

def fmt_tile(t: int | None) -> str:
    return "None" if t is None else _colorize_tile(t)

_TILE_TOKEN_RE = re.compile(r'(?<!\w)(?:[1-9][WDB]|[ESWNCFP])(?!\w)')

def _colorize_text_tiles(text: str) -> str:
    def _repl(m: re.Match) -> str:
        return _colorize_label(m.group(0))
    return _TILE_TOKEN_RE.sub(_repl, text)

def _suit_of(t: int) -> int:
    if 0 <= t <= 8: return 0
    if 9 <= t <= 17: return 1
    if 18 <= t <= 26: return 2
    return 3

def _rank_of(t: int) -> int:
    if 0 <= t <= 8: return t - 0 + 1
    if 9 <= t <= 17: return t - 9 + 1
    if 18 <= t <= 26: return t - 18 + 1
    return 0

_HONOR_ORDER = {"E": 0, "S": 1, "W": 2, "N": 3, "C": 4, "F": 5, "P": 6}

def _honor_index(t: int) -> int:
    label = tile_to_str(t)
    key = label[0] if label else "?"
    return _HONOR_ORDER.get(key, 99)

def _tile_sort_key(t: int):
    s = _suit_of(t)
    return (s, _rank_of(t), tile_to_str(t)) if s < 3 else (s, _honor_index(t), tile_to_str(t))

def _sort_tiles_for_display(tiles: List[int]) -> List[int]:
    return sorted(tiles, key=_tile_sort_key)

def render_melds(melds: List[Dict[str, Any]]) -> str:
    """將副露列成易讀字串（僅供 HumanStrategy 提示用；畫面主要靠 ui.console）。"""
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

# ======================================================================
# 輔助：事件摘要列印（只在 console 行輸出用；主要 UI 在 ui.console）
# ======================================================================

class Formatter:
    @staticmethod
    def print_action_line(act: Dict[str, Any], obs: Dict[str, Any]) -> None:
        """在 TURN 階段預先列印主動行為（REACTION 的顯示改由決議後輸出）。"""
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

# ======================================================================
# 策略：介面與內建策略
# ======================================================================

class Strategy(Protocol):
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]: ...

class AutoStrategy:
    """非常簡單的自動策略：能胡就胡；否則丟 drawn；否則任意丟。"""
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        acts = obs.get("legal_actions", []) or []
        phase = obs.get("phase")
        if phase == "REACTION":
            cand = [a for a in acts if (a.get("type") or "").upper() != "PASS"]
            if not cand:
                return {"type": "PASS"}
            cand.sort(key=lambda a: PRIORITY.get((a.get("type") or "").upper(), -1), reverse=True)
            return cand[0]
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
        return {"type": "PASS"}

class HumanStrategy:
    """CLI 人機互動：列出手牌/合法動作，輸入索引或牌面字串決策。"""
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        acts = obs.get("legal_actions", []) or []
        player = obs.get("player")
        phase = obs.get("phase")
        if not acts:
            print("\n[auto] No legal actions → PASS")
            return {"type": "PASS"}

        if phase == "TURN":
            return self._choose_turn(obs, acts, player)
        else:
            return self._choose_reaction(obs, acts, player)

    # ---- internal helpers for HumanStrategy ----
    def _choose_turn(self, obs: Dict[str, Any], acts: List[Dict[str, Any]], player: int) -> Dict[str, Any]:
        hand: List[int] = list(obs.get("hand") or [])
        drawn: Optional[int] = obs.get("drawn")
        hu_action = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
        discards_all: List[Dict[str, Any]] = [a for a in acts if (a.get("type") or "").upper() == "DISCARD"]

        def key_disc(a: Dict[str, Any]) -> Tuple:
            t = a.get("tile")
            src = a.get("from", "hand")
            # 讓從手牌丟的排前、drawn 丟的排後，並以花色順序顯示
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

        print(f"\n=== Your Turn | P{player} ===")
        sorted_hand_for_view = _sort_tiles_for_display(hand)
        print(f"Hand: {' '.join(_colorize_tile(t) for t in sorted_hand_for_view)}   Drawn: {fmt_tile(drawn)}")
        print(f"Melds: {render_melds(obs.get('melds') or [])}")

        if hu_action is not None:
            print("ACTIONS → [H] HU")
        line = "  ".join(f"[{i}] {_colorize_label(lbl)}" for i, lbl in enumerate(display_labels))
        print(f"DISCARD → {line}")

        while True:
            raw = input("Discard index or tile: ").strip().upper()
            if hu_action is not None and raw in ("H", "HU"):
                return dict(hu_action)
            if raw.isdigit():
                idx = int(raw)
                if 0 <= idx < len(display_actions):
                    return dict(display_actions[idx])
                print("索引超出範圍，請重新輸入。")
                continue
            key = raw.rstrip("*")
            for a, lbl in zip(display_actions, display_labels):
                if lbl.rstrip("*").upper() == key:
                    return dict(a)
            print("無效輸入，請輸入索引或合法牌面（例如 7W）。")

    def _choose_reaction(self, obs: Dict[str, Any], acts: List[Dict[str, Any]], player: int) -> Dict[str, Any]:
        """
        反應階段選單：固定 [0] = PASS，其餘選項依優先順序排列在後面。
        """
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

        # 先把 PASS 抽出來，其餘排序後接在後面；確保 [0] 一定是 PASS。
        pass_action = next((a for a in acts if (a.get("type") or "").upper() == "PASS"), {"type": "PASS"})
        others = [a for a in acts if (a.get("type") or "").upper() != "PASS"]
        others_sorted = sorted(others, key=key_react)

        def label_for(a: Dict[str, Any]) -> str:
            t = (a.get("type") or "").upper()
            if t in ("HU", "PONG", "GANG"):
                return t if ld_tile is None else f"{t} {tile_to_str(ld_tile)}"
            if t == "CHI":
                use = a.get("use", [])
                if isinstance(use, list) and len(use) == 2:
                    return f"CHI {tile_to_str(use[0])}-{tile_to_str(use[1])}  {tile_to_str(ld_tile) if ld_tile is not None else ''}".strip()
                return "CHI"
            return "PASS"

        menu_actions: List[Dict[str, Any]] = [pass_action] + others_sorted
        labels: List[str] = [label_for(a) for a in menu_actions]

        print(f"\n=== Your Reaction | P{player} → to {fmt_tile(ld_tile)} ===")
        print("  ".join(f"[{i}] {_colorize_text_tiles(lbl)}" for i, lbl in enumerate(labels)))

        while True:
            raw = input("Select action index: ").strip()
            if raw.isdigit():
                idx = int(raw)
                if 0 <= idx < len(menu_actions):
                    return dict(menu_actions[idx])
                print("索引超出範圍，請重新輸入。")
                continue
            print("請輸入數字索引。")

# ======================================================================
# 主流程輔助：策略工廠 / 事件摘要 / UI 更新
# ======================================================================

def build_strategies(n_players: int, human_pid: Optional[int], bot: str) -> List[Strategy]:
    """依 CLI 參數建立各家策略。"""
    strategies: List[Strategy] = []
    for pid in range(n_players):
        if human_pid is not None and pid == human_pid:
            strategies.append(HumanStrategy())
        else:
            if bot == "greedy":
                strategies.append(GreedyBotStrategy())
            elif bot == "human":
                strategies.append(HumanStrategy())
            else:
                strategies.append(AutoStrategy())
    return strategies

def summarize_resolved_claim(info: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    從 env.step(...) 回傳的 info 中提取決議事件摘要：
    回傳 {"who": "P?", "type": "...", "detail": "..."} or None
    """
    if not info or "resolved_claim" not in info:
        return None
    rc = info["resolved_claim"]
    t = (rc.get("type") or "").upper()
    pid = rc.get("pid")
    tile = rc.get("tile")
    detail = ""
    if t == "CHI":
        use = rc.get("use", [])
        if isinstance(use, list) and len(use) == 2:
            detail = f"{tile_to_str(use[0])}-{tile_to_str(use[1])} + {tile_to_str(tile)}"
    elif t in ("PONG", "GANG", "HU"):
        detail = tile_to_str(tile) or ""
    return {"who": f"P{pid}", "type": t, "detail": detail}

def update_ui(env: Mahjong16Env, human_pid: Optional[int], discard_id: int, last_action: Optional[Dict[str, Any]] = None) -> None:
    """統一呼叫 UI 重繪公開視角。"""
    pov = (human_pid if human_pid is not None else 0)
    render_public_view(env, pov_pid=pov, did=discard_id, last_action=last_action)

# ======================================================================
# 主要流程
# ======================================================================

def run_demo(seed=None, human_pid: Optional[int] = 0, bot: str = "auto"):
    """單盤 demo 迴圈。"""
    # 建立規則與環境
    rules = Ruleset(
        include_flowers=True,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        scoring_profile="gametower_star31",
        see_flower_see_wind=False,
        scoring_overrides_path=None,
    )
    env = Mahjong16Env(rules, seed=seed)
    print("=== mahjong16 demo（Rich Console UI） ===")

    # 初始化
    obs = env.reset()
    discard_id = 0
    strategies = build_strategies(env.rules.n_players, human_pid, bot)

    # 主迴圈
    while True:
        # 1) 回合開始：重繪 UI
        update_ui(env, human_pid, discard_id, last_action=None)

        # 2) 由當前玩家選擇動作
        act = strategies[obs.get("player")].choose(obs)

        # 3) TURN 階段的主動行為先印出（REACTION 則交給決議後再印）
        atype = (act.get("type") or "").upper()
        if obs.get("phase") == "TURN" and atype in ("HU", "GANG", "PONG", "CHI"):
            Formatter.print_action_line(act, obs)

        # 4) 紀錄丟牌前資訊
        pre_pid = obs.get("player")
        pre_tile = act.get("tile") if atype == "DISCARD" else None

        # 5) 送入環境
        obs, rew, done, info = env.step(act)

        # 6) 反應決議事件 → UI 顯示摘要
        event = summarize_resolved_claim(info) if isinstance(info, dict) else None
        if event:
            update_ui(env, human_pid, discard_id, last_action=event)

        # 7) 丟牌事件 → 立刻刷新
        if atype == "DISCARD" and pre_tile is not None:
            discard_id += 1
            update_ui(
                env,
                human_pid,
                discard_id,
                last_action={"who": f"P{pre_pid}", "type": "DISCARD", "detail": tile_to_str(pre_tile)},
            )

        # 8) 結束處理
        if done:
            print("=== round end ===")
            print(f"rewards: {rew}")

            # 額外列出 breakdown（易於驗證來源）
            rewards2, bd = score_with_breakdown(env)
            winner = env.winner
            if winner is not None:
                print(f"breakdown for P{winner}:")
                for item in bd.get(winner, []):
                    label = item.get("label", item.get("key"))
                    base = item.get("base", 0)
                    count = item.get("count", 1)
                    points = item.get("points", base * count)
                    print(f"  - {label}: {base} x {count} = {points}")
                print(f"total = {sum(i.get('points', 0) for i in bd.get(winner, []))}")

            # 終局亮牌
            render_reveal(env)
            break

        # 9) 安全保護：避免死循環
        if discard_id > 2000:
            print("=== stop (safety break) ===")
            break

# ======================================================================
# CLI
# ======================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="mahjong16 demo CLI")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (int). Omit for random.")
    parser.add_argument(
        "--human",
        type=str,
        default="0",
        help="Human player id (0-3), or 'none' for no human (all bots). Default: 0",
    )
    parser.add_argument(
        "--bot",
        type=str,
        default="greedy",
        choices=["auto", "greedy", "human"],
        help="Bot strategy for non-human players. Default: greedy",
    )
    args = parser.parse_args()

    # 解析 human 參數：支援 'none' / '-1' / 'no' 表示沒有真人
    human_str = (args.human or "").strip().lower()
    if human_str in ("none", "-1", "no", "n"):
        human_pid = None
    else:
        try:
            human_pid = int(args.human)
        except ValueError:
            raise SystemExit("Invalid --human value. Use 0-3 or 'none'.")
        if human_pid not in (0, 1, 2, 3):
            raise SystemExit("Invalid --human value. Must be 0,1,2,3 or 'none'.")

    run_demo(seed=args.seed, human_pid=human_pid, bot=args.bot)