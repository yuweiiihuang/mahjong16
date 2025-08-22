from __future__ import annotations
from functools import lru_cache
from typing import List, Dict, Any

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


# 暫時沿用樣板結算：流局全 0、和了全 0（之後再補）
def settle_scores_stub(env) -> List[int]:
    return [0] * env.rules.n_players
