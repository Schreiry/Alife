"""pyBioSim-style controlled experiment runs.

An experiment is a thin wrapper around Simulation: same engine, fixed
parameters, headless, returns a result dict suitable for JSON dump.

Built-in scenarios:
  * survival_arena   — fixed starting pop, no food refill; measure
                       half-life and last survivor lineage.
  * genetic_drift    — long run, statistics every CHECKPOINT_INTERVAL;
                       export gene-mean trajectories per category.
  * benchmark        — pure throughput test; report ticks-per-second
                       across pop sizes.

Each scenario yields a `dict` with: name, ticks, elapsed_s, tps,
final_population, summary metrics, and (when applicable) `lineages`
listing the top genealogies that survived to the end.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any, Callable, Dict, Optional

import numpy as np

import config


def _make_sim(seed: Optional[int] = None, telemetry=None):
    from core.simulation import Simulation
    return Simulation(seed=seed, telemetry=telemetry)


def survival_arena(ticks: int = 2000, seed: int = 0,
                   telemetry=None) -> Dict[str, Any]:
    """Cut off food entirely; record births=0, watch the die-off curve."""
    saved_spawn = config.FOOD_SPAWN_PER_TICK
    config.FOOD_SPAWN_PER_TICK = 0
    try:
        sim = _make_sim(seed=seed, telemetry=telemetry)
        if telemetry is not None:
            telemetry.emit_event(0, "experiment_start", {"name": "survival_arena", "ticks": ticks})
        pop_history = []
        t0 = time.perf_counter()
        for _ in range(ticks):
            sim._tick()
            if sim.world.tick % 25 == 0:
                pop_history.append((sim.world.tick, sim.world.population()))
            if sim.world.population() == 0:
                break
        elapsed = time.perf_counter() - t0
        # Compute half-life.
        initial = pop_history[0][1] if pop_history else config.INITIAL_CREATURES
        half_life_tick = None
        for tick, pop in pop_history:
            if pop <= initial / 2:
                half_life_tick = tick
                break
        # Surviving lineages: count by parent_a generation depth.
        surv_lineage = Counter()
        for c in sim.world.creatures.values():
            surv_lineage[c.parent_a_id] += 1
        top_lineages = surv_lineage.most_common(5)

        return {
            "name": "survival_arena",
            "ticks": sim.world.tick,
            "elapsed_s": round(elapsed, 3),
            "tps": round(sim.world.tick / max(1e-6, elapsed), 1),
            "initial_population": initial,
            "final_population": sim.world.population(),
            "half_life_tick": half_life_tick,
            "pop_history": pop_history,
            "top_lineages": [{"parent_a_id": p, "descendants": c}
                             for p, c in top_lineages],
            "deaths_by_starvation": int(sim.world.deaths_by_starvation),
            "deaths_by_age": int(sim.world.deaths_by_age),
        }
    finally:
        config.FOOD_SPAWN_PER_TICK = saved_spawn


def genetic_drift(ticks: int = 3000, seed: int = 0,
                  telemetry=None) -> Dict[str, Any]:
    """Run a normal world, sample gene means by category every 100 ticks."""
    from genetics.genes import GENE_CATALOG

    sim = _make_sim(seed=seed, telemetry=telemetry)
    if telemetry is not None:
        telemetry.emit_event(0, "experiment_start", {"name": "genetic_drift", "ticks": ticks})
    cat_index = {}
    for i, g in enumerate(GENE_CATALOG):
        cat_index.setdefault(g.category, []).append(i)

    samples = []
    t0 = time.perf_counter()
    for _ in range(ticks):
        sim._tick()
        if sim.world.tick % 100 == 0:
            world = sim.world
            row = {"tick": world.tick, "pop": world.population(),
                   "clans": len(world.clans), "species": sim.stats.species_count}
            if world.creatures:
                # Stack genomes once.
                stacked = np.stack([c.genome.values for c in world.creatures.values()])
                for cat, idxs in cat_index.items():
                    row[f"mean_{cat}"] = float(stacked[:, idxs].mean())
            samples.append(row)
    elapsed = time.perf_counter() - t0
    return {
        "name": "genetic_drift",
        "ticks": sim.world.tick,
        "elapsed_s": round(elapsed, 3),
        "tps": round(sim.world.tick / max(1e-6, elapsed), 1),
        "final_population": sim.world.population(),
        "samples": samples,
    }


def benchmark(ticks: int = 2000, seed: int = 0,
              telemetry=None) -> Dict[str, Any]:
    """Pure throughput. Reports per-section timings."""
    sim = _make_sim(seed=seed, telemetry=telemetry)
    t0 = time.perf_counter()
    for _ in range(ticks):
        sim._tick()
    elapsed = time.perf_counter() - t0
    sections = {k: round(v, 3) for k, v in sim.profiler.snapshot().items()}
    return {
        "name": "benchmark",
        "ticks": sim.world.tick,
        "elapsed_s": round(elapsed, 3),
        "tps": round(sim.world.tick / max(1e-6, elapsed), 1),
        "final_population": sim.world.population(),
        "section_avg_ms": sections,
    }


SCENARIOS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "survival_arena": survival_arena,
    "genetic_drift": genetic_drift,
    "benchmark": benchmark,
}


def run_experiment(name: str, ticks: int = 2000, seed: int = 0,
                   out_path: Optional[str] = None) -> Dict[str, Any]:
    if name not in SCENARIOS:
        raise ValueError(f"unknown experiment '{name}'; "
                         f"choose from {list(SCENARIOS)}")
    result = SCENARIOS[name](ticks=ticks, seed=seed)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    return result
