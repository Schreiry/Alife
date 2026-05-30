"""World: live container of all simulation state.

Hot per-creature data lives in CreatureStore (SoA, numpy arrays). The
Creature objects we hand out are thin proxies indexed into the store.
Foods sit in a FoodStore. Both are queried via numpy SpatialGrids that
get rebuilt at the start of each tick.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

import config
from core.creature_store import CreatureStore
from core.ecology import ResourceEcology
from core.food_store import FoodStore
from core.grid import TerritoryGrid
from core.spatial_grid import SpatialGrid
from entities.archetype import Archetype, amplify_traits, classify
from entities.clan import Clan
from entities.creature import Creature
from genetics.genome import Genome
from genetics.species import SpeciesRegistry
from rendering.colors import genome_to_color, mix_colors


class World:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.tick: int = 0

        self.store = CreatureStore(config.MAX_CREATURES)
        self.food_store = FoodStore(config.MAX_FOOD)

        # creature_id -> Creature (sparse). Indexed lookups for cold data.
        self.creatures: Dict[int, Creature] = {}
        # store_idx -> Creature (dense). Lets vectorized perception map
        # back to the cold object without a hash lookup.
        self.creature_by_idx: List[Optional[Creature]] = [None] * config.MAX_CREATURES

        self.clans: Dict[int, Clan] = {}
        self.species = SpeciesRegistry(distance_threshold=config.SPECIES_DISTANCE_THRESHOLD)

        self.territory = TerritoryGrid(config.WORLD_WIDTH, config.WORLD_HEIGHT)
        self.ecology = ResourceEcology(config.WORLD_WIDTH, config.WORLD_HEIGHT, rng)
        # Famine/bloom debounce flag — flipped by Simulation when the live
        # food supply crosses the famine/bloom thresholds.
        self.in_famine: bool = False
        self.creature_grid = SpatialGrid(
            config.WORLD_WIDTH, config.WORLD_HEIGHT, config.SPATIAL_HASH_CELL,
        )
        self.food_grid = SpatialGrid(
            config.WORLD_WIDTH, config.WORLD_HEIGHT, config.SPATIAL_HASH_CELL,
        )

        self._next_creature_id: int = 1
        self._next_clan_id: int = 1

        # Mean position of all living creatures, refreshed each tick in
        # rebuild_grids. Lonely reproduction-ready creatures steer toward it
        # when no mate is reachable, so a sparse population re-aggregates
        # instead of drifting apart into reproductive isolation.
        self.centroid_x: float = config.WORLD_WIDTH * 0.5
        self.centroid_y: float = config.WORLD_HEIGHT * 0.5

        # Cumulative stats — incremented from various subsystems.
        self.births_total: int = 0
        self.deaths_total: int = 0
        self.deaths_by_starvation: int = 0
        self.deaths_by_age: int = 0
        self.deaths_by_combat: int = 0
        self.hybrid_total: int = 0
        self.generation_max: int = 0

        # Render-side dirty flag — set by anything that mutates the
        # territory grid; cleared by the renderer after redraw.
        self.territory_dirty: bool = True

        # Per-tick gates flipped by Simulation._tick. Brain.step reads them
        # so we throttle the expensive intents without scattering modulo
        # checks across the action handlers.
        self.allow_reproduce_tick: bool = True
        self.allow_attack_tick: bool = True

        # Optional Werld-style observation sink. Set by Simulation. Any
        # subsystem (combat, reproduction, clan creation) can call
        # `world.emit(kind, payload)` without knowing whether telemetry
        # is wired or not.
        self.telemetry = None

        # Ring buffer of recent positioned "something happened HERE" markers
        # (war, new clan, new species, alliance). The live snapshot ships the
        # recent ones; the renderer fades them by age. View-only.
        self.signals: List[dict] = []

    def emit(self, kind: str, payload: dict | None = None) -> None:
        if self.telemetry is None:
            return
        self.telemetry.emit_event(self.tick, kind, payload)

    def push_signal(self, kind: str, x: float, y: float,
                    payload: dict | None = None) -> None:
        """Record a positioned event marker AND mirror it to telemetry.

        `payload` is merged into the telemetry event (with coords); the map
        signal itself only needs kind + position.
        """
        self.signals.append({
            "tick": self.tick, "kind": kind,
            "x": round(float(x), 1), "y": round(float(y), 1),
        })
        if len(self.signals) > config.SIGNAL_BUFFER_MAX:
            del self.signals[:-config.SIGNAL_BUFFER_MAX]
        ev = dict(payload or {})
        ev["x"] = round(float(x), 1)
        ev["y"] = round(float(y), 1)
        self.emit(kind, ev)

    # ---------- Creatures --------------------------------------------------
    def spawn_creature(
        self,
        genome: Genome,
        x: float,
        y: float,
        sex: int,
        parent_a_id: Optional[int] = None,
        parent_b_id: Optional[int] = None,
        generation: int = 0,
        clan_id: Optional[int] = None,
        is_hybrid: bool = False,
        parent_species_id: Optional[int] = None,
        energy_fraction: float = config.START_ENERGY_FRACTION,
        health_fraction: float = config.START_HEALTH_FRACTION,
    ) -> Optional[Creature]:
        if not self.store.has_capacity(1):
            return None

        idx = self.store.allocate()
        cid = self._next_creature_id
        self._next_creature_id += 1

        store = self.store
        store.creature_id[idx] = cid
        store.x[idx] = x
        store.y[idx] = y
        store.sex[idx] = sex
        store.is_hybrid[idx] = is_hybrid
        store.clan_id[idx] = -1 if clan_id is None else clan_id
        store.age[idx] = 0
        store.mating_cooldown[idx] = 0

        creature = Creature(store, idx, cid, genome)
        creature.parent_a_id = parent_a_id
        creature.parent_b_id = parent_b_id
        creature.generation = generation
        creature.attach_phenotype(rng=self.rng)
        archetype = classify(genome, is_hybrid=is_hybrid)
        creature.archetype = archetype.value
        amplify_traits(creature, archetype)
        creature.color = genome_to_color(genome)

        store.energy[idx] = store.max_energy[idx] * energy_fraction
        store.health[idx] = store.max_health[idx] * health_fraction

        # Offspring inherit their parent species directly; new species arise
        # only through cladogenesis (SpeciesRegistry.detect_splits), never by
        # re-clustering newborns. Parentless creatures (world seed, immigration
        # reseed) go through founder assignment.
        if parent_species_id is not None and parent_species_id in self.species.species:
            species_id = parent_species_id
            self.species.register_member(species_id)
        else:
            species_id = self.species.assign(genome, cid, self.tick, creature.color)
        store.species_id[idx] = species_id

        if clan_id is not None and clan_id in self.clans:
            self.clans[clan_id].add_member(cid)

        self.creatures[cid] = creature
        self.creature_by_idx[idx] = creature

        if generation > self.generation_max:
            self.generation_max = generation
        if is_hybrid:
            self.hybrid_total += 1
        return creature

    def remove_creature(self, cid: int) -> None:
        creature = self.creatures.pop(cid, None)
        if creature is None:
            return
        idx = creature.store_idx
        clan_id_value = creature.clan_id
        if clan_id_value is not None:
            clan = self.clans.get(clan_id_value)
            if clan is not None:
                clan.remove_member(cid)
                if not clan.alive:
                    self.clans.pop(clan.id, None)
                    self.emit("clan_dissolved", {"id": clan.id})
        self.species.remove_member(int(self.store.species_id[idx]))
        self.creature_by_idx[idx] = None
        self.store.release(idx)

    # ---------- Food -------------------------------------------------------
    def spawn_food(self, x: float, y: float, energy: float = config.FOOD_ENERGY) -> int:
        return self.food_store.allocate(x, y, energy)

    def remove_food(self, idx: int) -> None:
        self.food_store.release(idx)

    # ---------- Clans ------------------------------------------------------
    def create_clan(self, founder: Creature) -> Clan:
        clan_id = self._next_clan_id
        self._next_clan_id += 1
        founder_color = founder.color
        affinity = founder.genome.normalized("clan_color_affinity")
        accent = (
            int(255 * affinity),
            int(255 * (1.0 - affinity)),
            int(255 * (0.5 + 0.5 * affinity)),
        )
        color = mix_colors(founder_color, accent, 0.4)
        clan = Clan(
            id=clan_id,
            name=f"clan_{clan_id:03d}",
            leader_id=founder.id,
            color=color,
            created_tick=self.tick,
        )
        clan.add_member(founder.id)
        founder.clan_id = clan_id
        clan.aggression_level = 0.3 + 0.7 * founder.aggression
        clan.ideology = founder.aggression
        self.clans[clan_id] = clan
        # A new clan is "something new" born at the founder's location — give
        # it a positioned signal so the map can mark it.
        self.push_signal("clan_created", founder.x, founder.y, {
            "id": clan_id, "name": clan.name, "founder": founder.id,
            "aggression": round(clan.aggression_level, 3),
        })
        return clan

    def join_clan(self, creature: Creature, clan: Clan) -> None:
        old_clan_id = creature.clan_id
        if old_clan_id is not None and old_clan_id != clan.id:
            old = self.clans.get(old_clan_id)
            if old is not None:
                old.remove_member(creature.id)
                if not old.alive:
                    self.clans.pop(old.id, None)
        creature.clan_id = clan.id
        clan.add_member(creature.id)

    # ---------- Per-tick rebuild ------------------------------------------
    def rebuild_grids(self) -> None:
        self.creature_grid.rebuild(self.store.x, self.store.y, self.store.alive)
        self.food_grid.rebuild(
            self.food_store.x, self.food_store.y, self.food_store.alive,
        )
        alive = self.store.alive
        if alive.any():
            self.centroid_x = float(self.store.x[alive].mean())
            self.centroid_y = float(self.store.y[alive].mean())

    # ---------- Queries ----------------------------------------------------
    def population(self) -> int:
        return self.store.count

    def food_count(self) -> int:
        return self.food_store.count

    def alive_creatures(self) -> List[Creature]:
        return list(self.creatures.values())

    def get_creature(self, cid: int) -> Optional[Creature]:
        return self.creatures.get(cid)

    def alive_creature_indices(self) -> np.ndarray:
        return self.store.alive_indices()
