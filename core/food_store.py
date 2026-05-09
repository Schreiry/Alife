"""SoA storage for food. Mirrors CreatureStore's design at a smaller scale."""

from __future__ import annotations

from typing import List

import numpy as np


class FoodStore:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.alive: np.ndarray = np.zeros(capacity, dtype=np.bool_)
        self.x: np.ndarray = np.zeros(capacity, dtype=np.float32)
        self.y: np.ndarray = np.zeros(capacity, dtype=np.float32)
        self.energy: np.ndarray = np.zeros(capacity, dtype=np.float32)
        self._free: List[int] = []
        self._next: int = 0
        self.count: int = 0

    def allocate(self, x: float, y: float, energy: float) -> int:
        if self._free:
            idx = self._free.pop()
        elif self._next < self.capacity:
            idx = self._next
            self._next += 1
        else:
            return -1
        self.alive[idx] = True
        self.x[idx] = x
        self.y[idx] = y
        self.energy[idx] = energy
        self.count += 1
        return idx

    def release(self, idx: int) -> None:
        if not self.alive[idx]:
            return
        self.alive[idx] = False
        self._free.append(idx)
        self.count -= 1

    def reset(self) -> None:
        self.alive.fill(False)
        self._free.clear()
        self._next = 0
        self.count = 0
