"""ResourceEcology — food as the fruit of a fertility field, not an infinite
uniform spawner.

The world is divided into a coarse grid of cells (ECOLOGY_ZONE tiles each).
Every cell carries:

  fertility  — static intrinsic richness in [FLOOR, 1], a smoothed noise field
               so rich/poor regions are contiguous "biomes", not white noise.
  capacity   — fertility * ECOLOGY_ZONE_CAPACITY, the max standing biomass.
  current    — regenerating biomass (energy units); food points are drawn from
               it, so a cell that spawns a lot of food runs dry.
  depletion  — [0,1] over-grazing memory: rises with creature density, decays
               when the cell is left alone, and suppresses regrowth while high.

`step` (vectorized over the whole grid) advances grazing/depletion/regrowth.
`spawn_food` places discrete food points (still consumed by the unchanged
perception/eat path) into cells in proportion to their `current`, charging each
point's energy against that cell's biomass. `sample` is the per-creature sensor
read (local food ratio + depletion) used by perception.

This is a pure L2 "adaptive field": it changes slower than creatures act and
creates the slope the neutral system rolls down (scarcity -> migration ->
contested fertile zones).
"""

from __future__ import annotations

import numpy as np

import config


class ResourceEcology:
    def __init__(self, width: int, height: int, rng: np.random.Generator):
        self.width = int(width)
        self.height = int(height)
        self.zone = int(config.ECOLOGY_ZONE)
        self.cols = (self.width + self.zone - 1) // self.zone
        self.rows = (self.height + self.zone - 1) // self.zone

        # Smoothed-noise fertility field -> contiguous biomes.
        f = rng.random((self.cols, self.rows)).astype(np.float32)
        f = self._smooth(f, passes=3)
        lo, hi = float(f.min()), float(f.max())
        f = (f - lo) / (hi - lo + 1e-6)
        floor = config.ECOLOGY_FERTILITY_FLOOR
        self.fertility = (floor + (1.0 - floor) * f).astype(np.float32)

        self.capacity = (self.fertility * config.ECOLOGY_ZONE_CAPACITY).astype(np.float32)
        self.current = self.capacity.copy()            # start full
        self.depletion = np.zeros((self.cols, self.rows), dtype=np.float32)

    # ---------- field dynamics -------------------------------------------
    @staticmethod
    def _smooth(a: np.ndarray, passes: int = 2) -> np.ndarray:
        for _ in range(passes):
            a = (a
                 + np.roll(a, 1, 0) + np.roll(a, -1, 0)
                 + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
        return a

    def step(self, store) -> None:
        """Advance grazing pressure, depletion and regrowth one ecology tick.
        Fully vectorized over the (cols, rows) grid."""
        # Grazing pressure = live-creature density per cell.
        pressure = np.zeros((self.cols, self.rows), dtype=np.float32)
        idx = np.flatnonzero(store.alive)
        if idx.size:
            zx = np.clip((store.x[idx] / self.zone).astype(np.intp), 0, self.cols - 1)
            zy = np.clip((store.y[idx] / self.zone).astype(np.intp), 0, self.rows - 1)
            np.add.at(pressure, (zx, zy), 1.0)

        # Depletion: accumulate from grazing, then decay toward 0. Clipped.
        self.depletion += config.ECOLOGY_DEPLETION_PER_CREATURE * pressure
        self.depletion *= config.ECOLOGY_DEPLETION_DECAY
        np.clip(self.depletion, 0.0, 1.0, out=self.depletion)

        # Logistic-ish regrowth, scaled by fertility and suppressed by depletion.
        regen = (config.ECOLOGY_REGEN_RATE * self.fertility
                 * (1.0 - self.depletion) * (self.capacity - self.current))
        self.current += regen
        np.clip(self.current, 0.0, self.capacity, out=self.current)

    # ---------- food production ------------------------------------------
    def spawn_food(self, world, budget: int, rng: np.random.Generator) -> int:
        """Spawn up to `budget` food points (also bounded by MAX_FOOD), placing
        them in cells in proportion to current biomass and charging each point's
        energy against the cell it lands in. Returns the number spawned."""
        room = config.MAX_FOOD - world.food_count()
        n = int(min(budget, room))
        if n <= 0:
            return 0
        weights = self.current.ravel()                 # C-order: idx = zx*rows + zy
        total = float(weights.sum())
        if total <= 0.0:
            return 0
        counts = rng.multinomial(n, weights / total)
        food_energy = config.FOOD_ENERGY
        spawned = 0
        for z in np.flatnonzero(counts):
            zx, zy = divmod(int(z), self.rows)
            for _ in range(int(counts[z])):
                if self.current[zx, zy] < food_energy:
                    break
                x = min(self.width - 1.0, (zx + rng.random()) * self.zone)
                y = min(self.height - 1.0, (zy + rng.random()) * self.zone)
                if world.spawn_food(float(x), float(y)) >= 0:
                    self.current[zx, zy] -= food_energy
                    spawned += 1
        return spawned

    # ---------- sensor / observation reads -------------------------------
    def sample(self, x: float, y: float) -> tuple:
        """(local_food_ratio in [0,1], depletion in [0,1]) at a world point.
        Cheap single-cell lookup for the per-creature brain sensor."""
        zx = min(self.cols - 1, max(0, int(x) // self.zone))
        zy = min(self.rows - 1, max(0, int(y) // self.zone))
        cap = float(self.capacity[zx, zy])
        food_ratio = float(self.current[zx, zy]) / cap if cap > 1e-6 else 0.0
        return food_ratio, float(self.depletion[zx, zy])

    def total_biomass(self) -> float:
        return float(self.current.sum())

    def mean_depletion(self) -> float:
        return float(self.depletion.mean())
