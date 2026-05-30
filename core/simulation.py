"""Simulation tick driver.

The hot path:

1. Spawn food up to budget.
2. Vectorized "what changes for everyone": age, base energy, hunger,
   aging damage, mating cooldown, regen — all over numpy arrays.
3. Rebuild spatial grids once, off the freshly-updated positions.
4. Per-creature brain pass (perception + decision + action handler).
5. Apply movement-bound clamps in one numpy pass.
6. Sweep newly-dead creatures.
7. Throttled subsystems: territory decay, diplomacy, species resync,
   statistics — each on its own interval.

The Brain handlers are still Python (they're per-event branchy logic);
the heavy O(N) numerical work lives in numpy.
"""

from __future__ import annotations

import time
from typing import List

import numpy as np

import config
from behavior.brain_interface import make_brain
from behavior.diplomacy import step_diplomacy
from core.world import World
from data.profiler import PerformanceProfiler
from data.statistics import Statistics
from data.telemetry import Telemetry
from genetics.genome import Genome


class Simulation:
    def __init__(
        self,
        seed: int | None = None,
        telemetry: Telemetry | None = None,
    ):
        self.seed = seed
        self.rng: np.random.Generator = np.random.default_rng(seed)
        self.world: World = World(self.rng)
        self.brain = make_brain(getattr(config, "BRAIN_KIND", "baseline"), self.rng)
        self.stats: Statistics = Statistics()
        self.profiler: PerformanceProfiler = PerformanceProfiler()
        self.telemetry: Telemetry | None = telemetry
        self.paused: bool = config.DEFAULT_PAUSED
        self.speed_index: int = config.DEFAULT_SPEED_INDEX

        # Watchdog print throttle: a slow tick can fire every tick under a
        # heavy population, which floods the console unreadably. We print at
        # most once per WATCHDOG_LOG_INTERVAL_S and fold the suppressed count
        # into the next line.
        self._last_watchdog_print: float = 0.0
        self._watchdog_suppressed: int = 0

        # Cumulative counters used by telemetry delta-emission. World holds
        # the raw totals; Simulation tracks the last value emitted so we
        # send {birth_delta, death_delta} rather than full series.
        self._last_births_seen: int = 0
        self._last_deaths_seen: int = 0

        self.world.telemetry = self.telemetry
        self._populate_initial_state()
        if self.telemetry is not None:
            self.telemetry.emit_event(0, "sim_started", {
                "seed": seed,
                "initial_pop": config.INITIAL_CREATURES,
                "initial_food": config.INITIAL_FOOD,
                "world": {"w": config.WORLD_WIDTH, "h": config.WORLD_HEIGHT},
            })

    # ---------- bootstrap ---------------------------------------------------
    def _populate_initial_state(self) -> None:
        # Seed initial food through the ecology field so it lands in fertile
        # cells, not uniformly everywhere.
        self.world.ecology.spawn_food(self.world, config.INITIAL_FOOD, self.rng)
        self._seed_initial_creatures()

    def _seed_initial_creatures(self) -> None:
        """Seed the starting population as `INITIAL_SPECIES` founder lineages.
        Each founder owns a distinct point in signature space; its members
        share that signature (with small jitter) but keep independently random
        non-signature genes. Offspring inherit the founder species; cross-
        founder contact is what later produces hybrids."""
        from genetics.species import make_founder_signature, write_signature

        k = max(1, int(config.INITIAL_SPECIES))
        founders = [make_founder_signature(self.rng) for _ in range(k)]

        species_ids: list[int] = []
        for sig in founders:
            template = Genome.random(self.rng)
            write_signature(template.values, sig)
            sid = self.world.species.found_species(
                template.values,
                founder_id=self.world._next_creature_id,
                tick=self.world.tick,
                base_color=template.to_color(),
            )
            species_ids.append(sid)

        for i in range(config.INITIAL_CREATURES):
            kf = i % k
            genome = Genome.random(self.rng)
            write_signature(genome.values, founders[kf],
                            rng=self.rng, noise=config.FOUNDER_SIGNATURE_NOISE)
            x = float(self.rng.uniform(0, config.WORLD_WIDTH))
            y = float(self.rng.uniform(0, config.WORLD_HEIGHT))
            sex = int(self.rng.integers(0, 2))
            self.world.spawn_creature(genome, x, y, sex,
                                      parent_species_id=species_ids[kf])

    # ---------- public API --------------------------------------------------
    def reset(self) -> None:
        self.world = World(self.rng)
        self.world.telemetry = self.telemetry
        self.stats.reset()
        self._last_births_seen = 0
        self._last_deaths_seen = 0
        self._populate_initial_state()
        if self.telemetry is not None:
            self.telemetry.emit_event(0, "sim_reset", None)

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def speed_up(self) -> None:
        self.speed_index = min(len(config.SPEED_LEVELS) - 1, self.speed_index + 1)

    def speed_down(self) -> None:
        self.speed_index = max(0, self.speed_index - 1)

    @property
    def steps_per_frame(self) -> int:
        return config.SPEED_LEVELS[self.speed_index]

    def update(self, max_steps: int = config.MAX_STEPS_PER_FRAME) -> int:
        """Run as many sim ticks as the speed multiplier asks, capped by
        `max_steps` so the UI doesn't freeze if the sim is heavy."""
        if self.paused:
            return 0
        n = min(self.steps_per_frame, max_steps)
        for _ in range(n):
            self._tick()
        return n

    # ---------- one tick ----------------------------------------------------
    def _tick(self) -> None:
        prof = self.profiler
        prof.start_section("tick")
        tick_wall_start = time.perf_counter()
        world = self.world
        world.tick += 1

        # Per-tick gates read by Brain.step. Set them here so brain code
        # stays a pure function of (creature, world, flags).
        world.allow_reproduce_tick = (world.tick % config.REPRODUCTION_INTERVAL == 0)
        world.allow_attack_tick = (world.tick % config.COMBAT_INTERVAL == 0)

        # 1. Resource ecology ------------------------------------------
        # Regrow biomass + accumulate grazing/depletion (slow field), then
        # spawn food drawn from the fertility field, then check famine/bloom.
        prof.mark_phase("ecology")
        prof.start_section("ecology")
        if world.tick % config.ECOLOGY_INTERVAL == 0:
            world.ecology.step(world.store)
        self._spawn_food_pulse()
        self._check_famine(world)
        prof.end_section("ecology")

        # 2. Vectorized passive updates --------------------------------
        prof.mark_phase("vec_passive")
        prof.start_section("vec_passive")
        self._apply_passive_updates(world)
        prof.end_section("vec_passive")

        # 3. Sweep deaths from passive (starvation / age) -------------
        prof.mark_phase("sweep_passive")
        prof.start_section("sweep_passive")
        self._sweep_dead(world)
        prof.end_section("sweep_passive")

        # 4. Rebuild spatial grids -------------------------------------
        prof.mark_phase("grid_rebuild")
        prof.start_section("grid_rebuild")
        world.rebuild_grids()
        prof.end_section("grid_rebuild")

        # 5. Brain pass (per-creature) ---------------------------------
        prof.mark_phase("brain")
        prof.start_section("brain")
        creatures = list(world.creatures.values())
        brain = self.brain
        for creature in creatures:
            if not creature.is_alive:
                continue
            brain.step(creature, world)
        prof.end_section("brain")

        # 6. Sweep deaths from brain (combat) -------------------------
        prof.mark_phase("sweep_brain")
        prof.start_section("sweep_brain")
        self._clamp_positions_vectorized(world)
        self._sweep_dead(world)
        prof.end_section("sweep_brain")

        # 6b. Anti-extinction reseed (immigration floor) --------------
        self._reseed_if_needed(world)

        # 7. Throttled subsystems -------------------------------------
        if world.tick % config.TERRITORY_DECAY_INTERVAL == 0:
            prof.mark_phase("territory_decay")
            prof.start_section("territory_decay")
            world.territory.decay(config.CLAN_TERRITORY_DECAY)
            world.territory.update_dynamics()
            world.territory_dirty = True
            prof.end_section("territory_decay")

        if world.tick % config.CLAN_UPDATE_INTERVAL == 0:
            prof.mark_phase("clan_update")
            prof.start_section("clan_update")
            self._refresh_clan_territory_counts()
            prof.end_section("clan_update")

        if world.tick % config.DIPLOMACY_INTERVAL == 0:
            prof.mark_phase("diplomacy")
            prof.start_section("diplomacy")
            step_diplomacy(world)
            prof.end_section("diplomacy")

        if world.tick % config.SPECIES_RESYNC_INTERVAL == 0:
            prof.mark_phase("species_resync")
            prof.start_section("species_resync")
            self._resync_species()
            prof.end_section("species_resync")

        # 8. Stats (cheap counters now; deep aggregates inside) -------
        if world.tick % config.STATISTICS_INTERVAL == 0:
            prof.mark_phase("stats")
            prof.start_section("stats")
            self.stats.update(world)
            prof.end_section("stats")
            self._emit_telemetry_rollup(world)
        else:
            self.stats.update_cheap(world)

        # 9. Compact dead agents — sparse SoA cleanup pulse. Free-list
        # already keeps holes reusable, so this is mostly a telemetry
        # checkpoint and an opportunity to release any incidental Python
        # references the brain accumulated.
        if world.tick > 0 and world.tick % config.COMPACT_INTERVAL == 0:
            if self.telemetry is not None:
                self.telemetry.emit_event(world.tick, "compact_pulse", {
                    "pop": world.population(),
                    "free_slots": len(world.store._free),
                })

        # 10. Auto checkpoint (cheap; saves to side file so manual saves
        # aren't overwritten). Disabled when CHECKPOINT_INTERVAL == 0.
        if (config.CHECKPOINT_INTERVAL > 0
                and world.tick > 0
                and world.tick % config.CHECKPOINT_INTERVAL == 0):
            try:
                from data import save_load
                info = save_load.save(world, self.stats,
                                       path="checkpoint_auto.json",
                                       rng=self.rng)
                if self.telemetry is not None:
                    self.telemetry.emit_event(world.tick, "checkpoint_auto", info)
            except Exception as exc:
                if self.telemetry is not None:
                    self.telemetry.emit_event(world.tick, "checkpoint_failed",
                                              {"error": repr(exc)})

        # Profiler counters --------------------------------------------
        prof.set("creatures", world.population())
        prof.set("food", world.food_count())
        prof.set("clans", len(world.clans))
        prof.set("births", world.births_total)
        prof.set("deaths", world.deaths_total)
        prof.end_section("tick")

        # Watchdog: emit one-line diagnostic on slow ticks. Caller-visible
        # via stderr; observatory also exposes it through /api/status.
        tick_ms = (time.perf_counter() - tick_wall_start) * 1000.0
        warn = prof.note_tick(tick_ms, config.WATCHDOG_TICK_MS_THRESHOLD)
        if warn:
            now = time.perf_counter()
            if now - self._last_watchdog_print >= config.WATCHDOG_LOG_INTERVAL_S:
                import sys
                if self._watchdog_suppressed:
                    warn = f"{warn} (+{self._watchdog_suppressed} similar suppressed)"
                print(warn, file=sys.stderr)
                self._last_watchdog_print = now
                self._watchdog_suppressed = 0
            else:
                self._watchdog_suppressed += 1

    # ---------- vectorized helpers ----------------------------------------
    def _apply_passive_updates(self, world: World) -> None:
        s = world.store
        alive = s.alive
        if not alive.any():
            return

        # age, mating cooldown.
        s.age[alive] += 1
        # mating cooldown: clamped to >= 0.
        np.subtract(s.mating_cooldown, 1, out=s.mating_cooldown, where=alive)
        np.maximum(s.mating_cooldown, 0, out=s.mating_cooldown)

        # base energy cost.
        np.subtract(s.energy, s.base_energy_cost, out=s.energy, where=alive)

        # starvation: energy <= 0 → health -= starvation_damage.
        starving = alive & (s.energy <= 0.0)
        if starving.any():
            s.energy[starving] = 0.0
            s.health[starving] -= s.starvation_damage[starving]

        # aging damage past lifespan threshold.
        old_threshold = (s.lifespan.astype(np.float32) * config.AGE_DAMAGE_START_FRACTION).astype(np.int32)
        old = alive & (s.age > old_threshold)
        if old.any():
            s.health[old] -= config.AGE_DAMAGE_PER_TICK * s.aging_speed[old]
        # explicit cap on ages past lifespan: kill them.
        too_old = alive & (s.age > s.lifespan)

        # Mark deaths.
        starved_dead = alive & (s.health <= 0.0) & starving
        aged_dead = alive & ((s.health <= 0.0) | too_old) & ~starved_dead

        # Apply death masks: log cause via Creature objects (rare path).
        for idx in np.flatnonzero(starved_dead):
            cre = world.creature_by_idx[idx]
            if cre is not None:
                cre.kill("starvation")
                world.deaths_total += 1
                world.deaths_by_starvation += 1
                world.emit("death", {"id": cre.id, "cause": "starvation",
                                     "age": cre.age, "generation": cre.generation})
        for idx in np.flatnonzero(aged_dead):
            cre = world.creature_by_idx[idx]
            if cre is not None:
                cre.kill("age")
                world.deaths_total += 1
                world.deaths_by_age += 1
                world.emit("death", {"id": cre.id, "cause": "age",
                                     "age": cre.age, "generation": cre.generation})

        # Slow regen if at rest and energy ample.
        regen_mask = alive & (s.health < s.max_health) & (s.energy > s.max_energy * 0.4)
        if regen_mask.any():
            new_h = s.health[regen_mask] + s.regen_rate[regen_mask] * 0.5
            s.health[regen_mask] = np.minimum(new_h, s.max_health[regen_mask])

    def _clamp_positions_vectorized(self, world: World) -> None:
        s = world.store
        np.clip(s.x, 0.0, config.WORLD_WIDTH - 1, out=s.x)
        np.clip(s.y, 0.0, config.WORLD_HEIGHT - 1, out=s.y)

    def _sweep_dead(self, world: World) -> None:
        # Compose dead-but-still-attached list (alive=False but creature
        # still in dict). We collect ids first, then remove.
        dead_ids: List[int] = []
        for cid, creature in world.creatures.items():
            if not creature.is_alive:
                dead_ids.append(cid)
        for cid in dead_ids:
            world.remove_creature(cid)

    def _reseed_if_needed(self, world: World) -> None:
        """Immigration floor: if the population collapses below
        MIN_POPULATION_FLOOR, inject a small cluster of fresh random
        creatures near the population centroid so the world never reaches the
        absorbing "only food remains" state. Sexes are alternated so the
        cluster can actually reproduce. Disabled when the floor is 0."""
        floor = config.MIN_POPULATION_FLOOR
        if floor <= 0 or world.population() >= floor:
            return
        cx = world.centroid_x
        cy = world.centroid_y
        r = config.RESEED_CLUSTER_RADIUS
        spawned = 0
        for i in range(config.RESEED_COUNT):
            if world.population() >= config.MAX_CREATURES:
                break
            genome = Genome.random(self.rng)
            x = float(np.clip(cx + self.rng.uniform(-r, r), 0.0, config.WORLD_WIDTH - 1))
            y = float(np.clip(cy + self.rng.uniform(-r, r), 0.0, config.WORLD_HEIGHT - 1))
            sex = i % 2
            if world.spawn_creature(genome, x, y, sex) is not None:
                spawned += 1
        if spawned and self.telemetry is not None:
            self.telemetry.emit_event(world.tick, "reseed", {
                "count": spawned,
                "pop_after": world.population(),
            })

    def _spawn_food_pulse(self) -> None:
        self.world.ecology.spawn_food(self.world, config.FOOD_SPAWN_PER_TICK, self.rng)

    def _check_famine(self, world: World) -> None:
        """Emit world-level famine/bloom events when the live food supply
        crosses thresholds. Debounced by world.in_famine so each transition
        fires once, leaving a clean history trail."""
        food = world.food_count()
        if not world.in_famine and food < config.MAX_FOOD * config.ECOLOGY_FAMINE_FRACTION:
            world.in_famine = True
            world.emit("famine", {
                "food": food,
                "biomass": round(world.ecology.total_biomass(), 1),
                "depletion": round(world.ecology.mean_depletion(), 3),
            })
        elif world.in_famine and food > config.MAX_FOOD * config.ECOLOGY_BLOOM_FRACTION:
            world.in_famine = False
            world.emit("resource_bloom", {
                "food": food,
                "biomass": round(world.ecology.total_biomass(), 1),
            })

    def _emit_telemetry_rollup(self, world: World) -> None:
        """Emit aggregated metrics + delta events. Runs on STATISTICS_INTERVAL."""
        tel = self.telemetry
        if tel is None:
            return
        tick = world.tick
        birth_delta = world.births_total - self._last_births_seen
        death_delta = world.deaths_total - self._last_deaths_seen
        self._last_births_seen = world.births_total
        self._last_deaths_seen = world.deaths_total

        s = self.stats
        tel.emit_metric(tick, "population", float(s.population))
        tel.emit_metric(tick, "food", float(s.food))
        tel.emit_metric(tick, "biomass", float(world.ecology.total_biomass()))
        tel.emit_metric(tick, "depletion", float(world.ecology.mean_depletion()))
        tel.emit_metric(tick, "species", float(s.species_count))
        tel.emit_metric(tick, "clans", float(s.clan_count))
        tel.emit_metric(tick, "births_total", float(s.births_total))
        tel.emit_metric(tick, "deaths_total", float(s.deaths_total))
        tel.emit_metric(tick, "births_delta", float(birth_delta))
        tel.emit_metric(tick, "deaths_delta", float(death_delta))
        tel.emit_metric(tick, "deaths_starvation", float(s.deaths_by_starvation))
        tel.emit_metric(tick, "deaths_age", float(s.deaths_by_age))
        tel.emit_metric(tick, "deaths_combat", float(s.deaths_by_combat))
        tel.emit_metric(tick, "avg_energy", float(s.avg_energy))
        tel.emit_metric(tick, "avg_health", float(s.avg_health))
        tel.emit_metric(tick, "avg_aggression", float(s.avg_aggression))
        tel.emit_metric(tick, "avg_intelligence", float(s.avg_intelligence))
        tel.emit_metric(tick, "avg_strength", float(s.avg_strength))
        tel.emit_metric(tick, "avg_age", float(s.avg_age))
        tel.emit_metric(tick, "hybrids", float(s.hybrid_total))
        tel.emit_metric(tick, "generation_max", float(s.generation_max))
        tel.emit_metric(tick, "tick_ms", float(self.profiler.last_tick_ms))

        if birth_delta:
            tel.emit_event(tick, "births_window", {"count": birth_delta})
        if death_delta:
            tel.emit_event(tick, "deaths_window", {"count": death_delta})

    def _refresh_clan_territory_counts(self) -> None:
        # One bincount pass beats N independent np.count_nonzero scans.
        counts = self.world.territory.territory_counts_by_clan()
        for clan in self.world.clans.values():
            clan.territory_count = counts.get(clan.id, 0)

    def _resync_species(self) -> None:
        world = self.world
        genomes: dict[int, list[Genome]] = {}
        rows: dict[int, list] = {}
        for creature in world.creatures.values():
            sid = creature.species_id
            genomes.setdefault(sid, []).append(creature.genome)
            rows.setdefault(sid, []).append(
                (creature.id, creature.genome.values, creature.color)
            )
        world.species.update_signatures(genomes)

        # Cladogenesis: split species that have pulled apart into two breeding
        # clusters. detect_splits creates the new species + fixes counts; we
        # just retag the moved creatures (the setter writes through to the SoA
        # store) and leave a history event per new species.
        splits = world.species.detect_splits(rows, world.tick)
        if not splits:
            return
        per_new: dict[int, list] = {}
        pos_for_new: dict[int, tuple] = {}
        for cid, old_sid, new_sid in splits:
            creature = world.creatures.get(cid)
            if creature is not None:
                creature.species_id = new_sid
                pos_for_new.setdefault(new_sid, (float(creature.x), float(creature.y)))
            per_new.setdefault(new_sid, []).append(old_sid)
        for new_sid, old_ids in per_new.items():
            sp = world.species.species.get(new_sid)
            px, py = pos_for_new.get(new_sid, (world.centroid_x, world.centroid_y))
            # A new species emerging is "something new" — mark where it split off.
            world.push_signal("species_emerged", px, py, {
                "species": new_sid,
                "name": sp.name if sp is not None else f"sp_{new_sid:04d}",
                "parent_species": old_ids[0],
                "founder_members": len(old_ids),
            })
