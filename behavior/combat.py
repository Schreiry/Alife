"""Combat resolution: a single attacker-vs-defender exchange."""

from __future__ import annotations

import config

from entities.creature import Creature


def resolve_attack(attacker: Creature, defender: Creature, world, rng) -> None:
    if not attacker.is_alive or not defender.is_alive:
        return

    attacker.energy -= attacker.attack_energy_cost

    # Defender gets a chance to dodge entirely.
    if rng.random() < defender.dodge_chance:
        return

    rand_factor = rng.uniform(
        config.ATTACK_RANDOM_FACTOR_MIN,
        config.ATTACK_RANDOM_FACTOR_MAX,
    )
    base_damage = attacker.attack_power_real * rand_factor
    if rng.random() < attacker.crit_chance:
        base_damage *= 1.8

    damage = base_damage - defender.defense_power_real * config.DEFENSE_MODIFIER
    if damage < config.MIN_DAMAGE:
        damage = config.MIN_DAMAGE

    defender.health -= damage
    defender.rage = min(1.0, defender.rage + 0.05)

    if defender.health <= 0:
        defender.kill("combat")
        # Winner gains a portion of victim energy + confidence.
        gained = defender.energy * config.COMBAT_ENERGY_GAIN_FRACTION
        attacker.energy = min(attacker.max_energy, attacker.energy + gained)
        attacker.confidence = min(1.0, attacker.confidence
                                  + attacker.genome.real("victory_confidence_gain"))

        # Diplomacy: clans of attacker and defender go further into hostility.
        if (
            attacker.clan_id is not None
            and defender.clan_id is not None
            and attacker.clan_id != defender.clan_id
        ):
            _adjust_relations(world, attacker.clan_id, defender.clan_id,
                              -config.DIPLOMACY_KILL_PENALTY)

        world.deaths_total += 1
        world.deaths_by_combat += 1
        world.emit("death", {
            "id": defender.id, "cause": "combat",
            "killer": attacker.id, "age": defender.age,
            "generation": defender.generation,
        })


def _adjust_relations(world, clan_a: int, clan_b: int, delta: float) -> None:
    a = world.clans.get(clan_a)
    b = world.clans.get(clan_b)
    if a is not None:
        a.relations[clan_b] = max(-1.0, min(1.0, a.relations.get(clan_b, 0.0) + delta))
    if b is not None:
        b.relations[clan_a] = max(-1.0, min(1.0, b.relations.get(clan_a, 0.0) + delta))
