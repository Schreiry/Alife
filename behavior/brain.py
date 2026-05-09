"""Brain: glues perception + decisions + action execution.

Keeps the per-creature interface narrow: `step(creature, world, rng)`.
Action handlers mutate world state through the same APIs the simulation
itself uses, so behaviors compose cleanly.
"""

from __future__ import annotations

import math
from typing import Optional

import config

from entities.clan import Clan
from entities.creature import Creature
from .combat import resolve_attack
from .decisions import (
    Action,
    ATTACK_DISTANCE,
    EAT_DISTANCE,
    MATE_DISTANCE,
    score_actions,
)
from .perception import perceive
from .reproduction import attempt_reproduction


class Brain:
    """Stateless action selector. Lives once per simulation."""

    def __init__(self, rng):
        self.rng = rng

    def step(self, creature: Creature, world) -> None:
        if not creature.is_alive:
            return

        perception = perceive(creature, world)

        # Decide what other clan is nearby (for join_clan candidacy).
        nearby_clan_id = -1
        if creature.clan_id is None:
            if perception.closest_ally is not None and perception.closest_ally.clan_id is not None:
                nearby_clan_id = perception.closest_ally.clan_id
            elif perception.own_tile_owner is not None:
                nearby_clan_id = perception.own_tile_owner

        can_create = (
            creature.clan_id is None
            and len(world.clans) < 64
            and creature.age >= 60
        )

        action, _score = score_actions(
            creature, perception, self.rng, can_create, nearby_clan_id
        )
        creature.last_action = action.value

        # Dispatch
        if action is Action.EAT:
            self._do_eat(creature, perception, world)
        elif action is Action.SEEK_FOOD:
            self._step_toward_food(creature, perception, world)
        elif action is Action.FLEE:
            self._do_flee(creature, perception)
        elif action is Action.ATTACK:
            self._do_attack(creature, perception, world)
        elif action is Action.REPRODUCE:
            self._do_reproduce(creature, perception, world)
        elif action is Action.SEEK_MATE:
            self._step_toward(creature, perception.closest_mate)
        elif action is Action.REST:
            self._do_rest(creature)
        elif action is Action.CLAIM_TERRITORY:
            self._do_claim(creature, world)
        elif action is Action.CREATE_CLAN:
            self._do_create_clan(creature, world)
        elif action is Action.JOIN_CLAN:
            self._do_join_clan(creature, nearby_clan_id, world)
        elif action is Action.FOLLOW_CLAN:
            self._step_toward(creature, perception.closest_ally)
        elif action is Action.MIGRATE:
            self._do_migrate(creature, world)
        elif action is Action.MOVE_RANDOM:
            self._do_random_move(creature, world)
        else:
            self._do_idle(creature)

    # ---------- helpers --------------------------------------------------
    def _step_toward(self, creature: Creature, target) -> None:
        if target is None:
            self._do_random_move(creature, None)
            return
        dx = target.x - creature.x
        dy = target.y - creature.y
        dist = math.hypot(dx, dy)
        if dist < 1e-5:
            return
        speed = creature.move_speed
        # 1-tile movement cap to keep things stable in a 300x300 world.
        step = min(speed, dist)
        creature.x += dx / dist * step
        creature.y += dy / dist * step
        creature.energy -= creature.move_energy_cost * step

    def _step_away(self, creature: Creature, target) -> None:
        if target is None:
            return
        dx = creature.x - target.x
        dy = creature.y - target.y
        dist = math.hypot(dx, dy)
        if dist < 1e-5:
            return
        speed = creature.move_speed
        step = min(speed, dist)
        creature.x += dx / dist * step
        creature.y += dy / dist * step
        creature.energy -= creature.move_energy_cost * step * 1.2

    def _do_random_move(self, creature: Creature, world) -> None:
        angle = self.rng.uniform(0.0, 2.0 * math.pi)
        step = creature.move_speed * 0.6
        creature.x += math.cos(angle) * step
        creature.y += math.sin(angle) * step
        creature.energy -= creature.move_energy_cost * step

    def _do_idle(self, creature: Creature) -> None:
        creature.energy -= config.IDLE_ENERGY_COST_BASE * 0.5

    def _do_rest(self, creature: Creature) -> None:
        creature.energy -= config.IDLE_ENERGY_COST_BASE * 0.2
        creature.health = min(
            creature.max_health,
            creature.health + creature.regen_rate * creature.max_health * 0.01,
        )

    def _do_eat(self, creature: Creature, perception, world) -> None:
        fidx = perception.closest_food_idx
        if fidx < 0 or perception.closest_food_dist > EAT_DISTANCE:
            self._step_toward_food(creature, perception, world)
            return
        food_energy = float(world.food_store.energy[fidx])
        gained = food_energy * creature.digestion_efficiency * creature.energy_absorption
        creature.energy = min(creature.max_energy, creature.energy + gained)
        world.remove_food(fidx)

    def _step_toward_food(self, creature: Creature, perception, world) -> None:
        fidx = perception.closest_food_idx
        if fidx < 0:
            self._do_random_move(creature, world)
            return
        tx = float(world.food_store.x[fidx])
        ty = float(world.food_store.y[fidx])
        dx = tx - creature.x
        dy = ty - creature.y
        dist = math.hypot(dx, dy)
        if dist < 1e-5:
            return
        step = min(creature.move_speed, dist)
        creature.x += dx / dist * step
        creature.y += dy / dist * step
        creature.energy -= creature.move_energy_cost * step

    def _do_attack(self, creature: Creature, perception, world) -> None:
        enemy = perception.closest_enemy
        if enemy is None:
            return
        if perception.closest_enemy_dist > ATTACK_DISTANCE:
            self._step_toward(creature, enemy)
            return
        if creature.energy < creature.attack_energy_cost:
            return
        resolve_attack(creature, enemy, world, self.rng)

    def _do_flee(self, creature: Creature, perception) -> None:
        if perception.closest_enemy is None:
            return
        self._step_away(creature, perception.closest_enemy)

    def _do_reproduce(self, creature: Creature, perception, world) -> None:
        mate = perception.closest_mate
        if mate is None:
            return
        if perception.closest_mate_dist > MATE_DISTANCE:
            self._step_toward(creature, mate)
            return
        attempt_reproduction(creature, mate, world, self.rng)

    def _do_claim(self, creature: Creature, world) -> None:
        if creature.clan_id is None:
            return
        world.territory.reinforce(
            int(creature.x),
            int(creature.y),
            creature.clan_id,
            config.CLAN_TERRITORY_GAIN * (0.5 + creature.territoriality),
        )
        creature.energy -= config.IDLE_ENERGY_COST_BASE

    def _do_create_clan(self, creature: Creature, world) -> None:
        if creature.clan_id is not None:
            return
        if len(world.clans) >= 64:
            return
        if creature.energy < creature.max_energy * 0.55:
            return
        if creature.leadership <= 0.55 or creature.clan_creation_chance_n <= 0.5:
            return
        world.create_clan(creature)
        creature.energy -= config.IDLE_ENERGY_COST_BASE * 5

    def _do_join_clan(self, creature: Creature, clan_id: int, world) -> None:
        if clan_id == -1 or creature.clan_id is not None:
            return
        clan: Optional[Clan] = world.clans.get(clan_id)
        if clan is None:
            return
        world.join_clan(creature, clan)

    def _do_migrate(self, creature: Creature, world) -> None:
        # Bias toward the center of nearby empty space; cheap proxy = random.
        self._do_random_move(creature, world)
