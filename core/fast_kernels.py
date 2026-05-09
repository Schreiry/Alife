"""Numba-compiled hot kernels.

The dominant cost at large populations is per-creature neighbor
inspection — a tight loop where each iteration is a handful of float
multiplications. Numba compiles this loop to native code, removing the
~1 µs/op overhead that pure NumPy would pay for arrays this small.

If Numba is unavailable, a pure-NumPy fallback is provided that produces
identical results (slower, but the simulation never stops working).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


try:
    from numba import njit  # type: ignore
    NUMBA_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback path
    NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):  # type: ignore
        # Decorator that returns the original function untouched.
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        def wrapper(fn):
            return fn

        return wrapper


# --- Perception kernel --------------------------------------------------
# Returns a fixed-size 1-D float64 array; numba-friendly tuple alternative.
# Layout: see _PERC_* indices below.

PERC_FOOD_IDX        = 0
PERC_FOOD_D2         = 1
PERC_FOOD_COUNT      = 2
PERC_MATE_IDX        = 3
PERC_MATE_D2         = 4
PERC_ENEMY_IDX       = 5
PERC_ENEMY_D2        = 6
PERC_ENEMY_COUNT     = 7
PERC_DANGER          = 8
PERC_ALLY_IDX        = 9
PERC_ALLY_D2         = 10
PERC_ALLY_COUNT      = 11
PERC_TOTAL_NEIGHBORS = 12
PERC_LEN = 13


@njit(cache=True, fastmath=True)
def perceive_kernel(
    cx: float, cy: float, vr: float, vr2: float,
    own_idx: int,
    own_clan_id: int, own_sex: int, own_mating_cooldown: int,
    aggressive_no_clan: int,
    hostile_clans: np.ndarray,
    # creature arrays
    cre_x: np.ndarray, cre_y: np.ndarray,
    cre_clan: np.ndarray, cre_sex: np.ndarray,
    cre_cooldown: np.ndarray, cre_age: np.ndarray,
    cre_attack: np.ndarray,
    # creature grid
    cre_offsets: np.ndarray, cre_sorted: np.ndarray,
    cre_cells_x: int, cre_cells_y: int, cre_cell_size: int,
    # food arrays
    food_x: np.ndarray, food_y: np.ndarray,
    # food grid
    food_offsets: np.ndarray, food_sorted: np.ndarray,
    food_cells_x: int, food_cells_y: int, food_cell_size: int,
) -> np.ndarray:
    out = np.zeros(PERC_LEN, dtype=np.float64)
    out[PERC_FOOD_IDX] = -1.0
    out[PERC_FOOD_D2] = 1e30
    out[PERC_MATE_IDX] = -1.0
    out[PERC_MATE_D2] = 1e30
    out[PERC_ENEMY_IDX] = -1.0
    out[PERC_ENEMY_D2] = 1e30
    out[PERC_ALLY_IDX] = -1.0
    out[PERC_ALLY_D2] = 1e30

    # ---- food ----------------------------------------------------------
    cs = food_cell_size
    span = int(vr / cs) + 1
    fcx = int(cx) // cs
    fcy = int(cy) // cs
    x0 = fcx - span
    if x0 < 0: x0 = 0
    x1 = fcx + span
    if x1 > food_cells_x - 1: x1 = food_cells_x - 1
    y0 = fcy - span
    if y0 < 0: y0 = 0
    y1 = fcy + span
    if y1 > food_cells_y - 1: y1 = food_cells_y - 1

    if x1 >= x0 and y1 >= y0:
        for yy in range(y0, y1 + 1):
            row_start = yy * food_cells_x + x0
            row_end = yy * food_cells_x + x1
            s = food_offsets[row_start]
            e = food_offsets[row_end + 1]
            for k in range(s, e):
                fidx = food_sorted[k]
                dx = food_x[fidx] - cx
                dy = food_y[fidx] - cy
                d2 = dx * dx + dy * dy
                if d2 <= vr2:
                    out[PERC_FOOD_COUNT] += 1.0
                    if d2 < out[PERC_FOOD_D2]:
                        out[PERC_FOOD_D2] = d2
                        out[PERC_FOOD_IDX] = fidx

    # ---- creatures -----------------------------------------------------
    cs = cre_cell_size
    span = int(vr / cs) + 1
    ccx = int(cx) // cs
    ccy = int(cy) // cs
    x0 = ccx - span
    if x0 < 0: x0 = 0
    x1 = ccx + span
    if x1 > cre_cells_x - 1: x1 = cre_cells_x - 1
    y0 = ccy - span
    if y0 < 0: y0 = 0
    y1 = ccy + span
    if y1 > cre_cells_y - 1: y1 = cre_cells_y - 1

    n_hostile = hostile_clans.shape[0]
    has_clan = own_clan_id >= 0
    own_on_cooldown = own_mating_cooldown > 0

    if x1 >= x0 and y1 >= y0:
        for yy in range(y0, y1 + 1):
            row_start = yy * cre_cells_x + x0
            row_end = yy * cre_cells_x + x1
            s = cre_offsets[row_start]
            e = cre_offsets[row_end + 1]
            for k in range(s, e):
                idx = cre_sorted[k]
                if idx == own_idx:
                    continue
                dx = cre_x[idx] - cx
                dy = cre_y[idx] - cy
                d2 = dx * dx + dy * dy
                if d2 > vr2:
                    continue
                out[PERC_TOTAL_NEIGHBORS] += 1.0

                other_clan = cre_clan[idx]
                is_enemy = False
                if has_clan:
                    if other_clan >= 0 and other_clan != own_clan_id:
                        for h in range(n_hostile):
                            if hostile_clans[h] == other_clan:
                                is_enemy = True
                                break
                else:
                    if aggressive_no_clan == 1 and other_clan >= 0:
                        is_enemy = True

                if is_enemy:
                    out[PERC_ENEMY_COUNT] += 1.0
                    d = d2 ** 0.5
                    out[PERC_DANGER] += cre_attack[idx] / (d + 1.0)
                    if d2 < out[PERC_ENEMY_D2]:
                        out[PERC_ENEMY_D2] = d2
                        out[PERC_ENEMY_IDX] = idx
                    continue

                if has_clan and other_clan == own_clan_id:
                    out[PERC_ALLY_COUNT] += 1.0
                    if d2 < out[PERC_ALLY_D2]:
                        out[PERC_ALLY_D2] = d2
                        out[PERC_ALLY_IDX] = idx
                    continue

                if (
                    cre_sex[idx] != own_sex
                    and cre_cooldown[idx] <= 0
                    and not own_on_cooldown
                    and cre_age[idx] >= 40
                ):
                    if d2 < out[PERC_MATE_D2]:
                        out[PERC_MATE_D2] = d2
                        out[PERC_MATE_IDX] = idx

    return out
