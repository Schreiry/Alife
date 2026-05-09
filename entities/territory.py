"""Territory façade over the TerritoryGrid.

Wraps grid operations with high-level helpers used by the simulation.
"""

from __future__ import annotations

from typing import Optional

from core.grid import TerritoryGrid


class TerritoryManager:
    def __init__(self, grid: TerritoryGrid):
        self.grid = grid

    def reinforce_for_creature(
        self,
        clan_id: Optional[int],
        x: float,
        y: float,
        amount: float,
    ) -> None:
        if clan_id is None:
            return
        self.grid.reinforce(int(x), int(y), clan_id, amount)

    def owner_at(self, x: float, y: float) -> Optional[int]:
        return self.grid.clan_owns(int(x), int(y))

    def step_decay(self, decay: float) -> None:
        self.grid.decay(decay)
