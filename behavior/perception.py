"""Perception driven by the Numba (or NumPy fallback) kernel.

The hot inner loop — neighbor inspection — runs in compiled code; this
file is the thin Python adapter that prepares its inputs and unpacks
its outputs into a Perception dataclass that the rest of the brain
can read normally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from core.fast_kernels import (
    PERC_ALLY_COUNT, PERC_ALLY_D2, PERC_ALLY_IDX,
    PERC_DANGER, PERC_ENEMY_COUNT, PERC_ENEMY_D2, PERC_ENEMY_IDX,
    PERC_FOOD_COUNT, PERC_FOOD_D2, PERC_FOOD_IDX,
    PERC_MATE_D2, PERC_MATE_IDX, PERC_TOTAL_NEIGHBORS,
    perceive_kernel,
)
from entities.creature import Creature


@dataclass
class Perception:
    closest_food_idx: int = -1
    closest_food_dist: float = float("inf")
    nearby_food_count: int = 0

    closest_mate: Optional[Creature] = None
    closest_mate_dist: float = float("inf")
    closest_enemy: Optional[Creature] = None
    closest_enemy_dist: float = float("inf")
    closest_ally: Optional[Creature] = None
    closest_ally_dist: float = float("inf")

    nearby_creatures: int = 0
    nearby_enemies: int = 0
    nearby_allies: int = 0
    local_danger: float = 0.0
    # Resource-ecology sensor reads of the creature's current cell.
    local_food: float = 1.0          # current biomass / capacity, [0,1]
    resource_depletion: float = 0.0  # over-grazing memory, [0,1]
    own_tile_owner: Optional[int] = None
    is_on_own_clan_tile: bool = False
    is_on_enemy_clan_tile: bool = False


_EMPTY_HOSTILE = np.zeros(0, dtype=np.int32)
_HOSTILE_CACHE: Dict[int, np.ndarray] = {}
_HOSTILE_CACHE_TICK: int = -1


def reset_hostile_cache() -> None:
    """Call when diplomacy changes."""
    global _HOSTILE_CACHE_TICK
    _HOSTILE_CACHE.clear()
    _HOSTILE_CACHE_TICK = -1


def _hostile_clans_for(world, clan_id: int) -> np.ndarray:
    cached = _HOSTILE_CACHE.get(clan_id)
    if cached is not None:
        return cached
    clan = world.clans.get(clan_id)
    if clan is None:
        _HOSTILE_CACHE[clan_id] = _EMPTY_HOSTILE
        return _EMPTY_HOSTILE
    hostile = [int(o) for o, rel in clan.relations.items() if rel < -0.3]
    arr = np.asarray(hostile, dtype=np.int32) if hostile else _EMPTY_HOSTILE
    _HOSTILE_CACHE[clan_id] = arr
    return arr


def perceive(creature: Creature, world) -> Perception:
    global _HOSTILE_CACHE_TICK
    # Bust the hostile-clans cache once per tick (cheap; clans rarely shift
    # within a single tick, but combat does adjust relations).
    if _HOSTILE_CACHE_TICK != world.tick:
        _HOSTILE_CACHE.clear()
        _HOSTILE_CACHE_TICK = world.tick

    p = Perception()
    store = world.store
    fstore = world.food_store
    idx = creature.store_idx
    cx = float(store.x[idx])
    cy = float(store.y[idx])
    vr = float(store.vision_range[idx])
    vr2 = vr * vr

    own_clan = creature.clan_id
    own_clan_id = -1 if own_clan is None else int(own_clan)
    aggressive_no_clan = (
        1
        if (own_clan_id < 0
            and creature.outsider_tolerance < 0.25
            and creature.aggression > 0.6)
        else 0
    )
    hostile_clans = (
        _hostile_clans_for(world, own_clan_id)
        if own_clan_id >= 0
        else _EMPTY_HOSTILE
    )

    cgrid = world.creature_grid
    fgrid = world.food_grid

    out = perceive_kernel(
        cx, cy, vr, vr2,
        idx,
        own_clan_id, int(creature.sex), int(store.mating_cooldown[idx]),
        aggressive_no_clan,
        hostile_clans,
        store.x, store.y,
        store.clan_id, store.sex,
        store.mating_cooldown, store.age,
        store.attack_power,
        cgrid.cell_offsets, cgrid.sorted_indices,
        cgrid.cells_x, cgrid.cells_y, cgrid.cell_size,
        fstore.x, fstore.y,
        fgrid.cell_offsets, fgrid.sorted_indices,
        fgrid.cells_x, fgrid.cells_y, fgrid.cell_size,
    )

    food_idx = int(out[PERC_FOOD_IDX])
    if food_idx >= 0:
        p.closest_food_idx = food_idx
        p.closest_food_dist = float(np.sqrt(out[PERC_FOOD_D2]))
        p.nearby_food_count = int(out[PERC_FOOD_COUNT])

    p.nearby_creatures = int(out[PERC_TOTAL_NEIGHBORS])

    enemy_idx = int(out[PERC_ENEMY_IDX])
    if enemy_idx >= 0:
        p.closest_enemy = world.creature_by_idx[enemy_idx]
        p.closest_enemy_dist = float(np.sqrt(out[PERC_ENEMY_D2]))
        p.nearby_enemies = int(out[PERC_ENEMY_COUNT])
        p.local_danger = float(out[PERC_DANGER])

    ally_idx = int(out[PERC_ALLY_IDX])
    if ally_idx >= 0:
        p.closest_ally = world.creature_by_idx[ally_idx]
        p.closest_ally_dist = float(np.sqrt(out[PERC_ALLY_D2]))
        p.nearby_allies = int(out[PERC_ALLY_COUNT])

    mate_idx = int(out[PERC_MATE_IDX])
    if mate_idx >= 0:
        p.closest_mate = world.creature_by_idx[mate_idx]
        p.closest_mate_dist = float(np.sqrt(out[PERC_MATE_D2]))

    # Resource-ecology sensor: single coarse-cell lookup, like territory.
    p.local_food, p.resource_depletion = world.ecology.sample(cx, cy)

    # Tile ownership stays a Python check — it's a single array index.
    owner = world.territory.clan_owns(int(cx), int(cy))
    p.own_tile_owner = owner
    if owner is not None:
        if owner == own_clan:
            p.is_on_own_clan_tile = True
        else:
            p.is_on_enemy_clan_tile = True
    return p
