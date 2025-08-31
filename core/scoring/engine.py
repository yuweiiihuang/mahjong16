from __future__ import annotations
from typing import Any, Dict, List, Tuple

from ..tiles import tile_to_str, is_flower
from ..hand import waits_for_hand_16, _counts34  # reuse pure helpers
from .types import ScoringContext


def _is_honor(t: int) -> bool:
    ch = tile_to_str(t)[0]
    return ch in ("E", "S", "W", "N", "C", "F", "P")


def _is_dragon(t: int) -> bool:
    ch = tile_to_str(t)[0]
    return ch in ("C", "F", "P")


def _dead_wall_reserved(ctx: ScoringContext) -> int:
    mode = getattr(ctx.rules, "dead_wall_mode", "fixed")
    base = getattr(ctx.rules, "dead_wall_base", 16)
    if mode == "gang_plus_one":
        return base + int(getattr(ctx, "n_gang", 0) or 0)
    return base


def score_with_breakdown(ctx: ScoringContext) -> tuple[List[int], Dict[int, List[Dict[str, Any]]]]:
    winner = ctx.winner
    if winner is None:
        return [0] * ctx.rules.n_players, {i: [] for i in range(ctx.rules.n_players)}

    table = ctx.table
    labels = table.labels

    def P(key: str, default: int) -> int:
        return int(table.get(key, default))

    breakdown_by_player: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(ctx.rules.n_players)}
    bd: List[Dict[str, Any]] = breakdown_by_player[winner]

    def add(key: str, base: int | None = None, count: int = 1, meta: Dict[str, Any] | None = None) -> int:
        b = int(P(key, 0) if base is None else base)
        if b == 0 or count == 0:
            return 0
        pts = b * count
        item = {"key": key, "label": labels.get(key, key), "base": b, "count": count, "points": pts}
        if meta:
            item["meta"] = meta
        bd.append(item)
        return pts

    pl = ctx.players[winner]
    tsumo = str(ctx.win_source).upper() in ("TSUMO", "ZIMO")
    melds = pl.melds or []
    flowers = pl.flowers or []  # not used currently, placeholder for variants
    hand = list(pl.hand or [])
    drawn = pl.drawn

    # concealed tiles
    concealed_tiles = list(hand)
    if tsumo and (drawn is not None):
        concealed_tiles.append(drawn)

    fixed_melds = sum(1 for m in (melds or []) if (m.get("type") or "").upper() in ("CHI", "PONG", "GANG"))
    need = 5 - fixed_melds
    required_len = need * 3 + 2 if need >= 0 else None

    # ron tile
    ron_tile = None
    if not tsumo:
        wt = ctx.win_tile
        if isinstance(wt, int):
            ron_tile = wt
        else:
            ld = ctx.last_discard
            if isinstance(ld, dict):
                ron_tile = ld.get("tile")

    concealed_for_patterns = list(concealed_tiles)
    if (not tsumo) and isinstance(ron_tile, int) and (required_len is not None):
        if len(concealed_for_patterns) == required_len - 1:
            concealed_for_patterns.append(ron_tile)

    # stats
    menqing = all((m.get("type") not in ("CHI", "PONG", "GANG")) for m in melds)
    fixed_melds_pungs = 0
    fixed_melds_chis = 0
    dragon_pungs = 0
    for m in melds:
        mtype = (m.get("type") or "").upper()
        tiles_m = m.get("tiles") or []
        if mtype in ("PONG", "GANG"):
            fixed_melds_pungs += 1
            if tiles_m and _is_dragon(tiles_m[0]):
                dragon_pungs += 1
        elif mtype == "CHI":
            fixed_melds_chis += 1

    # base patterns
    if menqing and tsumo and P("menqing_zimo", 3):
        add("menqing_zimo")
    else:
        if menqing:
            add("menqing")
        if tsumo:
            add("zimo")

    if dragon_pungs:
        add("dragon_pung", count=dragon_pungs)

    if tsumo and ctx.wall_len == _dead_wall_reserved(ctx):
        add("hai_di")

    if ctx.win_by_gang_draw:
        add("gang_shang")
    if ctx.winner_is_dealer:
        add("dealer")

    # ting (聽牌)
    tenpai_before_draw = False
    if tsumo:
        try:
            waits = waits_for_hand_16(list(pl.hand or []), list(pl.melds or []), ctx.rules, exclude_exhausted=True)
            tenpai_before_draw = bool(waits)
        except Exception:
            tenpai_before_draw = False
    if bool(pl.declared_ting) or tenpai_before_draw:
        add("ting")

    # pattern-based
    all_tiles = list(concealed_for_patterns)
    for m in melds:
        all_tiles.extend(m.get("tiles") or [])

    suits = set()
    for t in all_tiles:
        s = tile_to_str(t)
        if len(s) == 2:
            suits.add(s[1])
    has_honor_total = any(_is_honor(t) for t in all_tiles)

    if fixed_melds > 0:
        if len(suits) == 1 and not has_honor_total:
            add("qing_yi_se")
        elif len(suits) == 1 and has_honor_total:
            add("hun_yi_se")

    # peng peng hu
    if fixed_melds_chis == 0 and need >= 0 and required_len is not None:
        if len(concealed_for_patterns) == required_len:
            cnt: Dict[str, int] = {}
            for t in concealed_for_patterns:
                s = tile_to_str(t)
                cnt[s] = cnt.get(s, 0) + 1
            mods = [c % 3 for c in cnt.values()]
            if mods.count(2) == 1 and all(m in (0, 2) for m in mods):
                add("peng_peng_hu")

    # ping hu
    if fixed_melds_pungs == 0 and fixed_melds_chis > 0 and need >= 0 and required_len is not None:
        if len(concealed_for_patterns) == required_len:
            counts34 = _counts34(concealed_for_patterns)
            if sum(counts34) == len(concealed_for_patterns):
                # DFS over only chows (reuse menqing-style helper not needed here)
                if _dfs_only_chows(tuple(counts34), need, False):
                    add("ping_hu")

    # xiao/da san yuan and si xi
    def _cnt_total(label: str) -> int:
        tile_id = None
        for i in range(34):
            if tile_to_str(i) == label:
                tile_id = i
                break
        if tile_id is None:
            return 0
        return all_tiles.count(tile_id)

    cntC = _cnt_total("C")
    cntF = _cnt_total("F")
    cntP = _cnt_total("P")
    tripC = cntC // 3
    tripF = cntF // 3
    tripP = cntP // 3
    pairC = cntC % 3 == 2
    pairF = cntF % 3 == 2
    pairP = cntP % 3 == 2
    triplets = tripC + tripF + tripP
    has_pair = pairC or pairF or pairP

    if triplets == 2 and has_pair:
        add("xiao_san_yuan")
    if triplets == 3:
        add("da_san_yuan")

    def _cnt_wind(label: str) -> int:
        tile_id = None
        for i in range(34):
            if tile_to_str(i) == label:
                tile_id = i
                break
        if tile_id is None:
            return 0
        return all_tiles.count(tile_id)

    cntE = _cnt_wind("E")
    cntS = _cnt_wind("S")
    cntW = _cnt_wind("W")
    cntN = _cnt_wind("N")
    trips = (cntE // 3) + (cntS // 3) + (cntW // 3) + (cntN // 3)
    pairs = ((cntE % 3) == 2) + ((cntS % 3) == 2) + ((cntW % 3) == 2) + ((cntN % 3) == 2)

    if trips == 3 and pairs == 1:
        add("xiao_si_xi")
    if trips == 4:
        add("da_si_xi")

    # excludes/includes constraints can be enforced later if needed

    rewards = [0] * ctx.rules.n_players
    total = sum(item.get("points", 0) for item in bd)
    rewards[winner] = total
    return rewards, breakdown_by_player


# local helper for only-chows DFS (copied from previous judge implementation)
from functools import lru_cache


def _is_suited_idx(i: int) -> bool:
    return 0 <= i <= 26


def _same_suit_triplet_ok(i: int) -> bool:
    if not (_is_suited_idx(i) and _is_suited_idx(i + 1) and _is_suited_idx(i + 2)):
        return False
    if i in (8, 17, 26):
        return False
    if (i // 9) != ((i + 1) // 9) or (i // 9) != ((i + 2) // 9):
        return False
    return True


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
        i1, i2 = i + 1, i + 2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[i] -= 1
            lst[i1] -= 1
            lst[i2] -= 1
            if _dfs_only_chows(tuple(lst), need - 1, eye_used):
                return True
    c = state[i]
    if not eye_used and c >= 2:
        lst = list(state)
        lst[i] -= 2
        if _dfs_only_chows(tuple(lst), need, True):
            return True
    return False

