"""Species registry: groups creatures by genome similarity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .genome import Genome


@dataclass
class Species:
    id: int
    name: str
    base_color: tuple
    founder_id: int
    created_tick: int
    signature: np.ndarray  # mean genome values for fast distance check
    population_count: int = 0


class SpeciesRegistry:
    def __init__(self, distance_threshold: float = 0.45):
        self.distance_threshold = distance_threshold
        self.species: Dict[int, Species] = {}
        self._next_id: int = 1

    def assign(
        self,
        genome: Genome,
        creature_id: int,
        tick: int,
        base_color: tuple,
    ) -> int:
        best_id: Optional[int] = None
        best_dist: float = self.distance_threshold
        for sp in self.species.values():
            d = float(np.mean(np.abs(genome.values - sp.signature)))
            if d < best_dist:
                best_dist = d
                best_id = sp.id

        if best_id is not None:
            self.species[best_id].population_count += 1
            return best_id

        new_id = self._next_id
        self._next_id += 1
        self.species[new_id] = Species(
            id=new_id,
            name=f"sp_{new_id:04d}",
            base_color=base_color,
            founder_id=creature_id,
            created_tick=tick,
            signature=genome.values.copy(),
            population_count=1,
        )
        return new_id

    def remove_member(self, species_id: int) -> None:
        sp = self.species.get(species_id)
        if sp is None:
            return
        sp.population_count = max(0, sp.population_count - 1)

    def update_signatures(self, genomes_by_species: Dict[int, List[Genome]]) -> None:
        """Recompute species signatures by averaging current member genomes."""
        for sp_id, genomes in genomes_by_species.items():
            sp = self.species.get(sp_id)
            if sp is None or not genomes:
                continue
            stacked = np.stack([g.values for g in genomes])
            sp.signature = stacked.mean(axis=0).astype(np.float32)

    def alive_species(self) -> List[Species]:
        return [s for s in self.species.values() if s.population_count > 0]
