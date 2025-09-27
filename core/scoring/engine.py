from __future__ import annotations
from typing import Any, Dict, List, Tuple

from ..tiles import tile_to_str, is_flower
from ..hand import waits_for_hand_16, _counts34  # reuse pure helpers
from .types import ScoringContext, Meld


def _is_honor(t: int) -> bool:
    """Return True if tile id corresponds to a wind/dragon (honor tile)."""
    ch = tile_to_str(t)[0]
    return ch in ("E", "S", "W", "N", "C", "F", "P")


def _is_dragon(t: int) -> bool:
    """Return True if tile id corresponds to a dragon (C/F/P)."""
    ch = tile_to_str(t)[0]
    return ch in ("C", "F", "P")


def _dead_wall_reserved(ctx: ScoringContext) -> int:
    """Compute current reserved tail length based on rules and number of gangs."""
    mode = getattr(ctx.rules, "dead_wall_mode", "fixed")
    base = getattr(ctx.rules, "dead_wall_base", 16)
    if mode == "gang_plus_one":
        return base + int(getattr(ctx, "n_gang", 0) or 0)
    return base


def score_with_breakdown(ctx: ScoringContext) -> tuple[List[int], Dict[int, List[Dict[str, Any]]]]:
    """Calculate per‑player rewards and a labeled breakdown for the winner.

    Args:
      ctx: ScoringContext built from the end‑of‑round env and preloaded table.

    Returns:
      (rewards, breakdown_by_player):
        - rewards: list of length ``n_players`` (台數), winner gets the sum, others 0.
        - breakdown_by_player: mapping pid -> list of items {key,label,base,count,points}.
    """
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
    melds: List[Meld] = pl.melds or []
    flowers = pl.flowers or []  # not used currently, placeholder for variants
    hand = list(pl.hand or [])
    drawn = pl.drawn

    # concealed tiles
    concealed_tiles = list(hand)
    if tsumo and (drawn is not None):
        concealed_tiles.append(drawn)

    fixed_melds = sum(1 for m in (melds or []) if (m.type or "").upper() in ("CHI", "PONG", "GANG", "ANGANG", "KAKAN"))
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
    # 門清：不可含明副露。明槓（大明槓 GANG、加槓 KAKAN）視為明副露；暗槓（ANGANG）不破門清。
    menqing = all((m.type not in ("CHI", "PONG", "GANG", "KAKAN")) for m in melds)
    fixed_melds_pungs = 0
    fixed_melds_chis = 0
    dragon_pungs = 0
    for m in melds:
        mtype = (m.type or "").upper()
        tiles_m = m.tiles or []
        if mtype in ("PONG", "GANG"):
            fixed_melds_pungs += 1
            if tiles_m and _is_dragon(tiles_m[0]):
                dragon_pungs += 1
        elif mtype == "CHI":
            fixed_melds_chis += 1

    # base patterns
    # 槓上自摸：已含自摸，不再重複加計『自摸』；若門清則僅加『門清』
    if tsumo and getattr(ctx, "win_by_gang_draw", False):
        if menqing:
            add("menqing")
    else:
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
    if getattr(ctx, "win_by_qiang_gang", False):
        add("qiang_gang")
    if ctx.winner_is_dealer:
        # 動態莊家台：若已連 N 莊 → 2N+1 台（N=0 時為 1 台）
        try:
            n = int(getattr(ctx, "dealer_streak", 0) or 0)
        except Exception:
            n = 0
        add("dealer", base=(2 * n + 1))

    # ting (聽牌)
    tenpai_before_draw = False
    if tsumo:
        try:
            melds_dicts = [{"type": m.type, "tiles": list(m.tiles or [])} for m in (pl.melds or [])]
            waits = waits_for_hand_16(list(pl.hand or []), melds_dicts, ctx.rules, exclude_exhausted=True)
            tenpai_before_draw = bool(waits)
        except Exception:
            tenpai_before_draw = False
    if bool(pl.declared_ting) or tenpai_before_draw:
        add("ting")

    # pattern-based
    all_tiles = list(concealed_for_patterns)
    for m in melds:
        all_tiles.extend(m.tiles or [])

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
    is_da_si_xi = False
    if trips == 4:
        add("da_si_xi")
        is_da_si_xi = True

    # excludes/includes constraints can be enforced later if needed

    # ====== 風位與圈風台 ======
    # - 圈風牌（當前圈的風做成刻/槓） +1
    # - 門風牌（自己的門風做成刻/槓） +1
    # 若為大四喜，按照常見約定不另計圈風/門風（已由大四喜吃掉）。
    if not is_da_si_xi and getattr(ctx.rules, "enable_wind_flower_scoring", False):
        try:
            qf = (getattr(ctx, "quan_feng", None) or "").upper()
            seat_winds = list(getattr(ctx, "seat_winds", []) or [])
            my_wind = (seat_winds[winner] if 0 <= winner < len(seat_winds) else None)
        except Exception:
            qf, my_wind = None, None

        def _has_wind_triplet(label: str | None) -> bool:
            if not label:
                return False
            return _cnt_wind(label) // 3 >= 1

        if _has_wind_triplet(qf):
            add("quan_feng_ke")
        if _has_wind_triplet(my_wind):
            add("men_feng_ke")

    # ====== 正花 / 花槓 ======
    # - 正花：依門風對應的兩朵花（東: 春/梅、南: 夏/蘭、西: 秋/菊、北: 冬/竹）每張 +1
    # - 花槓：集齊四季或四君子，各計一次
    if flowers and getattr(ctx.rules, "enable_wind_flower_scoring", False):
        # 解析 F1..F8 標籤並映射到 1..8 的序號
        def _flower_no(x: int) -> int | None:
            s = tile_to_str(x)
            if s and s.startswith("F"):
                try:
                    return int(s[1:])
                except Exception:
                    return None
            return None

        fnums = sorted([n for n in (_flower_no(t) for t in flowers) if isinstance(n, int)])
        fset = set(fnums)
        # 正花對應表（以常見順序：F1~F4=春夏秋冬，F5~F8=梅蘭菊竹）
        zheng_map = {
            "E": {1, 5},  # 春、梅
            "S": {2, 6},  # 夏、蘭
            "W": {3, 7},  # 秋、菊
            "N": {4, 8},  # 冬、竹
        }
        # 正花計數
        try:
            my_wind = (getattr(ctx, "seat_winds", None) or [None])[winner]
        except Exception:
            my_wind = None
        if isinstance(my_wind, str):
            targets = zheng_map.get(my_wind.upper(), set())
            cnt_zheng = len(fset.intersection(targets))
            if cnt_zheng > 0:
                add("zheng_hua", count=cnt_zheng)
        # 花槓：四季 or 四君子
        has_seasons = {1, 2, 3, 4}.issubset(fset)
        has_gentlemen = {5, 6, 7, 8}.issubset(fset)
        hua_gang_cnt = int(has_seasons) + int(has_gentlemen)
        if hua_gang_cnt:
            add("hua_gang", count=hua_gang_cnt)

    rewards = [0] * ctx.rules.n_players
    total = sum(item.get("points", 0) for item in bd)
    rewards[winner] = total
    return rewards, breakdown_by_player


