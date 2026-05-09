"""2D grid storing per-tile territory ownership and claim strength."""

from __future__ import annotations

from typing import Optional

import numpy as np


class TerritoryGrid:
    """Stores owner_clan_id and claim_strength for each tile.

    -1 means unowned. claim_strength is in [0, 1].
    """

    def __init__(self, width: int, height: int):
        self.width: int = width
        self.height: int = height
        self.owner: np.ndarray = np.full((width, height), -1, dtype=np.int32)
        self.strength: np.ndarray = np.zeros((width, height), dtype=np.float32)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def reinforce(self, x: int, y: int, clan_id: int, amount: float) -> None:
        if not self.in_bounds(x, y):
            return
        current_owner = int(self.owner[x, y])
        current_strength = float(self.strength[x, y])
        if current_owner == clan_id or current_owner == -1:
            self.owner[x, y] = clan_id
            self.strength[x, y] = min(1.0, current_strength + amount)
        else:
            new_strength = current_strength - amount
            if new_strength <= 0.0:
                self.owner[x, y] = clan_id
                self.strength[x, y] = min(1.0, -new_strength + amount * 0.5)
            else:
                self.strength[x, y] = new_strength

    def decay(self, decay_amount: float) -> None:
        if decay_amount <= 0.0:
            return
        # Operate only on tiles that actually have ownership. At large
        # world sizes most of the grid is untouched and a full-grid
        # numpy sweep dominates the tick budget.
        mask = self.owner != -1
        if not mask.any():
            return
        new_strength = self.strength[mask] - decay_amount
        cleared = new_strength <= 0.0
        new_strength[cleared] = 0.0
        self.strength[mask] = new_strength
        if cleared.any():
            owner_indices = np.flatnonzero(mask.ravel())
            cleared_indices = owner_indices[cleared]
            flat_owner = self.owner.ravel()
            flat_owner[cleared_indices] = -1

    def clan_owns(self, x: int, y: int) -> Optional[int]:
        if not self.in_bounds(x, y):
            return None
        owner = int(self.owner[x, y])
        return None if owner == -1 else owner

    def territory_count(self, clan_id: int) -> int:
        return int(np.count_nonzero(self.owner == clan_id))

    def territory_counts_by_clan(self) -> dict:
        """Return {clan_id: tile_count} via a single bincount pass."""
        flat = self.owner.ravel()
        if flat.size == 0:
            return {}
        # bincount needs non-negative ints; treat -1 as a separate bucket.
        valid_mask = flat >= 0
        if not valid_mask.any():
            return {}
        vals = flat[valid_mask]
        counts = np.bincount(vals)
        return {int(i): int(c) for i, c in enumerate(counts) if c > 0}
