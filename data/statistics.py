"""Per-tick statistics aggregator.

Cheap counters (population, food, totals) update every tick; expensive
averages over the whole population update every `_AVG_PERIOD` ticks so
the simulation stays responsive at large populations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List


_AVG_PERIOD: int = 10


@dataclass
class Statistics:
    tick: int = 0
    population: int = 0
    food: int = 0

    births_total: int = 0
    deaths_total: int = 0
    deaths_by_starvation: int = 0
    deaths_by_age: int = 0
    deaths_by_combat: int = 0
    hybrid_total: int = 0
    generation_max: int = 0

    species_count: int = 0
    clan_count: int = 0

    avg_energy: float = 0.0
    avg_health: float = 0.0
    avg_strength: float = 0.0
    avg_intelligence: float = 0.0
    avg_aggression: float = 0.0
    avg_age: float = 0.0

    history: List[Dict[str, float]] = field(default_factory=list)

    def reset(self) -> None:
        self.__dict__.update(Statistics().__dict__)

    def update_cheap(self, world) -> None:
        """O(1) counter refresh — call every tick if you want live counts."""
        self.tick = world.tick
        self.population = world.population()
        self.food = world.food_count()
        self.births_total = world.births_total
        self.deaths_total = world.deaths_total
        self.deaths_by_starvation = world.deaths_by_starvation
        self.deaths_by_age = world.deaths_by_age
        self.deaths_by_combat = world.deaths_by_combat
        self.hybrid_total = world.hybrid_total
        self.generation_max = world.generation_max
        self.clan_count = len(world.clans)

    def update(self, world) -> None:
        """Full refresh including O(N) averages — call on STATISTICS_INTERVAL."""
        self.update_cheap(world)
        self.species_count = sum(
            1 for s in world.species.species.values() if s.population_count > 0
        )
        self._refresh_averages_vectorized(world)
        self.history.append(
            {
                "tick": self.tick,
                "population": self.population,
                "food": self.food,
                "species": self.species_count,
                "clans": self.clan_count,
                "avg_energy": self.avg_energy,
                "avg_health": self.avg_health,
                "avg_aggression": self.avg_aggression,
                "avg_intelligence": self.avg_intelligence,
            }
        )
        if len(self.history) > 4000:
            self.history = self.history[-4000:]

    def _refresh_averages_vectorized(self, world) -> None:
        s = world.store
        mask = s.alive
        n = int(mask.sum())
        if n == 0:
            self.avg_energy = 0.0
            self.avg_health = 0.0
            self.avg_strength = 0.0
            self.avg_intelligence = 0.0
            self.avg_aggression = 0.0
            self.avg_age = 0.0
            return
        import numpy as np
        self.avg_energy = float(s.energy[mask].mean())
        self.avg_health = float(s.health[mask].mean())
        self.avg_strength = float(s.attack_power[mask].mean())
        self.avg_age = float(s.age[mask].mean())
        # Aggression / intelligence aren't in the SoA store (cold attrs);
        # average them from creature objects — still cheap at N=3000.
        if world.creatures:
            agg = 0.0
            intel = 0.0
            for c in world.creatures.values():
                agg += c.aggression
                intel += c.intelligence
            inv = 1.0 / len(world.creatures)
            self.avg_aggression = agg * inv
            self.avg_intelligence = intel * inv
        else:
            self.avg_aggression = 0.0
            self.avg_intelligence = 0.0

    def export_json(self, path: str) -> None:
        payload = {
            "tick": self.tick,
            "totals": {
                "births": self.births_total,
                "deaths": self.deaths_total,
                "starvation": self.deaths_by_starvation,
                "age": self.deaths_by_age,
                "combat": self.deaths_by_combat,
                "hybrids": self.hybrid_total,
                "generation_max": self.generation_max,
            },
            "snapshot": {
                "population": self.population,
                "food": self.food,
                "species": self.species_count,
                "clans": self.clan_count,
                "avg_energy": self.avg_energy,
                "avg_health": self.avg_health,
                "avg_strength": self.avg_strength,
                "avg_intelligence": self.avg_intelligence,
                "avg_aggression": self.avg_aggression,
                "avg_age": self.avg_age,
            },
            "history": self.history,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
