# main.py
from __future__ import annotations
from typing import Dict, Any, List
from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str, hand_to_str

# 反應優先權：HU > GANG > PONG > CHI
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}

def fmt_tile(t: int | None) -> str:
    return "None" if t is None else tile_to_str(t)

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
    hand_s = hand_to_str(me["hand"])
    melds_s = render_melds(me["melds"])
    print(f"[D{did:03d}]P{pid} DISCARD {tile_to_str(tile)} | hand={hand_s} | melds={melds_s} | drawn={fmt_tile(pre_drawn)}")

def print_table_snapshot(env: Mahjong16Env, discarder_pid: int, pre_drawn: int | None) -> None:
    """在丟牌後輸出四家快照；丟牌者那行帶 step 前的 drawn，其餘不顯示 drawn。"""
    for p in range(env.rules.n_players):
        pl = env.players[p]
        hand_s = hand_to_str(pl["hand"])
        melds_s = render_melds(pl["melds"])
        if p == discarder_pid:
            print(f"      P{p} | hand={hand_s} | melds={melds_s} | drawn={fmt_tile(pre_drawn)}")
        else:
            print(f"      P{p} | hand={hand_s} | melds={melds_s}")

def run_demo(seed=None):
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
        run_demo(31)
