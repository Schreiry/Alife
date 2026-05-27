"""Snapshot extraction.

Turns the live Simulation state into JSON-serializable dicts at two
granularities:

  * `live_snapshot(sim)` — small, sent over WebSocket at ~20 Hz. Just
    enough to render the map and chrome (no genomes, no clan members).
  * `creature_detail(sim, cid)` — large, served on demand for the
    inspector panel. Includes full genome.

Two performance rules to keep this cheap:
  - Never iterate Python dicts over the full population if a numpy mask
    will do.
  - Snapshots are built under a *cooperative* assumption: SimRunner pauses
    the sim thread by holding `sim.snapshot_lock` (a plain threading.Lock)
    while extracting, so we don't see torn arrays.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

import config


def live_snapshot(sim) -> Dict[str, Any]:
    world = sim.world
    store = world.store
    alive = store.alive
    alive_idx = np.flatnonzero(alive)

    n = alive_idx.size
    # Map data: only the alive subset, only fields the renderer needs.
    if n:
        x = store.x[alive_idx].astype(np.float32).tolist()
        y = store.y[alive_idx].astype(np.float32).tolist()
        cre_ids = store.creature_id[alive_idx].astype(np.int32).tolist()
        clan_ids = store.clan_id[alive_idx].astype(np.int32).tolist()
        species = store.species_id[alive_idx].astype(np.int32).tolist()
        # Colors live on the Creature object — pack via creature_by_idx.
        colors_r = [0] * n
        colors_g = [0] * n
        colors_b = [0] * n
        for i, idx in enumerate(alive_idx.tolist()):
            c = world.creature_by_idx[idx]
            if c is not None:
                cr, cg, cb = c.color
                colors_r[i] = cr
                colors_g[i] = cg
                colors_b[i] = cb
    else:
        x = []; y = []; cre_ids = []; clan_ids = []; species = []
        colors_r = []; colors_g = []; colors_b = []

    food = world.food_store
    food_alive_idx = np.flatnonzero(food.alive)
    food_x = food.x[food_alive_idx].astype(np.float32).tolist() if food_alive_idx.size else []
    food_y = food.y[food_alive_idx].astype(np.float32).tolist() if food_alive_idx.size else []

    clans_payload = []
    for clan in world.clans.values():
        clans_payload.append({
            "id": clan.id,
            "name": clan.name,
            "color": list(clan.color),
            "members": len(clan.members),
            "territory": clan.territory_count,
            "aggression": round(clan.aggression_level, 3),
        })

    stats = sim.stats
    prof = sim.profiler

    return {
        "tick": world.tick,
        "paused": bool(sim.paused),
        "speed": config.SPEED_LEVELS[sim.speed_index],
        "world": {
            "width": config.WORLD_WIDTH,
            "height": config.WORLD_HEIGHT,
        },
        "population": int(world.population()),
        "max_population": config.MAX_CREATURES,
        "food_count": int(world.food_count()),
        "species_count": int(stats.species_count),
        "clan_count": int(stats.clan_count),
        "hybrids": int(stats.hybrid_total),
        "generation_max": int(stats.generation_max),
        "births": int(stats.births_total),
        "deaths": int(stats.deaths_total),
        "deaths_starvation": int(stats.deaths_by_starvation),
        "deaths_age": int(stats.deaths_by_age),
        "deaths_combat": int(stats.deaths_by_combat),
        "avg_energy": round(stats.avg_energy, 2),
        "avg_health": round(stats.avg_health, 2),
        "avg_strength": round(stats.avg_strength, 3),
        "avg_intelligence": round(stats.avg_intelligence, 3),
        "avg_aggression": round(stats.avg_aggression, 3),
        "avg_age": round(stats.avg_age, 1),
        "profiler": {
            "tick_ms": round(prof.last_tick_ms, 2),
            "slow_ticks": int(prof.slow_tick_count),
            "last_phase": prof.last_phase,
            "sections": {k: round(v, 3) for k, v in prof.snapshot().items()},
        },
        "creatures": {
            "ids": cre_ids,
            "x": x,
            "y": y,
            "clan": clan_ids,
            "species": species,
            "r": colors_r,
            "g": colors_g,
            "b": colors_b,
        },
        "food": {"x": food_x, "y": food_y},
        "clans": clans_payload,
    }


def history_snapshot(sim, limit: int = 200) -> Dict[str, Any]:
    """Recent timeseries used for charts. Tail of the stats history."""
    history = sim.stats.history[-limit:] if sim.stats.history else []
    return {"history": history}


def config_snapshot() -> Dict[str, Any]:
    """Read-only view of the active configuration. UI shows it; experiment
    runs serialize it next to the result."""
    keys = (
        "WORLD_WIDTH", "WORLD_HEIGHT", "TILE_SIZE", "SPATIAL_HASH_CELL",
        "INITIAL_CREATURES", "MAX_CREATURES",
        "INITIAL_FOOD", "MAX_FOOD", "FOOD_SPAWN_PER_TICK", "FOOD_ENERGY",
        "PERCEPTION_INTERVAL", "REPRODUCTION_INTERVAL", "COMBAT_INTERVAL",
        "TERRITORY_DECAY_INTERVAL", "STATISTICS_INTERVAL",
        "CLAN_UPDATE_INTERVAL", "DIPLOMACY_INTERVAL",
        "COMPACT_INTERVAL", "CHECKPOINT_INTERVAL", "SPECIES_RESYNC_INTERVAL",
        "DEFAULT_MUTATION_RATE", "DEFAULT_MUTATION_STRENGTH",
        "SPECIES_DISTANCE_THRESHOLD", "WAR_THRESHOLD", "ALLIANCE_THRESHOLD",
        "OBSERVATORY_HOST", "OBSERVATORY_PORT",
        "OBSERVATORY_WS_HZ", "OBSERVATORY_SIM_HZ",
        "WATCHDOG_TICK_MS_THRESHOLD",
    )
    return {k: getattr(config, k) for k in keys}


def species_list(sim) -> Dict[str, Any]:
    out = []
    for sp in sim.world.species.species.values():
        if sp.population_count <= 0:
            continue
        out.append({
            "id": sp.id,
            "name": sp.name,
            "color": list(sp.base_color),
            "founder": sp.founder_id,
            "created_tick": sp.created_tick,
            "population": sp.population_count,
        })
    out.sort(key=lambda s: -s["population"])
    return {"count": len(out), "species": out}


def clans_list(sim) -> Dict[str, Any]:
    out = []
    for c in sim.world.clans.values():
        out.append({
            "id": c.id,
            "name": c.name,
            "color": list(c.color),
            "leader": c.leader_id,
            "members": len(c.members),
            "territory": c.territory_count,
            "aggression": round(c.aggression_level, 3),
            "ideology": round(c.ideology, 3),
            "stability": round(c.stability, 3),
            "relations": {int(k): round(v, 3) for k, v in c.relations.items()},
        })
    out.sort(key=lambda d: -d["members"])
    return {"count": len(out), "clans": out}


def metrics_now(sim) -> Dict[str, Any]:
    """Quick scalar dump — what dashboards want without a snapshot."""
    s = sim.stats
    prof = sim.profiler
    return {
        "tick": sim.world.tick,
        "population": int(s.population),
        "food": int(s.food),
        "species_count": int(s.species_count),
        "clan_count": int(s.clan_count),
        "births_total": int(s.births_total),
        "deaths_total": int(s.deaths_total),
        "deaths_starvation": int(s.deaths_by_starvation),
        "deaths_age": int(s.deaths_by_age),
        "deaths_combat": int(s.deaths_by_combat),
        "hybrids": int(s.hybrid_total),
        "generation_max": int(s.generation_max),
        "avg_energy": round(s.avg_energy, 3),
        "avg_health": round(s.avg_health, 3),
        "avg_strength": round(s.avg_strength, 3),
        "avg_intelligence": round(s.avg_intelligence, 3),
        "avg_aggression": round(s.avg_aggression, 3),
        "avg_age": round(s.avg_age, 1),
        "tick_ms": round(prof.last_tick_ms, 3),
        "slow_ticks": int(prof.slow_tick_count),
    }


def creature_detail(sim, cid: int) -> Optional[Dict[str, Any]]:
    creature = sim.world.creatures.get(cid)
    if creature is None:
        return None
    genome = {k: round(v, 4) for k, v in creature.genome.to_dict().items()}
    return {
        "id": creature.id,
        "x": float(creature.x),
        "y": float(creature.y),
        "sex": int(creature.sex),
        "age": int(creature.age),
        "lifespan": int(creature.lifespan),
        "generation": int(creature.generation),
        "species_id": int(creature.species_id),
        "clan_id": creature.clan_id,
        "is_hybrid": bool(creature.is_hybrid),
        "archetype": creature.archetype,
        "energy": float(creature.energy),
        "max_energy": float(creature.max_energy),
        "health": float(creature.health),
        "max_health": float(creature.max_health),
        "color": list(creature.color),
        "last_action": creature.last_action,
        "parent_a": creature.parent_a_id,
        "parent_b": creature.parent_b_id,
        "death_cause": creature.death_cause,
        "genome": genome,
    }
