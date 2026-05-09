"""Score-based action selection.

Each candidate action gets a numeric score; the best one wins, with a
small randomness term so behavior isn't perfectly mechanical. The brain
delegates to this module, but the scoring is intentionally pure so it
can be unit-tested or swapped out later.
"""

from __future__ import annotations

from enum import Enum
from typing import Tuple

from entities.creature import Creature
from .perception import Perception


class Action(str, Enum):
    IDLE = "idle"
    MOVE_RANDOM = "move_random"
    SEEK_FOOD = "seek_food"
    EAT = "eat"
    REST = "rest"
    FLEE = "flee"
    ATTACK = "attack"
    SEEK_MATE = "seek_mate"
    REPRODUCE = "reproduce"
    CLAIM_TERRITORY = "claim_territory"
    CREATE_CLAN = "create_clan"
    JOIN_CLAN = "join_clan"
    FOLLOW_CLAN = "follow_clan"
    MIGRATE = "migrate"


# Distance thresholds for "right next to it" actions.
EAT_DISTANCE: float = 1.5
MATE_DISTANCE: float = 2.0
ATTACK_DISTANCE: float = 1.6


def score_actions(
    c: Creature,
    p: Perception,
    rng,
    can_create_clan: bool,
    nearby_clan_id: int = -1,
) -> Tuple[Action, float]:
    """Return the chosen action and its score."""

    energy_frac = c.energy / max(1.0, c.max_energy)
    health_frac = c.health / max(1.0, c.max_health)
    hunger = 1.0 - energy_frac

    # ---- food ---------------------------------------------------------
    food_score = 0.0
    has_food = p.closest_food_idx >= 0
    if has_food:
        proximity = 1.0 / (1.0 + p.closest_food_dist)
        food_score = (
            hunger * 1.6
            + 0.4 * c.food_search_efficiency
            + 0.6 * proximity
        )
        if p.closest_food_dist <= EAT_DISTANCE:
            food_score += 1.5

    eat_score = 0.0
    if has_food and p.closest_food_dist <= EAT_DISTANCE:
        eat_score = food_score + 1.5

    # ---- flee ---------------------------------------------------------
    flee_score = 0.0
    if p.closest_enemy is not None:
        weakness = 1.0 - health_frac
        threat = p.local_danger / max(1.0, c.attack_power_real)
        flee_score = (
            c.fear * 1.4
            + c.self_preservation * 0.8
            + weakness * 1.5
            + threat * 0.7
            - c.aggression * 0.5
        )
        if health_frac < c.retreat_threshold:
            flee_score += 1.5

    # ---- attack -------------------------------------------------------
    attack_score = 0.0
    if p.closest_enemy is not None and energy_frac > 0.2:
        enemy = p.closest_enemy
        enemy_weakness = 1.0 - (enemy.health / max(1.0, enemy.max_health))
        own_strength = c.attack_power_real / max(1.0, enemy.defense_power_real + 1.0)
        attack_score = (
            c.aggression * 1.3
            + c.hunting_instinct * 0.6
            + enemy_weakness * 0.9
            + own_strength * 0.4
            - c.fear * 0.7
        )
        if p.closest_enemy_dist <= ATTACK_DISTANCE:
            attack_score += 1.0
        if p.is_on_enemy_clan_tile:
            attack_score += 0.4 * c.territoriality

    # ---- mate ---------------------------------------------------------
    mate_score = 0.0
    repro_score = 0.0
    can_repro = (
        c.age >= c.min_age_repro
        and c.mating_cooldown <= 0
        and energy_frac >= c.min_energy_repro_fraction
        and p.closest_enemy_dist > 4.0  # avoid breeding under threat
    )
    if can_repro and p.closest_mate is not None:
        mate_score = (
            c.reproduction_drive * 1.4
            + c.fertility * 0.6
            + 0.6 / (1.0 + p.closest_mate_dist)
        )
        if p.closest_mate_dist <= MATE_DISTANCE:
            repro_score = mate_score + 1.5

    # ---- rest ---------------------------------------------------------
    rest_score = 0.0
    if energy_frac < 0.4 and p.closest_enemy is None:
        rest_score = (1.0 - energy_frac) * 0.6 + 0.2 * c.self_preservation

    # ---- territory ----------------------------------------------------
    claim_score = 0.0
    if c.clan_id is not None:
        owner = p.own_tile_owner
        if owner is None or owner != c.clan_id:
            claim_score = (
                c.territoriality * 0.9
                + c.expansion_drive * 0.4
                + (0.6 if owner is None else 0.2)
            )

    # ---- clan ---------------------------------------------------------
    create_clan_score = 0.0
    join_clan_score = 0.0
    if c.clan_id is None:
        if (
            can_create_clan
            and c.leadership > 0.55
            and c.clan_creation_chance_n > 0.5
            and energy_frac > 0.55
        ):
            dominance = 0.5 + 0.5 * (
                c.genome.normalized("dominance_drive")
                - c.genome.normalized("submission_tendency")
            )
            create_clan_score = (
                c.leadership * 1.0
                + c.clan_creation_chance_n * 0.8
                + dominance * 0.3
            )
        if nearby_clan_id != -1 and c.clan_joining_chance_n > 0.4:
            join_clan_score = (
                c.social_bonding * 0.8
                + c.trust * 0.6
                + c.clan_joining_chance_n * 1.0
                + c.cooperation * 0.4
            )

    # ---- follow clan / migrate ---------------------------------------
    follow_score = 0.0
    if c.clan_id is not None and p.closest_ally is not None and p.closest_ally_dist > 4.0:
        follow_score = c.pack_instinct * 0.5 + c.cooperation * 0.3

    migrate_score = 0.0
    if energy_frac > 0.6 and p.nearby_food_count == 0 and p.nearby_enemies == 0:
        migrate_score = c.curiosity * 0.4 + 0.2

    # ---- baseline -----------------------------------------------------
    move_random_score = 0.05 + 0.2 * c.curiosity + 0.1 * c.impulsiveness
    idle_score = 0.02

    candidates = [
        (Action.EAT, eat_score),
        (Action.SEEK_FOOD, food_score),
        (Action.FLEE, flee_score),
        (Action.ATTACK, attack_score),
        (Action.REPRODUCE, repro_score),
        (Action.SEEK_MATE, mate_score),
        (Action.REST, rest_score),
        (Action.CLAIM_TERRITORY, claim_score),
        (Action.CREATE_CLAN, create_clan_score),
        (Action.JOIN_CLAN, join_clan_score),
        (Action.FOLLOW_CLAN, follow_score),
        (Action.MIGRATE, migrate_score),
        (Action.MOVE_RANDOM, move_random_score),
        (Action.IDLE, idle_score),
    ]

    # Add controlled randomness scaled by impulsiveness.
    jitter = 0.08 + 0.25 * c.impulsiveness
    best_action = Action.IDLE
    best_score = -1e9
    for action, score in candidates:
        s = score + (rng.random() - 0.5) * jitter
        if s > best_score:
            best_score = s
            best_action = action
    return best_action, best_score


