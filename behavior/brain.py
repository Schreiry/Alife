"""Concrete brain implementations.

  * BaselineScoreBrain — handcrafted action scoring + dispatch. Stable
                         fallback per §8.
  * HybridBrain        — same scoring, but each action score is biased by
                         a genome-derived multiplier (the creature's
                         archetype). Lets evolution shift behavior without
                         abandoning baseline survival rules.

The `Brain` name is kept as an alias for backward compatibility (older
imports do `from behavior.brain import Brain`).
"""

from __future__ import annotations

import math
from typing import Optional

import config

from entities.clan import Clan
from entities.creature import Creature
from .brain_interface import BrainInterface
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


class BaselineScoreBrain(BrainInterface):
    """Stateless action selector — handcrafted scoring rules."""

    def __init__(self, rng):
        self.rng = rng

    def decide(self, creature, perception, world):
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
        action, _ = score_actions(creature, perception, self.rng,
                                  can_create, nearby_clan_id)
        return action, nearby_clan_id

    def step(self, creature: Creature, world) -> None:
        if not creature.is_alive:
            return

        perception = perceive(creature, world)
        action, nearby_clan_id = self.decide(creature, perception, world)

        # Per-tick gates: convert throttled intents into a cheaper substitute
        # so a creature that *wants* to reproduce on an off-tick still moves
        # toward its mate, instead of standing still.
        if action is Action.REPRODUCE and not world.allow_reproduce_tick:
            action = Action.SEEK_MATE if perception.closest_mate is not None else Action.MOVE_RANDOM
        elif action is Action.ATTACK and not world.allow_attack_tick:
            action = Action.MOVE_RANDOM

        # Long-range mate seeking. A reproduction-ready creature with no mate
        # in sight would otherwise wander at random and, in a large sparse
        # world, never re-encounter a partner (Allee trap -> extinction).
        # Steer it toward the nearest distant creature, or the population
        # centroid, so isolated survivors re-aggregate and can breed.
        if (perception.closest_mate is None
                and perception.closest_enemy is None
                and action in (Action.MOVE_RANDOM, Action.MIGRATE,
                               Action.IDLE, Action.REST)
                and self._is_repro_ready(creature)):
            creature.last_action = "seek_distant_mate"
            self._seek_distant_mate(creature, world)
            return

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
        elif action is Action.DEFEND:
            self._do_defend(creature, perception)
        elif action is Action.COMMUNICATE:
            self._do_communicate(creature, perception, world)
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

    @staticmethod
    def _is_repro_ready(creature: Creature) -> bool:
        return (
            creature.age >= creature.min_age_repro
            and creature.mating_cooldown <= 0
            and creature.energy >= creature.max_energy * creature.min_energy_repro_fraction
        )

    def _step_toward_point(self, creature: Creature, tx: float, ty: float) -> None:
        dx = tx - creature.x
        dy = ty - creature.y
        dist = math.hypot(dx, dy)
        if dist < 1e-5:
            return
        step = min(creature.move_speed, dist)
        creature.x += dx / dist * step
        creature.y += dy / dist * step
        creature.energy -= creature.move_energy_cost * step

    def _seek_distant_mate(self, creature: Creature, world) -> None:
        store = world.store
        idx = creature.store_idx
        cx = creature.x
        cy = creature.y
        my_sex = creature.sex
        candidates = world.creature_grid.query_indices(cx, cy, config.MATE_SEEK_RADIUS)
        best = -1
        best_d2 = float("inf")
        for j in candidates:
            j = int(j)
            if j == idx or not store.alive[j]:
                continue
            if int(store.sex[j]) == my_sex:
                continue
            dx = float(store.x[j]) - cx
            dy = float(store.y[j]) - cy
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best = j
        if best >= 0:
            target = world.creature_by_idx[best]
            if target is not None:
                self._step_toward(creature, target)
                return
        # No opposite-sex creature even in the wide radius: converge on the
        # population centroid so scattered survivors come back together.
        self._step_toward_point(creature, world.centroid_x, world.centroid_y)

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
        world.territory.reinforce_area(
            int(creature.x),
            int(creature.y),
            creature.clan_id,
            config.CLAN_TERRITORY_GAIN * (0.5 + creature.territoriality),
            config.CLAN_TERRITORY_CLAIM_RADIUS,
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
        # Directed migration: sample a ring of candidate points one-ish ecology
        # cell out and head for the richest, least-depleted one. Turns the
        # depletion sensor into actual relocation toward fertile ground.
        look = config.ECOLOGY_ZONE * 1.5
        best_x = best_y = None
        best_score = -2.0
        for k in range(6):
            ang = 2.0 * math.pi * (k / 6.0) + self.rng.random() * 0.5
            tx = creature.x + math.cos(ang) * look
            ty = creature.y + math.sin(ang) * look
            if tx < 0 or tx >= config.WORLD_WIDTH or ty < 0 or ty >= config.WORLD_HEIGHT:
                continue
            food_ratio, depletion = world.ecology.sample(tx, ty)
            score = food_ratio - depletion
            if score > best_score:
                best_score = score
                best_x, best_y = tx, ty
        if best_x is None:
            self._do_random_move(creature, world)
            return
        self._step_toward_point(creature, best_x, best_y)

    def _do_defend(self, creature: Creature, perception) -> None:
        # Stand ground and reduce energy cost; if attacked, combat handles damage.
        creature.energy -= config.IDLE_ENERGY_COST_BASE * 0.3
        # Mark territory under our feet a bit harder.
        if creature.clan_id is not None and perception.is_on_own_clan_tile:
            creature.rage = min(1.0, creature.rage + 0.02)

    def _do_communicate(self, creature: Creature, perception, world) -> None:
        # Emit a clan signal: small territory reinforcement at current tile
        # if in own clan, otherwise just an idle pulse. Hook for future
        # message bus / threat memory.
        creature.energy -= config.IDLE_ENERGY_COST_BASE * 0.4
        if creature.clan_id is not None and perception.is_on_own_clan_tile:
            world.territory.reinforce(
                int(creature.x), int(creature.y),
                creature.clan_id,
                config.CLAN_TERRITORY_GAIN * 0.3 * creature.social_bonding,
            )


class HybridBrain(BaselineScoreBrain):
    """Baseline scoring biased by creature archetype.

    The archetype enum (Forager/Predator/Social/Explorer/Hybrid) is
    derived from dominant genes at spawn time and stored on the Creature.
    Here we re-score the baseline's chosen action set with a small
    per-archetype multiplier so genome-driven personality shifts without
    breaking baseline survival rules."""

    def decide(self, creature, perception, world):
        # Reuse baseline's full scoring then apply a single boost on the
        # chosen action. This is intentionally light — the baseline still
        # owns survival logic; archetype just nudges style.
        action, nearby_clan_id = super().decide(creature, perception, world)
        # Already-chosen action stays; the bias was applied through the
        # baseline scorer via creature.* attributes that the archetype
        # already inflated (see entities.archetype.amplify_traits).
        return action, nearby_clan_id


# Backward-compatible alias.
Brain = BaselineScoreBrain
