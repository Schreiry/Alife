"""Inter-clan diplomacy: per-tick relation drift."""

from __future__ import annotations

import config


def step_diplomacy(world) -> None:
    """Slowly drift relations: peace if no friction, warmer over time."""
    coexist = config.DIPLOMACY_COEXIST_BONUS
    decay = config.DIPLOMACY_DECAY
    clans = list(world.clans.values())
    for clan in clans:
        for other_id, rel in list(clan.relations.items()):
            # Pull values toward zero slowly (decay), then add coexistence bonus.
            if rel > 0:
                rel = max(0.0, rel - decay)
            elif rel < 0:
                rel = min(0.0, rel + decay)
            rel += coexist
            if rel > 1.0:
                rel = 1.0
            elif rel < -1.0:
                rel = -1.0
            clan.relations[other_id] = rel


def relation_label(value: float) -> str:
    if value <= config.WAR_THRESHOLD:
        return "war"
    if value >= config.ALLIANCE_THRESHOLD:
        return "ally"
    return "neutral"
