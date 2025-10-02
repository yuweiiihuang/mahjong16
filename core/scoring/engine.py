from __future__ import annotations
from typing import Any, Dict, List, Tuple

from ..tiles import tile_to_str
from .state import DerivedScoringState, build_state
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

    state: DerivedScoringState = build_state(ctx)

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

    pl = state.player
    tsumo = state.win.tsumo
    melds = state.melds
    flowers = state.flowers
    has_flowers_total = state.has_flowers_total
    drawn = pl.drawn
    flower_win_type = state.flower_win_type

    if flower_win_type:
        if flower_win_type == "ba_xian":
            add("ba_xian")
        elif flower_win_type == "qi_qiang_yi":
            add("qi_qiang_yi")
        else:
            add(str(flower_win_type))
        rewards = [0] * ctx.rules.n_players
        total = sum(item.get("points", 0) for item in bd)
        rewards[winner] = total
        return rewards, breakdown_by_player

    # concealed tiles
    concealed_tiles = state.hand.concealed_tiles
    concealed_for_patterns = state.hand.concealed_for_patterns
    need = state.hand.need
    required_len = state.hand.required_len
    menqing = state.hand.menqing
    fixed_melds_pungs = state.hand.fixed_melds_pungs
    fixed_melds_chis = state.hand.fixed_melds_chis
    counts34 = state.hand.counts34
    counts34_concealed = state.hand.counts34_concealed
    ron_tile = state.win.ron_tile
    ron_tile_idx = state.win.ron_tile_idx

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

    if tsumo and ctx.wall_len == _dead_wall_reserved(ctx):
        add("hai_di")
    if (not tsumo) and ctx.wall_len == _dead_wall_reserved(ctx):
        add("he_di")

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
    tenpai_before_draw = state.win.tenpai_before_draw
    if bool(pl.declared_ting) or tenpai_before_draw:
        add("ting")

    # 獨聽：僅聽唯一一張牌（邊張/嵌張/單吊）。
    win_tile_id = state.win.win_tile_id
    counts16 = state.hand.counts16
    waits_for_du_set = state.win.waits_for_du_set
    if isinstance(win_tile_id, int) and waits_for_du_set:
        if len(waits_for_du_set) == 1 and win_tile_id in waits_for_du_set:
            add("du_ting")

    def _is_two_sided_ping_hu_wait(win_tile: int | None) -> bool:
        if not isinstance(win_tile, int):
            return False
        if win_tile < 0 or win_tile >= 34:
            return False
        if win_tile not in waits_for_du_set:
            return False
        if win_tile >= 27:
            return False

        for a in range(33):
            b = a + 1
            if b >= 34:
                break
            if counts16[a] <= 0 or counts16[b] <= 0:
                continue
            if (a // 9) != (b // 9):
                continue
            left = a - 1 if (a % 9) != 0 else None
            right = b + 1 if (b % 9) != 8 else None
            if left is None or right is None:
                continue
            if (left // 9) != (a // 9) or (right // 9) != (a // 9):
                continue
            if win_tile == left and right in waits_for_du_set:
                return True
            if win_tile == right and left in waits_for_du_set:
                return True
        return False

    # pattern-based
    all_tiles = state.all_tiles
    suits = set()
    for t in all_tiles:
        s = tile_to_str(t)
        if len(s) == 2:
            suits.add(s[1])
    has_honor_total = state.has_honor_total

    if all_tiles:
        if all(_is_honor(t) for t in all_tiles):
            add("zi_yi_se")
        elif len(suits) == 1:
            if has_honor_total:
                add("hun_yi_se")
            else:
                add("qing_yi_se")

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

    if (not tsumo):
        open_from_others = [m for m in melds if (m.type or "").upper() in ("CHI", "PONG", "GANG", "KAKAN") and m.from_pid is not None]
        concealed_melds = [m for m in melds if (m.type or "").upper() == "ANGANG"]
        if len(open_from_others) >= 5 and not concealed_melds and len(concealed_tiles) <= 1:
            add("quan_qiu_ren")

    # ping hu
    ping_hu_two_sided = _is_two_sided_ping_hu_wait(win_tile_id)

    if (
        fixed_melds_pungs == 0
        and fixed_melds_chis > 0
        and need >= 0
        and required_len is not None
        and ping_hu_two_sided
        and not tsumo  # 平胡僅限榮牌
    ):
        if len(concealed_for_patterns) == required_len and not has_flowers_total and not has_honor_total:
            if sum(counts34) == len(concealed_for_patterns):
                # DFS over only chows (reuse menqing-style helper not needed here)
                if _dfs_only_chows(tuple(counts34), need, False):
                    add("ping_hu")

    # 三暗刻 / 四暗刻 / 五暗刻
    concealed_triplets = 0
    if need >= 0 and required_len is not None and len(concealed_for_patterns) == required_len:
        max_triplets = _max_concealed_triplets(tuple(counts34), need, False)
        if ron_tile_idx is not None and max_triplets > 0:
            if (
                counts34[ron_tile_idx] >= 3
                and counts34_concealed[ron_tile_idx] < 3
                and counts34[ron_tile_idx] == counts34_concealed[ron_tile_idx] + 1
            ):
                max_triplets = max(max_triplets - 1, 0)
        if max_triplets > 0:
            concealed_triplets += max_triplets
        elif max_triplets == 0:
            concealed_triplets += 0
    concealed_triplets += sum(1 for m in melds if (m.type or "").upper() == "ANGANG")
    if concealed_triplets >= 5:
        add("wu_an_ke")
    elif concealed_triplets >= 4:
        add("si_an_ke")
    elif concealed_triplets >= 3:
        add("san_an_ke")

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

    is_xiao_san_yuan = False
    is_da_san_yuan = False
    if triplets == 2 and has_pair:
        add("xiao_san_yuan")
        is_xiao_san_yuan = True
    if triplets == 3:
        add("da_san_yuan")
        is_da_san_yuan = True
    if triplets > 0 and not (is_xiao_san_yuan or is_da_san_yuan):
        add("dragon_pung", count=triplets)

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
        unique_flowers = len(fset)
        if flower_win_type is None:
            if unique_flowers == 8:
                add("ba_xian")
            elif unique_flowers == 7:
                add("qi_qiang_yi")

    ting_declared_at = getattr(pl, "ting_declared_at", None)
    ting_open_melds = getattr(pl, "ting_declared_open_melds", None)
    if isinstance(ting_declared_at, int):
        if ting_declared_at <= 1:
            add("tian_ting")
        elif ting_declared_at <= 8 and int(ting_open_melds or 0) == 0:
            add("di_ting")

    win_src = state.win.win_source
    discards = max(0, int(getattr(ctx, "discard_count", 0) or 0))
    open_melds = max(0, int(getattr(ctx, "open_meld_count", 0) or 0))
    if win_src in ("TSUMO", "ZIMO") and discards == 0:
        add("tian_hu")
    elif discards == 1 and win_src in ("RON", "TSUMO", "ZIMO"):
        add("di_hu")
    elif (
        discards > 1
        and discards <= ctx.rules.n_players
        and open_melds == 0
    ):
        add("ren_hu")

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


@lru_cache(maxsize=None)
def _max_concealed_triplets(state: Tuple[int, ...], need: int, eye_used: bool) -> int:
    """Return the maximum concealed triplet count for a given state."""

    if need < 0:
        return -1
    if need == 0:
        total = sum(state)
        if total == 0 and eye_used:
            return 0
        if not eye_used and total == 2 and any(c == 2 for c in state):
            return 0
        return -1

    i = next((idx for idx, c in enumerate(state) if c > 0), -1)
    if i == -1:
        return -1

    best = -1

    if state[i] >= 3:
        lst = list(state)
        lst[i] -= 3
        res = _max_concealed_triplets(tuple(lst), need - 1, eye_used)
        if res >= 0:
            best = max(best, res + 1)

    if _same_suit_triplet_ok(i):
        i1, i2 = i + 1, i + 2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[i] -= 1
            lst[i1] -= 1
            lst[i2] -= 1
            res = _max_concealed_triplets(tuple(lst), need - 1, eye_used)
            if res >= 0:
                best = max(best, res)

    if not eye_used and state[i] >= 2:
        lst = list(state)
        lst[i] -= 2
        res = _max_concealed_triplets(tuple(lst), need, True)
        if res >= 0:
            best = max(best, res)

    return best
