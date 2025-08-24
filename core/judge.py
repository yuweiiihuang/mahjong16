# file: core/judge.py
from __future__ import annotations
from functools import lru_cache
from typing import List, Dict, Any, Tuple
import json, os
from pathlib import Path
from .tiles import tile_to_str, is_flower
from .scoring_profiles import PY_SCORING_TABLE

# ----------------------------
# 基本判斷
# ----------------------------
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

def _load_profile_table(profile_name: str, override_path: str | None = None) -> dict:
    """
    嘗試載入外部 JSON 覆蓋；找不到時回退到內建表。
    - override_path：Ruleset.scoring_overrides_path 或環境變數 MAHJONG16_SCORING_JSON
    - 若 JSON 根節點含多個 profile，取指定名稱；若根節點即為單一表，也可直接使用
    """
    path = override_path or os.environ.get("MAHJONG16_SCORING_JSON")
    if path and Path(path).is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and profile_name in data:
                return data[profile_name]
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return PY_SCORING_TABLE.get(profile_name, {})

# ----------------------------
# 34 張計數工具
# ----------------------------
def _counts34(tiles: List[int]) -> List[int]:
    c = [0]*34
    for t in tiles:
        if 0 <= t < 34:
            c[t] += 1
        else:
            return [0]*34
    return c

def _is_suited_idx(i: int) -> bool:
    return 0 <= i <= 26  # 0..8(萬), 9..17(筒), 18..26(條)

