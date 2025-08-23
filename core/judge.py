from __future__ import annotations
from functools import lru_cache
from typing import List, Dict, Any
from .tiles import tile_to_str, is_flower

def _is_honor(t: int) -> bool:
    ch = tile_to_str(t)[0]
    return ch in ("E","S","W","N","C","F","P")

def _is_wind(t: int) -> bool:
    ch = tile_to_str(t)[0]
    return ch in ("E","S","W","N")

def _is_dragon(t: int) -> bool:
    ch = tile_to_str(t)[0]
    return ch in ("C","F","P")

def _tsumo_detect(env) -> bool:
    src = getattr(env, "win_source", None)
    return str(src).upper() in ("TSUMO","ZIMO")

def _dead_wall_reserved(env) -> int:
    mode = getattr(env.rules, "dead_wall_mode", "fixed")
    base = getattr(env.rules, "dead_wall_base", 16)
    if mode == "gang_plus_one":
        return base + getattr(env, "n_gang", 0)
    return base

def _score_env(env) -> list:
    winner = getattr(env, "winner", None)
    if winner is None:
        return [0] * env.rules.n_players
    pl = env.players[winner]
    tsumo = _tsumo_detect(env)
    melds = pl.get("melds") or []
    flowers = pl.get("flowers") or []
    hand = list(pl.get("hand") or [])
    drawn = pl.get("drawn")
    if drawn is not None:
        hand.append(drawn)

    menqing = all((m.get("type") not in ("CHI","PONG","GANG")) for m in melds)
    fan = 0
    menqing_awarded = False
    if menqing and tsumo:
        fan += 3
        menqing_awarded = True
    else:
        if tsumo:
            fan += 1
        # 暫不立即加門清，先看是否符合「無字無花」

    fan += len(flowers)

    for m in melds:
        if m.get("type") in ("PONG","GANG"):
            tiles = m.get("tiles") or []
            if not tiles:
                continue
            t0 = tiles[0]
            if _is_wind(t0):
                fan += 1
            if _is_dragon(t0):
                fan += 1
            if m.get("type") == "GANG":
                fan += 1

    # 無字無花 +2：須「門清」且整副皆無字，且無花
    has_honor = any(_is_honor(t) for t in hand) or any(_is_honor(t) for m in melds for t in (m.get("tiles") or []))
    if menqing and not flowers and not has_honor:
        # 無字無花 +2 與門清不疊加 → 只加 +2
        fan += 2
        menqing_awarded = True
    elif menqing and not menqing_awarded:
        # 非「門清自摸=3」，且非「無字無花」時，才補門清 +1
        fan += 1

    if tsumo and len(env.wall) == _dead_wall_reserved(env):
        fan += 1

    rewards = [0] * env.rules.n_players
    rewards[winner] = fan
    return rewards

# 入口：判定「五面子（順子或刻子）+ 一個眼睛」
def is_win_16(tiles: List[int], melds: List[Dict[str, Any]], rules) -> bool:
    """
    tiles: 目前「手上的牌」；自摸請傳 hand + drawn；榮和傳 hand + 榮進來的牌
    melds: 既有的吃／碰／槓（每一組算 1 個面子）
      - 形如 {"type":"CHI"|"PONG"|"GANG", "tiles":[...]}
    規則：這裡只用到需要的面子數（固定 5）
    """
    # 既有面子數（吃/碰/槓都算 1 組）
    fixed_melds = 0
    for m in melds or []:
        t = (m.get("type") or "").upper()
        if t in ("CHI", "PONG", "GANG"):
            fixed_melds += 1

    need_melds = 5 - fixed_melds
    if need_melds < 0:
        return False  # 異常：面子數不應超過 5

    # 目前 tiles 必須恰好能拆成「need_melds*3 + 2」
    if len(tiles) != need_melds * 3 + 2:
        return False

    # 把牌轉為 34 種牌的計數（假設 0..33：3門數牌 + 字牌；花牌在抽牌時已替換，不會出現在此）
    # 你的 tiles.py 應已用 0..26 為數牌，27..33 為字牌。若不同，請調整「是否可做順子」的判定。
    counts = [0] * 34
    for t in tiles:
        if 0 <= t < 34:
            counts[t] += 1
        else:
            # 防守：未知編碼直接失敗（或忽略）
            return False

    # 內部工具
    def is_suited(i: int) -> bool:
        return 0 <= i <= 26  # 0..8(萬), 9..17(筒), 18..26(條)

    def same_suit_triplet_ok(i: int) -> bool:
        # 是否能以 i,i+1,i+2 做順子（且不跨花色）
        if not is_suited(i) or not is_suited(i + 1) or not is_suited(i + 2):
            return False
        # 防跨界（9/18/27 的邊界）
        if (i == 8) or (i == 17) or (i == 26):
            return False
        # 同一花色區段內
        if (i // 9) != ((i + 1) // 9) or (i // 9) != ((i + 2) // 9):
            return False
        return True

    @lru_cache(maxsize=None)
    def dfs(state: tuple, need: int, eye_used: bool) -> bool:
        # state: 34-tuple of counts
        if need == 0:
            # 需剩下一個眼睛（已用眼睛則應全清空；未用則必須恰好剩 2 張同值）
            total = sum(state)
            if eye_used:
                return total == 0
            # 未用眼睛：必須只剩一對
            if total != 2:
                return False
            for i, c in enumerate(state):
                if c == 2:
                    return True
            return False

        # 找到第一個有牌的 index
        i = -1
        for idx, c in enumerate(state):
            if c > 0:
                i = idx
                break
        if i == -1:
            # 沒牌了但仍有 need>0，失敗
            return False

        # 嘗試：刻子
        c = state[i]
        if c >= 3:
            lst = list(state)
            lst[i] -= 3
            if dfs(tuple(lst), need - 1, eye_used):
                return True

        # 嘗試：順子（僅數牌）
        if same_suit_triplet_ok(i):
            i1, i2 = i + 1, i + 2
            if state[i1] > 0 and state[i2] > 0:
                lst = list(state)
                lst[i] -= 1
                lst[i1] -= 1
                lst[i2] -= 1
                if dfs(tuple(lst), need - 1, eye_used):
                    return True

        # 嘗試：眼睛（若尚未使用）
        if not eye_used and c >= 2:
            lst = list(state)
            lst[i] -= 2
            if dfs(tuple(lst), need, True):
                return True

        return False

    return dfs(tuple(counts), need_melds, False)


def settle_scores_stub(env) -> List[int]:
    return _score_env(env)
