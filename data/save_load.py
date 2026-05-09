"""Save / load the simulation state to a JSON file.

The full grid is intentionally not persisted (it's regenerated from
ownership counts, which would inflate the file). Stats history and the
genome arrays of each living creature are preserved.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import numpy as np

import config
from core.world import World
from entities.clan import Clan
from genetics.genome import Genome


def save(world: World, stats, path: str = config.SAVE_PATH) -> None:
    payload: Dict[str, Any] = {
        "tick": world.tick,
        "creatures": [],
        "clans": [],
        "stats": {
            "births_total": world.births_total,
            "deaths_total": world.deaths_total,
            "deaths_by_starvation": world.deaths_by_starvation,
            "deaths_by_age": world.deaths_by_age,
            "deaths_by_combat": world.deaths_by_combat,
            "hybrid_total": world.hybrid_total,
            "generation_max": world.generation_max,
        },
    }

    for c in world.creatures.values():
        payload["creatures"].append({
            "id": c.id,
            "x": float(c.x),
            "y": float(c.y),
            "sex": int(c.sex),
            "species_id": int(c.species_id),
            "clan_id": c.clan_id,
            "parent_a_id": c.parent_a_id,
            "parent_b_id": c.parent_b_id,
            "generation": int(c.generation),
            "age": int(c.age),
            "energy": float(c.energy),
            "health": float(c.health),
            "is_hybrid": bool(c.is_hybrid),
            "genome": c.genome.values.tolist(),
        })

    for clan in world.clans.values():
        payload["clans"].append({
            "id": clan.id,
            "name": clan.name,
            "leader_id": clan.leader_id,
            "color": list(clan.color),
            "created_tick": clan.created_tick,
            "members": list(clan.members),
            "relations": clan.relations,
            "aggression_level": clan.aggression_level,
            "ideology": clan.ideology,
            "stability": clan.stability,
        })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def load(simulation, path: str = config.SAVE_PATH) -> bool:
    """Replace the simulation state with the contents of `path`. Returns success."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False

    world = World(simulation.rng)
    world.tick = int(payload.get("tick", 0))
    world.births_total = int(payload.get("stats", {}).get("births_total", 0))
    world.deaths_total = int(payload.get("stats", {}).get("deaths_total", 0))
    world.deaths_by_starvation = int(payload.get("stats", {}).get("deaths_by_starvation", 0))
    world.deaths_by_age = int(payload.get("stats", {}).get("deaths_by_age", 0))
    world.deaths_by_combat = int(payload.get("stats", {}).get("deaths_by_combat", 0))
    world.hybrid_total = int(payload.get("stats", {}).get("hybrid_total", 0))
    world.generation_max = int(payload.get("stats", {}).get("generation_max", 0))

    # Recreate clans first so creatures can attach to them.
    for clan_data in payload.get("clans", []):
        clan = Clan(
            id=int(clan_data["id"]),
            name=clan_data.get("name", f"clan_{clan_data['id']}"),
            leader_id=int(clan_data["leader_id"]),
            color=tuple(clan_data.get("color", (180, 180, 180))),
            created_tick=int(clan_data.get("created_tick", 0)),
        )
        clan.aggression_level = float(clan_data.get("aggression_level", 0.5))
        clan.ideology = float(clan_data.get("ideology", 0.5))
        clan.stability = float(clan_data.get("stability", 1.0))
        clan.relations = {int(k): float(v) for k, v in clan_data.get("relations", {}).items()}
        world.clans[clan.id] = clan
        world._next_clan_id = max(world._next_clan_id, clan.id + 1)

    for c_data in payload.get("creatures", []):
        values = np.asarray(c_data["genome"], dtype=np.float32)
        # If the saved genome was shorter (older catalog), pad with random.
        from genetics.genes import GENE_COUNT
        if values.shape[0] < GENE_COUNT:
            extra = np.random.random(GENE_COUNT - values.shape[0]).astype(np.float32)
            values = np.concatenate([values, extra])
        elif values.shape[0] > GENE_COUNT:
            values = values[:GENE_COUNT]
        genome = Genome(values)

        creature = world.spawn_creature(
            genome=genome,
            x=float(c_data["x"]),
            y=float(c_data["y"]),
            sex=int(c_data["sex"]),
            parent_a_id=c_data.get("parent_a_id"),
            parent_b_id=c_data.get("parent_b_id"),
            generation=int(c_data.get("generation", 0)),
            clan_id=c_data.get("clan_id"),
            is_hybrid=bool(c_data.get("is_hybrid", False)),
            energy_fraction=1.0,
            health_fraction=1.0,
        )
        if creature is not None:
            creature.energy = float(c_data.get("energy", creature.energy))
            creature.health = float(c_data.get("health", creature.health))
            creature.age = int(c_data.get("age", 0))

    simulation.world = world
    simulation.stats.reset()
    simulation.stats.update(world)
    return True