def _same_suit_triplet_ok(i: int) -> bool:
    if not (_is_suited_idx(i) and _is_suited_idx(i+1) and _is_suited_idx(i+2)):
        return False
    if i in (8, 17, 26):  # 跨邊界
        return False
    if (i//9) != ((i+1)//9) or (i//9) != ((i+2)//9):
        return False
    return True

# （仍保留：只刻/只順 的 DFS，可做其他用途）
@lru_cache(maxsize=None)
def _dfs_only_pungs(state: Tuple[int, ...], need: int, eye_used: bool) -> bool:
    if need == 0:
        total = sum(state)
        if eye_used:
            return total == 0
        if total != 2:
            return False
        return any(c == 2 for c in state)
    i = next((idx for idx, c in enumerate(state) if c > 0), -1)
    if i == -1:
        return False
    c = state[i]
    if c >= 3:
        lst = list(state); lst[i] -= 3
        if _dfs_only_pungs(tuple(lst), need-1, eye_used):
            return True
    if not eye_used and c >= 2:
        lst = list(state); lst[i] -= 2
        if _dfs_only_pungs(tuple(lst), need, True):
            return True
    return False

@lru_cache(maxsize=None)
def _dfs_only_chows(state: Tuple[int, ...], need: int, eye_used: bool) -> bool:
    if need == 0:
        total = sum(state)
        if eye_used:
            return total == 0
        if total != 2:
            return False
        return any(c == 2 for c in state)
    i = next((idx for idx, c in enumerate(state) if c > 0), -1)
    if i == -1:
        return False
    if _same_suit_triplet_ok(i):
        i1, i2 = i+1, i+2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[i]  -= 1; lst[i1] -= 1; lst[i2] -= 1
            if _dfs_only_chows(tuple(lst), need-1, eye_used):
                return True
    c = state[i]
    if not eye_used and c >= 2:
        lst = list(state); lst[i] -= 2
        if _dfs_only_chows(tuple(lst), need, True):
            return True
    return False

# ----------------------------
# 主計分：混合式
# ----------------------------
def _score_env(env) -> list:
    winner = getattr(env, "winner", None)
    if winner is None:
        return [0] * env.rules.n_players

    rules = env.rules
    profile_name = getattr(rules, "scoring_profile", "gametower_star31")
    table = _load_profile_table(profile_name, getattr(rules, "scoring_overrides_path", None))

    # 預設值（若 profile 未提供）
    def P(key: str, default: int) -> int:
        return int(table.get(key, default))

    pl = env.players[winner]
    tsumo = _tsumo_detect(env)
    melds = pl.get("melds") or []
    flowers = pl.get("flowers") or []
    hand = list(pl.get("hand") or [])
    drawn = pl.get("drawn")
    concealed_tiles = list(hand)
    # 只有自摸才把 drawn 算進隱蔽牌；榮和時贏家不應有自家 drawn
    if tsumo and (drawn is not None):
        concealed_tiles.append(drawn)

    # ---- 狀態與統計 ----
    menqing = all((m.get("type") not in ("CHI","PONG","GANG")) for m in melds)

    fixed_melds = 0
    fixed_melds_pungs = 0
    fixed_melds_chis  = 0
    dragon_pungs = 0

    for m in melds:
        mtype = (m.get("type") or "").upper()
        if mtype in ("CHI","PONG","GANG"):
            fixed_melds += 1
        tiles_m = m.get("tiles") or []
        if tiles_m:
            t0 = tiles_m[0]
            if mtype in ("PONG","GANG"):
                fixed_melds_pungs += 1
                if _is_dragon(t0): dragon_pungs += 1
            elif mtype == "CHI":
                fixed_melds_chis += 1

    has_honor_in_all = any(_is_honor(t) for t in concealed_tiles) or any(
        _is_honor(t) for m in melds for t in (m.get("tiles") or [])
    )

    # ---- 台數（門清/自摸/無字無花）----
    fan = 0
    menqing_bonus = 0
    zimo_bonus = 0

    if menqing and tsumo and P("menqing_zimo", 3):
        fan += P("menqing_zimo", 3)
    else:
        if menqing:
            menqing_bonus = P("menqing", 1)
        if tsumo:
            zimo_bonus = P("zimo", 1)

    if dragon_pungs:
        fan += dragon_pungs * P("dragon_pung", 1)

    fan += menqing_bonus
    fan += zimo_bonus

    if tsumo and len(env.wall) == _dead_wall_reserved(env):
        fan += P("hai_di", 1)

    if getattr(env, "win_by_gang_draw", False):
        fan += P("gang_shang", 0)
    if getattr(env, "winner_is_dealer", False):
        fan += P("dealer", 0)

    # ----------------------------
    # 牌型類
    # ----------------------------
    # 全部牌
    all_tiles = list(concealed_tiles)
    for m in melds:
        all_tiles.extend(m.get("tiles") or [])

    suits = set()
    for t in all_tiles:
        s = tile_to_str(t)
        if len(s) == 2:
            suits.add(s[1])  # 'W','D','B'
    has_honor_total = any(_is_honor(t) for t in all_tiles)

    # 清一色／混一色（至少 1 組副露）
    if fixed_melds > 0:
        if len(suits) == 1 and not has_honor_total:
            fan += P("qing_yi_se", 8)
        elif len(suits) == 1 and has_honor_total:
            fan += P("hun_yi_se", 4)

    # 碰碰胡：副露不可含 CHI，且隱蔽部分必須是「純刻子 + 1 對」
    if fixed_melds_chis == 0:
        need = 5 - fixed_melds
        if need >= 0:
            # 按牌面字串計數（避免依賴 0..33 編號）
            cnt: Dict[str, int] = {}
            for t in concealed_tiles:
                s = tile_to_str(t)
                cnt[s] = cnt.get(s, 0) + 1
            mods = [c % 3 for c in cnt.values()]
            if mods.count(2) == 1 and all(m in (0, 2) for m in mods) and len(concealed_tiles) == need*3 + 2:
                fan += P("peng_peng_hu", 4)

    # 平胡：副露不可含 PONG/GANG（可有 CHI），且隱蔽部分必須能被「順子 + 1 對」完全分解
    if fixed_melds_pungs == 0 and fixed_melds_chis > 0:
        need = 5 - fixed_melds
        if need >= 0 and len(concealed_tiles) == need * 3 + 2:
            counts34 = _counts34(concealed_tiles)
            # 確認索引有效（沒有越界牌）
            if sum(counts34) == len(concealed_tiles):
                if _dfs_only_chows(tuple(counts34), need, False):
                    fan += P("ping_hu", 2)

    # 大小三元（總張數）
    def _cnt_total(label: str) -> int:
        tid = None
        for i in range(34):
            if tile_to_str(i) == label:
                tid = i; break
        if tid is None: return 0
        total = concealed_tiles.count(tid)
        for m in melds:
            total += (m.get("tiles") or []).count(tid)
        return total

    c_cnt = _cnt_total("C")
    f_cnt = _cnt_total("F")
    p_cnt = _cnt_total("P")
    # 對子需「恰為 2 張」，不可與刻子(>=3)重疊
    triplets = sum(1 for x in (c_cnt, f_cnt, p_cnt) if x >= 3)
    pairs    = sum(1 for x in (c_cnt, f_cnt, p_cnt) if x == 2)
    if triplets == 3:
        fan += P("da_san_yuan", 8)
    elif triplets == 2 and pairs == 1:
        fan += P("xiao_san_yuan", 4)

    # 大小四喜（總張數）
    def _cnt_wind(label: str) -> int:
        tid = None
        for i in range(34):
            if tile_to_str(i) == label:
                tid = i; break
        if tid is None: return 0
        total = concealed_tiles.count(tid)
        for m in melds:
            total += (m.get("tiles") or []).count(tid)
        return total

    e_cnt = _cnt_wind("E")
    s_cnt = _cnt_wind("S")
    w_cnt = _cnt_wind("W")
    n_cnt = _cnt_wind("N")
    # 小四喜的對子也必須「恰為 2 張」
    w_triplets = sum(1 for x in (e_cnt, s_cnt, w_cnt, n_cnt) if x >= 3)
    w_pairs    = sum(1 for x in (e_cnt, s_cnt, w_cnt, n_cnt) if x == 2)
    if w_triplets == 4:
        fan += P("da_si_xi", 16)
    elif w_triplets == 3 and w_pairs == 1:
        fan += P("xiao_si_xi", 8)

    rewards = [0] * env.rules.n_players
    rewards[winner] = fan
    return rewards

# ----------------------------
# 胡牌判定（原本的）
# ----------------------------
def is_win_16(tiles: List[int], melds: List[Dict[str, Any]], rules) -> bool:
    fixed_melds = 0
    for m in melds or []:
        t = (m.get("type") or "").upper()
        if t in ("CHI", "PONG", "GANG"):
            fixed_melds += 1
    need_melds = 5 - fixed_melds
    if need_melds < 0:
        return False
    if len(tiles) != need_melds * 3 + 2:
        return False

    counts = [0] * 34
    for t in tiles:
        if 0 <= t < 34:
            counts[t] += 1
        else:
            return False

    def is_suited(i: int) -> bool:
        return 0 <= i <= 26

    def same_suit_triplet_ok(i: int) -> bool:
        if not (is_suited(i) and is_suited(i+1) and is_suited(i+2)):
            return False
        if i in (8,17,26):
            return False
        if (i//9) != ((i+1)//9) or (i//9) != ((i+2)//9):
            return False
        return True

    @lru_cache(maxsize=None)
    def dfs(state: tuple, need: int, eye_used: bool) -> bool:
        if need == 0:
            total = sum(state)
            if eye_used:
                return total == 0
            if total != 2:
                return False
            for c in state:
                if c == 2:
                    return True
            return False

        i = next((idx for idx, c in enumerate(state) if c > 0), -1)
        if i == -1:
            return False

        if state[i] >= 3:
            lst = list(state); lst[i] -= 3
            if dfs(tuple(lst), need-1, eye_used):
                return True

        if same_suit_triplet_ok(i):
            i1, i2 = i+1, i+2
            if state[i1] > 0 and state[i2] > 0:
                lst = list(state)
                lst[i]  -= 1; lst[i1] -= 1; lst[i2] -= 1
                if dfs(tuple(lst), need-1, eye_used):
                    return True

        if not eye_used and state[i] >= 2:
            lst = list(state); lst[i] -= 2
            if dfs(tuple(lst), need, True):
                return True

        return False

    return dfs(tuple(counts), need_melds, False)

def settle_scores_stub(env) -> List[int]:
    return _score_env(env)