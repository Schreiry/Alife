"""Structure-of-Arrays storage for hot per-creature fields.

Every creature owns a stable `index` into these arrays. When a creature
dies, its slot is freed back to a free-list; arrays only ever grow
(bounded by capacity). This keeps neighbor lookups, mass updates and
spatial-grid rebuilds entirely vectorized.

A `Creature` object proxies its hot fields to this store via properties,
so business logic continues to read/write `creature.x`, `creature.energy`
etc. unchanged.
"""

from __future__ import annotations

from typing import List

import numpy as np


class CreatureStore:
    def __init__(self, capacity: int):
        self.capacity: int = capacity
        z32 = lambda: np.zeros(capacity, dtype=np.float32)
        zi32 = lambda: np.zeros(capacity, dtype=np.int32)
        zi8 = lambda: np.zeros(capacity, dtype=np.int8)
        zb = lambda: np.zeros(capacity, dtype=np.bool_)

        # Identity / lifecycle.
        self.alive: np.ndarray = zb()
        self.creature_id: np.ndarray = zi32()
        self.species_id: np.ndarray = zi32()
        self.clan_id: np.ndarray = np.full(capacity, -1, dtype=np.int32)
        self.sex: np.ndarray = zi8()
        self.is_hybrid: np.ndarray = zb()

        # Position / movement.
        self.x: np.ndarray = z32()
        self.y: np.ndarray = z32()

        # State.
        self.energy: np.ndarray = z32()
        self.health: np.ndarray = z32()
        self.age: np.ndarray = zi32()
        self.mating_cooldown: np.ndarray = zi32()

        # Cached derived stats (set at attach_phenotype).
        self.max_energy: np.ndarray = z32()
        self.max_health: np.ndarray = z32()
        self.vision_range: np.ndarray = z32()
        self.move_speed: np.ndarray = z32()
        self.attack_power: np.ndarray = z32()
        self.defense_power: np.ndarray = z32()
        self.base_energy_cost: np.ndarray = z32()
        self.move_energy_cost: np.ndarray = z32()
        self.attack_energy_cost: np.ndarray = z32()
        self.starvation_damage: np.ndarray = z32()
        self.regen_rate: np.ndarray = z32()
        self.lifespan: np.ndarray = zi32()
        self.aging_speed: np.ndarray = z32()

        self._free: List[int] = []
        self._next: int = 0
        self.count: int = 0

    # ---------- allocation ------------------------------------------------
    def allocate(self) -> int:
        if self._free:
            idx = self._free.pop()
        elif self._next < self.capacity:
            idx = self._next
            self._next += 1
        else:
            raise RuntimeError(
                f"CreatureStore capacity exceeded ({self.capacity})"
            )
        self.alive[idx] = True
        self.count += 1
        return idx

    def release(self, idx: int) -> None:
        if not self.alive[idx]:
            return
        self.alive[idx] = False
        self.clan_id[idx] = -1
        self._free.append(idx)
        self.count -= 1

    # ---------- mass updates --------------------------------------------
    def alive_indices(self) -> np.ndarray:
        return np.flatnonzero(self.alive)

    def has_capacity(self, extra: int = 1) -> bool:
        return (self.count + extra) <= self.capacity

    def reset(self) -> None:
        self.alive.fill(False)
        self.clan_id.fill(-1)
        self._free.clear()
        self._next = 0
        self.count = 0
