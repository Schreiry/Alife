"""Save / load full simulation state.

Layout on disk (per save path):
  <path>                    JSON metadata (tick, totals, clans, species,
                            creatures cold fields, rng state, config snapshot)
  <path>.genomes.npz        NPZ with genome matrix (ids, values)
  <path>.world.npz          NPZ with territory grids (owner, strength)

All writes go through a temp file + os.replace so an interrupted save
never leaves a corrupt artifact. JSON is for hand-inspection; NPZ for
bulk numpy arrays (loading mmap-fast). Telemetry is its own SQLite db
and is *not* bundled into the checkpoint — it represents history, not
snapshot state.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

import numpy as np

import config
from core.world import World
from entities.clan import Clan
from genetics.genome import Genome


def _atomic_write_bytes(path: str, data: bytes) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".save_", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _atomic_npz(path: str, **arrays: np.ndarray) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".save_", suffix=".npz", dir=directory)
    os.close(fd)
    try:
        np.savez_compressed(tmp, **arrays)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _config_snapshot() -> Dict[str, Any]:
    """Capture the values currently in `config` that affect world shape."""
    keys = (
        "WORLD_WIDTH", "WORLD_HEIGHT", "TILE_SIZE", "SPATIAL_HASH_CELL",
        "INITIAL_CREATURES", "MAX_CREATURES",
        "INITIAL_FOOD", "MAX_FOOD", "FOOD_SPAWN_PER_TICK", "FOOD_ENERGY",
        "PERCEPTION_INTERVAL", "REPRODUCTION_INTERVAL", "COMBAT_INTERVAL",
        "TERRITORY_DECAY_INTERVAL", "DIPLOMACY_INTERVAL",
        "STATISTICS_INTERVAL", "CLAN_UPDATE_INTERVAL",
        "COMPACT_INTERVAL", "CHECKPOINT_INTERVAL",
    )
    return {k: getattr(config, k) for k in keys}


def save(world: World, stats, path: str = config.SAVE_PATH,
         rng: Optional[np.random.Generator] = None) -> Dict[str, Any]:
    """Persist full simulation state. Returns the metadata payload (handy
    for logging / API responses)."""
    t0 = time.time()
    creatures_meta: List[Dict[str, Any]] = []
    genome_ids: List[int] = []
    genome_rows: List[np.ndarray] = []

    for c in world.creatures.values():
        creatures_meta.append({
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
        })
        genome_ids.append(c.id)
        genome_rows.append(c.genome.values)

    clans_payload: List[Dict[str, Any]] = []
    for clan in world.clans.values():
        clans_payload.append({
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
            "territory_count": clan.territory_count,
        })

    species_payload: List[Dict[str, Any]] = []
    for sp in world.species.species.values():
        species_payload.append({
            "id": sp.id,
            "name": sp.name,
            "base_color": list(sp.base_color),
            "founder_id": sp.founder_id,
            "created_tick": sp.created_tick,
            "population_count": sp.population_count,
            # Signature is dense — store as base64-less json-friendly list.
            "signature": sp.signature.astype(np.float32).tolist(),
        })

    rng_state: Optional[Dict[str, Any]] = None
    if rng is not None:
        try:
            raw = rng.bit_generator.state
            rng_state = json.loads(json.dumps(raw, default=_json_default))
        except Exception:
            rng_state = None

    payload: Dict[str, Any] = {
        "version": 2,
        "saved_at": t0,
        "tick": world.tick,
        "config": _config_snapshot(),
        "rng_state": rng_state,
        "creatures": creatures_meta,
        "clans": clans_payload,
        "species": species_payload,
        "stats": {
            "births_total": world.births_total,
            "deaths_total": world.deaths_total,
            "deaths_by_starvation": world.deaths_by_starvation,
            "deaths_by_age": world.deaths_by_age,
            "deaths_by_combat": world.deaths_by_combat,
            "hybrid_total": world.hybrid_total,
            "generation_max": world.generation_max,
        },
        "genomes_ref": os.path.basename(path) + ".genomes.npz",
        "world_ref": os.path.basename(path) + ".world.npz",
    }

    _atomic_write_bytes(path, json.dumps(payload).encode("utf-8"))

    # Genome matrix.
    if genome_rows:
        ids_arr = np.asarray(genome_ids, dtype=np.int32)
        genomes_arr = np.stack(genome_rows).astype(np.float32, copy=False)
    else:
        from genetics.genes import GENE_COUNT
        ids_arr = np.zeros(0, dtype=np.int32)
        genomes_arr = np.zeros((0, GENE_COUNT), dtype=np.float32)
    _atomic_npz(path + ".genomes.npz", ids=ids_arr, genomes=genomes_arr)

    # World grids — small at 300x300, and they ARE the state of territory.
    _atomic_npz(
        path + ".world.npz",
        territory_owner=world.territory.owner,
        territory_strength=world.territory.strength,
    )

    return {"ok": True, "tick": world.tick, "creatures": len(creatures_meta),
            "clans": len(clans_payload), "species": len(species_payload),
            "elapsed_ms": int((time.time() - t0) * 1000)}


def _json_default(obj):
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    raise TypeError(f"Cannot json-serialize {type(obj)}")


def load(simulation, path: str = config.SAVE_PATH) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False

    from genetics.genes import GENE_COUNT
    from genetics.species import Species

    base_dir = os.path.dirname(path) or "."

    genome_lookup: Dict[int, np.ndarray] = {}
    npz_ref = payload.get("genomes_ref")
    if npz_ref:
        full = os.path.join(base_dir, npz_ref)
        if os.path.exists(full):
            try:
                with np.load(full) as data:
                    ids = data["ids"]; genomes = data["genomes"]
                for i, cid in enumerate(ids.tolist()):
                    genome_lookup[int(cid)] = genomes[i]
            except (OSError, KeyError):
                pass

    world = World(simulation.rng)
    world.telemetry = simulation.telemetry
    world.tick = int(payload.get("tick", 0))
    s = payload.get("stats", {})
    world.births_total = int(s.get("births_total", 0))
    world.deaths_total = int(s.get("deaths_total", 0))
    world.deaths_by_starvation = int(s.get("deaths_by_starvation", 0))
    world.deaths_by_age = int(s.get("deaths_by_age", 0))
    world.deaths_by_combat = int(s.get("deaths_by_combat", 0))
    world.hybrid_total = int(s.get("hybrid_total", 0))
    world.generation_max = int(s.get("generation_max", 0))

    # Restore territory grids.
    world_ref = payload.get("world_ref")
    if world_ref:
        full = os.path.join(base_dir, world_ref)
        if os.path.exists(full):
            try:
                with np.load(full) as data:
                    own = data["territory_owner"]
                    stren = data["territory_strength"]
                if own.shape == world.territory.owner.shape:
                    world.territory.owner[...] = own
                    world.territory.strength[...] = stren
                    world.territory_dirty = True
            except (OSError, KeyError):
                pass

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
        clan.territory_count = int(clan_data.get("territory_count", 0))
        world.clans[clan.id] = clan
        world._next_clan_id = max(world._next_clan_id, clan.id + 1)

    # Restore species. The signatures will be overwritten when creatures
    # are spawned in via assign(); we restore them right after so brains
    # see the right signature.
    for sp_data in payload.get("species", []):
        sp = Species(
            id=int(sp_data["id"]),
            name=sp_data.get("name", f"sp_{sp_data['id']:04d}"),
            base_color=tuple(sp_data.get("base_color", (180, 180, 180))),
            founder_id=int(sp_data["founder_id"]),
            created_tick=int(sp_data.get("created_tick", 0)),
            signature=np.asarray(sp_data["signature"], dtype=np.float32),
            population_count=0,  # rebuilt by assign() below
        )
        world.species.species[sp.id] = sp
        if sp.id >= world.species._next_id:
            world.species._next_id = sp.id + 1

    for c_data in payload.get("creatures", []):
        cid = int(c_data["id"])
        if cid in genome_lookup:
            values = np.asarray(genome_lookup[cid], dtype=np.float32)
        else:
            inline = c_data.get("genome")
            values = (np.asarray(inline, dtype=np.float32)
                      if inline is not None
                      else np.random.random(GENE_COUNT).astype(np.float32))
        if values.shape[0] < GENE_COUNT:
            extra = np.random.random(GENE_COUNT - values.shape[0]).astype(np.float32)
            values = np.concatenate([values, extra])
        elif values.shape[0] > GENE_COUNT:
            values = values[:GENE_COUNT]

        creature = world.spawn_creature(
            genome=Genome(values),
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

    # Restore RNG state if present (so reruns are reproducible from save).
    rng_state = payload.get("rng_state")
    if rng_state and isinstance(rng_state, dict):
        try:
            simulation.rng.bit_generator.state = rng_state
        except Exception:
            pass

    simulation.world = world
    simulation.world.telemetry = simulation.telemetry
    simulation.stats.reset()
    simulation.stats.update(world)
    if simulation.telemetry is not None:
        simulation.telemetry.emit_event(world.tick, "checkpoint_loaded",
                                        {"creatures": len(payload.get("creatures", []))})
    return True


def list_checkpoints(directory: str = ".") -> List[Dict[str, Any]]:
    """List candidate checkpoints in `directory` based on .genomes.npz pairs."""
    out = []
    try:
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if not os.path.isfile(full):
                continue
            if name.endswith(".genomes.npz") or name.endswith(".world.npz"):
                continue
            # Heuristic: any file with a matching .genomes.npz is a checkpoint.
            if os.path.exists(full + ".genomes.npz"):
                st = os.stat(full)
                out.append({
                    "path": name,
                    "size": st.st_size,
                    "modified": st.st_mtime,
                })
    except OSError:
        pass
    out.sort(key=lambda d: -d["modified"])
    return out
