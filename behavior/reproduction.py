"""Reproduction: gating + offspring construction."""

from __future__ import annotations

import config

from entities.creature import Creature
from genetics.inheritance import crossover


def can_reproduce(a: Creature, b: Creature) -> bool:
    if not (a.is_alive and b.is_alive):
        return False
    if a.sex == b.sex:
        return False
    if a.mating_cooldown > 0 or b.mating_cooldown > 0:
        return False
    if a.age < a.min_age_repro or b.age < b.min_age_repro:
        return False
    if (
        a.energy < a.max_energy * a.min_energy_repro_fraction
        or b.energy < b.max_energy * b.min_energy_repro_fraction
    ):
        return False

    distance = a.genome.distance(b.genome)
    compat_window = 0.5 * (
        a.genome.real("genetic_compatibility_range")
        + b.genome.real("genetic_compatibility_range")
    )
    if distance > compat_window:
        return False

    # Incest avoidance — if creatures share a parent, applied genetically.
    if (
        a.parent_a_id is not None
        and (
            a.parent_a_id == b.parent_a_id
            or a.parent_a_id == b.parent_b_id
            or a.parent_b_id == b.parent_a_id
            or a.parent_b_id == b.parent_b_id
        )
    ):
        avoidance = 0.5 * (a.incest_avoidance + b.incest_avoidance)
        if avoidance > 0.5:
            return False

    return True


def attempt_reproduction(a: Creature, b: Creature, world, rng) -> int:
    """Return number of offspring spawned (0 if blocked)."""
    if not can_reproduce(a, b):
        return 0
    if world.population() >= config.MAX_CREATURES:
        return 0

    # Local density check: don't allow infinite breeding in one spot.
    nearby = int(
        world.creature_grid.query_indices(
            a.x, a.y, config.REPRODUCTION_DENSITY_RADIUS
        ).size
    )
    if nearby > config.LOCAL_DENSITY_LIMIT:
        return 0

    is_hybrid = a.species_id != b.species_id

    # How many offspring this couple produces — bounded by the parent
    # genes and by global config.
    min_count = max(
        config.OFFSPRING_BASE_MIN,
        int(0.5 * (a.genome.real("offspring_count_min") + b.genome.real("offspring_count_min"))),
    )
    max_count = min(
        config.OFFSPRING_BASE_MAX,
        int(0.5 * (a.genome.real("offspring_count_max") + b.genome.real("offspring_count_max"))),
    )
    if max_count < min_count:
        max_count = min_count
    n = int(rng.integers(min_count, max_count + 1))

    spawned = 0
    for _ in range(n):
        if world.population() >= config.MAX_CREATURES:
            break
        child_genome, _mutated = crossover(a.genome, b.genome, rng, is_hybrid=is_hybrid)
        sex = int(rng.integers(0, 2))
        offset_x = float(rng.uniform(-1.5, 1.5))
        offset_y = float(rng.uniform(-1.5, 1.5))
        gen = max(a.generation, b.generation) + 1

        # Pick a clan from one of the parents (if either has one).
        clan_id = a.clan_id if a.clan_id is not None else b.clan_id

        child = world.spawn_creature(
            genome=child_genome,
            x=_clamp(a.x + offset_x, 0, config.WORLD_WIDTH - 1),
            y=_clamp(a.y + offset_y, 0, config.WORLD_HEIGHT - 1),
            sex=sex,
            parent_a_id=a.id,
            parent_b_id=b.id,
            generation=gen,
            clan_id=clan_id,
            is_hybrid=is_hybrid,
            energy_fraction=config.NEWBORN_ENERGY_FRACTION,
            health_fraction=config.NEWBORN_HEALTH_FRACTION,
        )
        if child is None:
            break
        spawned += 1
        world.births_total += 1
        world.emit("birth", {
            "id": child.id,
            "parents": [a.id, b.id],
            "generation": child.generation,
            "is_hybrid": is_hybrid,
            "species": int(child.species_id),
            "clan": child.clan_id,
        })

    if spawned > 0:
        cost = a.repro_energy_cost * 0.5
        a.energy = max(0.0, a.energy - cost)
        b.energy = max(0.0, b.energy - cost)
        a.mating_cooldown = a.mating_cooldown_ticks
        b.mating_cooldown = b.mating_cooldown_ticks
    return spawned


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