def compute_payments(
    ctx: ScoringContext,
    base_points: int,
    tai_points: int,
    rewards: List[int] | None = None,
    breakdown: Dict[int, List[Dict[str, Any]]] | None = None,
) -> tuple[List[int], Dict[int, List[Dict[str, Any]]]]:
    """Return net chip movement per player under the Taiwan 16-tile payout rule.

    Args:
      ctx: Prepopulated scoring context.
      base_points: Flat base paid per opponent.
      tai_points: Value of each tai.

    Returns:
      (payments, breakdown):
        - payments: list of length ``n_players`` with net gain/loss per player.
        - breakdown: same structure as ``score_with_breakdown`` for reuse.
    """

    if rewards is None or breakdown is None:
        rewards, breakdown = score_with_breakdown(ctx)
    else:
        rewards = list(rewards)
        breakdown = {pid: list(items) for pid, items in breakdown.items()}
    n_players = ctx.rules.n_players
    payments = [0] * n_players
    winner = ctx.winner
    if winner is None:
        return payments, breakdown

    try:
        base_points_int = int(base_points)
    except Exception:
        base_points_int = 0
    try:
        tai_points_int = int(tai_points)
    except Exception:
        tai_points_int = 0

    base_tai = int(rewards[winner]) if winner < len(rewards) else 0

    dealer_pid = getattr(ctx, "dealer_pid", None)
    try:
        dealer_streak = max(0, int(getattr(ctx, "dealer_streak", 0) or 0))
    except Exception:
        dealer_streak = 0

    dealer_bonus_for_payer = 0
    if dealer_pid is not None:
        try:
            dealer_bonus_for_payer = max(0, 2 * dealer_streak + 1)
        except Exception:
            dealer_bonus_for_payer = 0

    def extra_tai_for(opponent_pid: int) -> int:
        if dealer_pid is None:
            return 0
        if winner == dealer_pid:
            return 0
        if opponent_pid == dealer_pid:
            return dealer_bonus_for_payer
        return 0

    def payout_for(opponent_pid: int) -> int:
        total_tai = base_tai + extra_tai_for(opponent_pid)
        return base_points_int + total_tai * tai_points_int

    source = (ctx.win_source or "").upper()
    if source in ("TSUMO", "ZIMO"):
        for pid in range(n_players):
            if pid == winner:
                continue
            amount = payout_for(pid)
            payments[winner] += amount
            payments[pid] -= amount
    else:
        payer = getattr(ctx, "turn_at_win", None)
        if isinstance(payer, int) and 0 <= payer < n_players:
            amount = payout_for(payer)
            payments[winner] += amount
            payments[payer] -= amount

    return payments, breakdown


# local helper for only-chows DFS (copied from previous judge implementation)
from functools import lru_cache


def _is_suited_idx(i: int) -> bool:
    """Index helper: 0..26 are suited tiles (万/筒/条)."""
    return 0 <= i <= 26


def _same_suit_triplet_ok(i: int) -> bool:
    """Check if i,i+1,i+2 are consecutive in the same suit without crossing suit edges."""
    if not (_is_suited_idx(i) and _is_suited_idx(i + 1) and _is_suited_idx(i + 2)):
        return False
    if i in (8, 17, 26):
        return False
    if (i // 9) != ((i + 1) // 9) or (i // 9) != ((i + 2) // 9):
        return False
    return True


@lru_cache(maxsize=None)
def _dfs_only_chows(state: Tuple[int, ...], need: int, eye_used: bool) -> bool:
    """DFS that tries to consume only chows plus one pair across suited tiles.

    Args:
      state: Length‑34 counts.
      need: Number of melds to form.
      eye_used: Whether the pair is already picked.

    Returns:
      True if the state can be fully consumed under these constraints.
    """
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
