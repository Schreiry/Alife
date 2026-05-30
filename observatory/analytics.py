"""Analytics aggregations for the /analytics research page.

All functions take the live Simulation and run under the SimRunner snapshot
lock (the server wraps them in `with_snapshot`), so they read consistent
arrays. They are intentionally read-only and vectorized where possible:
the SoA store gives us ages/energy/health as numpy arrays; the few things
that live on cold Creature objects (generation, genome) are gathered with a
single Python pass over the alive set.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from genetics.genes import ACTIVE_GENES, GENE_CATALOG, GENE_INDEX


def _hist(values: np.ndarray, lo: float, hi: float, bins: int) -> Dict[str, Any]:
    """Histogram helper returning bin centers + counts as plain lists."""
    if values.size == 0:
        edges = np.linspace(lo, hi, bins + 1)
        centers = (0.5 * (edges[:-1] + edges[1:])).round(3).tolist()
        return {"centers": centers, "counts": [0] * bins, "lo": lo, "hi": hi}
    counts, edges = np.histogram(values, bins=bins, range=(lo, hi))
    centers = 0.5 * (edges[:-1] + edges[1:])
    return {
        "centers": centers.round(3).tolist(),
        "counts": counts.astype(int).tolist(),
        "lo": float(lo),
        "hi": float(hi),
    }


def analytics_snapshot(sim) -> Dict[str, Any]:
    """Population-wide distributions + ecology breakdowns for the dashboard."""
    world = sim.world
    store = world.store
    alive = store.alive
    idx = np.flatnonzero(alive)
    n = int(idx.size)

    if n:
        ages = store.age[idx].astype(np.float64)
        lifespans = store.lifespan[idx].astype(np.float64)
        life_frac = np.divide(ages, np.maximum(1.0, lifespans))
        energy_frac = store.energy[idx] / np.maximum(1.0, store.max_energy[idx])
        health_frac = store.health[idx] / np.maximum(1.0, store.max_health[idx])
        age_hist = _hist(life_frac, 0.0, 1.0, 10)
        energy_hist = _hist(energy_frac, 0.0, 1.0, 12)
        health_hist = _hist(health_frac, 0.0, 1.0, 12)
        mean_age = float(ages.mean())
        mean_life_frac = float(life_frac.mean())
    else:
        age_hist = _hist(np.empty(0), 0.0, 1.0, 10)
        energy_hist = _hist(np.empty(0), 0.0, 1.0, 12)
        health_hist = _hist(np.empty(0), 0.0, 1.0, 12)
        mean_age = 0.0
        mean_life_frac = 0.0

    # Generation distribution lives on the cold Creature objects.
    gen_counts: Dict[int, int] = {}
    hybrids = 0
    for c in world.creatures.values():
        g = int(c.generation)
        gen_counts[g] = gen_counts.get(g, 0) + 1
        if c.is_hybrid:
            hybrids += 1
    gen_sorted = sorted(gen_counts.items())
    generations = {
        "labels": [g for g, _ in gen_sorted],
        "counts": [c for _, c in gen_sorted],
    }

    species = []
    for sp in world.species.species.values():
        if sp.population_count <= 0:
            continue
        species.append({
            "id": sp.id,
            "name": sp.name,
            "color": list(sp.base_color),
            "population": int(sp.population_count),
            "created_tick": int(sp.created_tick),
        })
    species.sort(key=lambda s: -s["population"])

    clans = []
    for cl in world.clans.values():
        clans.append({
            "id": cl.id,
            "name": cl.name,
            "color": list(cl.color),
            "members": len(cl.members),
            "territory": int(cl.territory_count),
            "aggression": round(cl.aggression_level, 3),
        })
    clans.sort(key=lambda c: -c["members"])

    stats = sim.stats
    return {
        "tick": int(world.tick),
        "population": n,
        "food": int(world.food_count()),
        "hybrids": hybrids,
        "mean_age": round(mean_age, 1),
        "mean_life_frac": round(mean_life_frac, 3),
        "age_hist": age_hist,
        "energy_hist": energy_hist,
        "health_hist": health_hist,
        "generations": generations,
        "species": species,
        "clans": clans,
        "death_causes": {
            "starvation": int(stats.deaths_by_starvation),
            "age": int(stats.deaths_by_age),
            "combat": int(stats.deaths_by_combat),
        },
        "deaths_total": int(stats.deaths_total),
        "births_total": int(stats.births_total),
        "generation_max": int(stats.generation_max),
    }


def gene_distribution(
    sim,
    gene_name: str,
    bins: int = 24,
    top_species: int = 4,
) -> Optional[Dict[str, Any]]:
    """Histogram of one gene's normalized value across the live population,
    plus per-species means for the most populous species. Returns None for an
    unknown gene name."""
    if gene_name not in GENE_INDEX:
        return None
    gi = GENE_INDEX[gene_name]

    world = sim.world
    creatures = list(world.creatures.values())
    n = len(creatures)
    if n == 0:
        return {
            "gene": gene_name,
            "active": gene_name in ACTIVE_GENES,
            "count": 0,
            "mean": 0.0,
            "std": 0.0,
            "hist": _hist(np.empty(0), 0.0, 1.0, bins),
            "by_species": [],
        }

    vals = np.fromiter((float(c.genome.values[gi]) for c in creatures), dtype=np.float64, count=n)
    hist = _hist(vals, 0.0, 1.0, bins)

    # Per-species means (top N by population).
    by_sp: Dict[int, List[float]] = {}
    for c, v in zip(creatures, vals):
        by_sp.setdefault(int(c.species_id), []).append(v)
    sp_rows = []
    for sid, vlist in by_sp.items():
        sp = world.species.species.get(sid)
        sp_rows.append({
            "id": sid,
            "name": sp.name if sp is not None else f"sp_{sid}",
            "color": list(sp.base_color) if sp is not None else [150, 150, 150],
            "count": len(vlist),
            "mean": round(float(np.mean(vlist)), 3),
        })
    sp_rows.sort(key=lambda r: -r["count"])

    return {
        "gene": gene_name,
        "active": gene_name in ACTIVE_GENES,
        "count": n,
        "mean": round(float(vals.mean()), 4),
        "std": round(float(vals.std()), 4),
        "hist": hist,
        "by_species": sp_rows[:top_species],
    }


def territory_snapshot(sim, block: int = 5) -> Dict[str, Any]:
    """Downsampled clan-ownership map for the territory/border view layer.

    Read-only and stride-sampled (cheap): we sample owner/strength every
    `block` tiles instead of returning the full WxH grid. This is a pure
    observation layer — it never feeds back into the simulation. Served on
    its own low-cadence endpoint so the 30 Hz live stream stays untouched.

    Layout: `owner`/`strength` are flattened C-order over (cols, rows); cell
    (ix, iy) maps to world tile (ix*block, iy*block) and is at index
    ix*rows + iy.
    """
    world = sim.world
    terr = world.territory
    block = max(1, min(16, int(block)))

    # Block aggregation: per block we keep the *dominant* tile (the one with
    # the highest claim strength). Plain stride sampling aliased small regions
    # into scattered dots; this captures any owned tile inside a block so a
    # clan's holdings read as connected areas.
    bw = (terr.width // block) * block
    bh = (terr.height // block) * block
    cols = bw // block
    rows = bh // block

    def blocks(arr):
        # (bw, bh) -> (cols, rows, block*block)
        return (arr[:bw, :bh]
                .reshape(cols, block, rows, block)
                .transpose(0, 2, 1, 3)
                .reshape(cols, rows, block * block))

    owner_b = blocks(terr.owner)
    strength_b = blocks(terr.strength)
    assim_b = blocks(terr.assimilation)
    conflict_b = blocks(terr.conflict)
    last_b = blocks(terr.last_owner)

    sel = np.argmax(strength_b, axis=2)[:, :, None]   # dominant tile per block

    def pick(a):
        return np.take_along_axis(a, sel, axis=2)[:, :, 0]

    owner = pick(owner_b)
    strength = pick(strength_b)
    assimilation = pick(assim_b)
    conflict = pick(conflict_b)
    last_owner = pick(last_b)

    clans: Dict[int, list] = {}
    for cid in np.unique(owner).tolist():
        if cid < 0:
            continue
        cl = world.clans.get(int(cid))
        clans[int(cid)] = list(cl.color) if cl is not None else [150, 150, 150]

    def flat_round(arr) -> list:
        return np.round(arr, 3).astype(np.float32).ravel(order="C").tolist()

    return {
        "tick": int(world.tick),
        "block": block,
        "cols": int(cols),
        "rows": int(rows),
        "world_w": int(terr.width),
        "world_h": int(terr.height),
        "owner": owner.astype(np.int32).ravel(order="C").tolist(),
        "strength": flat_round(strength),
        "assimilation": flat_round(assimilation),
        "conflict": flat_round(conflict),
        "last_owner": last_owner.astype(np.int32).ravel(order="C").tolist(),
        "clans": clans,
    }


def ecology_snapshot(sim) -> Dict[str, Any]:
    """Coarse resource-ecology field for the heatmap overlay. Flattened
    C-order over (cols, rows): cell (ix, iy) is at index ix*rows + iy and maps
    to world tile (ix*zone, iy*zone). Read-only; never feeds the simulation."""
    world = sim.world
    eco = world.ecology

    def flat(a) -> list:
        return np.round(a, 3).astype(np.float32).ravel(order="C").tolist()

    return {
        "tick": int(world.tick),
        "cols": int(eco.cols),
        "rows": int(eco.rows),
        "zone": int(eco.zone),
        "world_w": int(eco.width),
        "world_h": int(eco.height),
        "fertility": flat(eco.fertility),
        "current_ratio": flat(eco.current / np.maximum(1e-6, eco.capacity)),
        "depletion": flat(eco.depletion),
        "in_famine": bool(world.in_famine),
        "total_biomass": round(eco.total_biomass(), 1),
        "mean_depletion": round(eco.mean_depletion(), 3),
    }


def gene_names() -> Dict[str, Any]:
    """Catalog of gene names grouped by category, with active flags. Lets the
    analytics page build its gene selector without a separate catalog call."""
    cats: Dict[str, List[Dict[str, Any]]] = {}
    for spec in GENE_CATALOG:
        cats.setdefault(spec.category, []).append({
            "name": spec.name,
            "active": spec.name in ACTIVE_GENES,
        })
    return {"categories": cats}
