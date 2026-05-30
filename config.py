"""Central configuration for the ALife simulation.

All tunable constants live here. Avoid scattering magic numbers
across the codebase.
"""

from __future__ import annotations


# --- World ---------------------------------------------------------------
# 300x300 = 90k tiles. Fits in any cache, gives visible density, keeps
# TerritoryGrid under 1 MB. Tune up later only after profiler confirms
# the new bottleneck is *not* density-related.
WORLD_WIDTH: int = 300
WORLD_HEIGHT: int = 300
TILE_SIZE: int = 4
SPATIAL_HASH_CELL: int = 8

# --- Window / UI (pygame fallback only) ---------------------------------
UI_PANEL_WIDTH: int = 320
WINDOW_WIDTH: int = WORLD_WIDTH * TILE_SIZE + UI_PANEL_WIDTH
WINDOW_HEIGHT: int = WORLD_HEIGHT * TILE_SIZE
FPS: int = 60
WINDOW_TITLE: str = "ALife Simulation"

# --- Population ---------------------------------------------------------
# Hard cap raised to 1000. The whole food economy below is scaled in
# proportion (~2.2x over the old 450 regime) so the carrying-capacity
# equilibrium sits near, but a little under, the cap — the world fills up
# and stays dense without the cap forcing a permanent boom-bust crash.
# Energy budget that fixes these numbers: a creature spends ~0.1 (base) +
# ~0.16/tile (move) per tick and gains ~28 energy per food eaten, so the
# spawn budget must replace what ~1000 grazers burn between meals.
INITIAL_CREATURES: int = 320
MAX_CREATURES: int = 1000
INITIAL_FOOD: int = 1100
MAX_FOOD: int = 3400          # hard cap on simultaneous food points (memory guard)
FOOD_SPAWN_PER_TICK: int = 34 # per-tick spawn budget, gated by zone biomass
FOOD_ENERGY: float = 30.0

# --- Resource ecology (food as a field, not an infinite spawner) --------
# Food is the fruit of a coarse fertility field. The world is divided into
# ECOLOGY_ZONE-sized cells; each cell has static `fertility`, a `capacity`
# (= fertility * ECOLOGY_ZONE_CAPACITY, in energy units) and a regenerating
# `current` biomass. Food points are spawned drawing from `current` in
# proportion to it, so fertile, ungrazed cells grow food while grazed/barren
# ones run dry — creating growth centers, migration sources and contested
# borders. Grazing pressure (creature density per cell) raises `depletion`,
# which suppresses regrowth (recovery delay) and decays when the cell is left
# alone. All cell math is vectorized over the (cols x rows) grid.
ECOLOGY_ZONE: int = 15                  # tile size of one ecology cell -> 20x20 cells at 300px
ECOLOGY_ZONE_CAPACITY: float = 180.0    # max standing biomass energy per cell at fertility 1.0
                                        # (doubled to feed the 1000-creature cap: regrowth
                                        # throughput = cells * (cap-current) * regen must exceed
                                        # FOOD_SPAWN_PER_TICK * FOOD_ENERGY energy/tick)
ECOLOGY_FERTILITY_FLOOR: float = 0.25   # even the poorest cell has some fertility (raised so
                                        # poor zones aren't death-traps -> less spatial starvation)
ECOLOGY_REGEN_RATE: float = 0.05        # fraction of (capacity-current) regrown per ecology tick
ECOLOGY_INTERVAL: int = 1               # run regen/grazing/depletion every Nth tick
ECOLOGY_DEPLETION_PER_CREATURE: float = 0.012  # depletion added per creature in a cell per ecology tick
ECOLOGY_DEPLETION_DECAY: float = 0.94          # per-ecology-tick decay of depletion toward 0
# Famine / bloom history events: emitted when the live food-point count
# crosses these fractions of MAX_FOOD (debounced by the in_famine flag).
ECOLOGY_FAMINE_FRACTION: float = 0.20
ECOLOGY_BLOOM_FRACTION: float = 0.55

# Anti-extinction floor: if the live population drops below this, the world
# reseeds RESEED_COUNT fresh random creatures (immigration) near the current
# population centroid. Guarantees the simulation never reaches the absorbing
# "only food remains" state. Set MIN_POPULATION_FLOOR = 0 to disable.
# Raised well above the Allee trap: a population that busts down to a few
# dozen survivors spread across a 300x300 world can't re-find mates and stalls
# forever (observed: stuck at ~23 with food plentiful, no births, no
# evolution). Reseeding a viable breeding cluster before that point keeps the
# world recovering from deep busts instead of flatlining.
MIN_POPULATION_FLOOR: int = 60
RESEED_COUNT: int = 16
RESEED_CLUSTER_RADIUS: float = 10.0

# --- Creature defaults --------------------------------------------------
START_ENERGY_FRACTION: float = 0.7
START_HEALTH_FRACTION: float = 1.0
NEWBORN_ENERGY_FRACTION: float = 0.5
NEWBORN_HEALTH_FRACTION: float = 1.0

# --- Reproduction --------------------------------------------------------
MIN_AGE_FOR_MATING: int = 80
MATING_COOLDOWN_TICKS: int = 120
MIN_ENERGY_FRACTION_FOR_MATING: float = 0.55
REPRODUCTION_DISTANCE: float = 2.5
OFFSPRING_BASE_MIN: int = 1
OFFSPRING_BASE_MAX: int = 3
LOCAL_DENSITY_LIMIT: int = 14
REPRODUCTION_DENSITY_RADIUS: float = 6.0
# When a reproduction-ready creature sees no mate within its vision range,
# it searches this much wider radius (via the spatial grid) for the nearest
# opposite-sex creature to move toward. Defeats the Allee trap in a large,
# sparse world where survivors would otherwise never find each other.
MATE_SEEK_RADIUS: float = 48.0

# --- Mutation defaults --------------------------------------------------
DEFAULT_MUTATION_RATE: float = 0.05
DEFAULT_MUTATION_STRENGTH: float = 0.08
HYBRID_MUTATION_BONUS: float = 0.04

# --- Combat --------------------------------------------------------------
COMBAT_RANGE: float = 1.6
ATTACK_RANDOM_FACTOR_MIN: float = 0.7
ATTACK_RANDOM_FACTOR_MAX: float = 1.3
DEFENSE_MODIFIER: float = 0.8
MIN_DAMAGE: float = 0.0
COMBAT_ENERGY_GAIN_FRACTION: float = 0.25

# --- Speciation / clans -------------------------------------------------
# Founder/immigrant assignment threshold (mean-abs over the SPECIATION
# signature subset, not all 170 genes). A parentless creature joins the
# nearest species within this distance, else founds a new one. Offspring do
# NOT use this — they inherit the parent species and only split via
# cladogenesis (see below).
SPECIES_DISTANCE_THRESHOLD: float = 0.45

# Cladogenesis (emergent speciation by within-species divergence). On each
# species resync we project a species' member signatures onto their principal
# axis of variance, find the widest gap, and — if the two resulting subgroups'
# centroids are separated by more than SPECIATION_SPLIT_THRESHOLD (in mean-abs
# over the signature subset) and BOTH subgroups have at least
# SPECIATION_MIN_SPLIT_POP members — split the diverged subgroup off as a new
# species. This is the only way new species arise from a single ancestor: the
# population must actually pull apart into two breeding clusters.
SPECIATION_SPLIT_THRESHOLD: float = 0.16
SPECIATION_MIN_SPLIT_POP: int = 24
# Hard cap so runaway splitting can't exhaust ids / memory. Observation cap;
# tune up once the dynamics are confirmed stable.
MAX_SPECIES: int = 24

# Founder lineages seeded at world start. A flat, well-mixed world has no force
# that pulls one ancestor's gene pool apart (verified: pure single-ancestor
# emergence stays one species indefinitely), so we plant initial lineage
# diversity here. Only the *starting* species set is seeded; contact,
# compatibility, hybridization and further cladogenesis all remain emergent.
# Set to 1 to start from a single ancestor.
INITIAL_SPECIES: int = 3
# Within-lineage jitter applied to the signature genes of each founder's
# members, so a founder lineage is a tight cluster, not identical clones.
FOUNDER_SIGNATURE_NOISE: float = 0.04

# --- Hybridization (cross-species mating) -------------------------------
# A pairing of two *different* species must clear an extra social-acceptance
# gate on top of the normal biological (genetic-distance) and spatial
# (must-be-adjacent) gates. This keeps hybrids rare and meaningful instead of
# flooding the moment two species coexist. acceptance =
#   0.5*(mixed_species_acceptance_a + _b)
#   + CROSS_SPECIES_TOLERANCE_WEIGHT * 0.5*(outsider_tolerance_a + _b)
#   - CROSS_SPECIES_PREFERENCE_PENALTY * 0.5*(same_species_preference_a + _b)
#   - CROSS_SPECIES_FEAR_WEIGHT * 0.5*(fear_a + fear_b)
# The pair may hybridize only if acceptance >= CROSS_SPECIES_MATE_THRESHOLD.
CROSS_SPECIES_MATE_THRESHOLD: float = 0.80
CROSS_SPECIES_TOLERANCE_WEIGHT: float = 0.6
CROSS_SPECIES_PREFERENCE_PENALTY: float = 0.7
CROSS_SPECIES_FEAR_WEIGHT: float = 0.3
CLAN_CREATE_COOLDOWN: int = 200
CLAN_MIN_LEADERSHIP: float = 0.55
CLAN_MIN_ENERGY_FRACTION: float = 0.6
CLAN_JOIN_DISTANCE: float = 8.0
CLAN_TERRITORY_GAIN: float = 0.15
CLAN_TERRITORY_DECAY: float = 0.005
# A claiming creature stamps a disk of this radius (tiles), not a single tile,
# so members of the same clan build contiguous, merging regions instead of
# scattered one-tile enclaves. Kept modest because the stamp runs inside the
# per-creature brain loop; the disk geometry is precomputed once (cached
# stencil) so each claim is just a window slice + boolean masks.
CLAN_TERRITORY_CLAIM_RADIUS: int = 3
# Territory "maturation" dynamics. These drive the border-type view layer
# (occupied -> assimilating -> stable) and the contest pressure map. They are
# OBSERVATION/visualization state only — they do not change creature behavior.
# Applied once per TERRITORY_DECAY_INTERVAL tick.
TERRITORY_ASSIMILATION_RATE: float = 0.04   # how fast held ground becomes "stable"
TERRITORY_CONFLICT_DECAY: float = 0.85       # per-update decay of contest pressure
TERRITORY_CONFLICT_BUMP: float = 0.5         # pressure added when a tile is contested/captured
DIPLOMACY_DECAY: float = 0.0005
DIPLOMACY_KILL_PENALTY: float = 0.18
DIPLOMACY_COEXIST_BONUS: float = 0.0008
WAR_THRESHOLD: float = -0.5
ALLIANCE_THRESHOLD: float = 0.5
# Relation must climb back past this for a declared war to *end* (hysteresis
# so a war doesn't flicker on/off around WAR_THRESHOLD).
WAR_END_THRESHOLD: float = -0.2

# --- Border friction (what actually STARTS wars) ------------------------
# Without this, relations only dropped on a cross-clan kill — but a kill needs
# an already-hostile relation to even perceive the enemy (perception only flags
# foreign clans with rel < -0.3 as enemies). That chicken-and-egg left the world
# permanently at peace. Border friction breaks it: clans whose territories touch
# erode each other's relation every DIPLOMACY_INTERVAL in proportion to the
# shared-border length, scaled by militancy (clan ideology) and global resource
# stress (mean depletion / famine). Sustained bordering -> hostility -> the
# perception gate opens -> skirmishes -> kills -> war. Neighbors who stop
# touching drift back toward peace via the coexistence bonus.
BORDER_FRICTION_RATE: float = 0.017       # relation drop/step at full contact, before
                                          # militancy/stress scaling (see step_diplomacy)
BORDER_FRICTION_SATURATION: float = 28.0  # bordering tiles for full contact factor

# --- Map signals (transient positioned event markers) -------------------
# The world keeps a small ring buffer of recent "something happened HERE"
# markers (war declared, new clan, new species, alliance). The live snapshot
# ships the recent ones with coords and the renderer fades them by age.
SIGNAL_TTL_TICKS: int = 1500
SIGNAL_BUFFER_MAX: int = 64

# --- Aging / death ------------------------------------------------------
# Lowered so a brief, local food shortage doesn't wipe an entire cohort at
# once (which fed the boom-bust extinction). Gene starvation_damage_rate
# still scales per-creature around this baseline.
STARVATION_DAMAGE_PER_TICK: float = 0.4
AGE_DAMAGE_START_FRACTION: float = 0.85
AGE_DAMAGE_PER_TICK: float = 0.4

# --- Movement -----------------------------------------------------------
MOVEMENT_ENERGY_COST_BASE: float = 0.05
IDLE_ENERGY_COST_BASE: float = 0.02

# --- Rendering colors (R, G, B) -----------------------------------------
COLOR_BG: tuple[int, int, int] = (12, 14, 20)
COLOR_FOOD: tuple[int, int, int] = (90, 200, 90)
COLOR_PANEL: tuple[int, int, int] = (24, 26, 32)
COLOR_PANEL_BORDER: tuple[int, int, int] = (60, 64, 72)
COLOR_TEXT: tuple[int, int, int] = (220, 220, 230)
COLOR_TEXT_DIM: tuple[int, int, int] = (160, 160, 170)
COLOR_TEXT_ACCENT: tuple[int, int, int] = (240, 200, 100)
COLOR_DEAD_TEXT: tuple[int, int, int] = (200, 80, 80)

# --- Simulation control --------------------------------------------------
SPEED_LEVELS: tuple[int, ...] = (1, 2, 3, 5, 8, 12)
DEFAULT_SPEED_INDEX: int = 0
DEFAULT_PAUSED: bool = False

# Cap on simulation steps per rendered frame. Prevents UI freeze when sim
# is heavy: drop ticks rather than block the event loop.
MAX_STEPS_PER_FRAME: int = 16

# --- Update intervals (every Nth tick) ----------------------------------
# Cheap things every tick. Expensive things throttled. These constants are
# now actively read by Simulation._tick (previously they were defined but
# unused, which is half the freeze story).
PERCEPTION_INTERVAL: int = 1        # spec §15: every tick
REPRODUCTION_INTERVAL: int = 5      # spec §15: every 5 ticks
COMBAT_INTERVAL: int = 2            # spec §15: every 2 ticks
TERRITORY_DECAY_INTERVAL: int = 10  # spec §15
STATISTICS_INTERVAL: int = 15       # spec §15
CLAN_UPDATE_INTERVAL: int = 30      # spec §15 (clan housekeeping)
DIPLOMACY_INTERVAL: int = 60        # spec §15
COMPACT_INTERVAL: int = 200         # spec §15 (telemetry pulse)
CHECKPOINT_INTERVAL: int = 1000     # spec §15 (auto-save every N ticks)
SPECIES_RESYNC_INTERVAL: int = 250
RENDER_DEBUG_INTERVAL: int = 6

# --- Brain --------------------------------------------------------------
# "baseline" — handcrafted scoring rules (default, stable)
# "hybrid"   — baseline scoring + archetype-driven bias
# "neural"   — placeholder; currently falls back to baseline
BRAIN_KIND: str = "hybrid"

# --- Watchdog -----------------------------------------------------------
# If a single tick exceeds WATCHDOG_TICK_MS_THRESHOLD, profiler emits a
# one-line diagnostic dump (slowest section + counters). Disabled at 0.
WATCHDOG_TICK_MS_THRESHOLD: float = 80.0
# Watchdog diagnostics are printed at most once per this many seconds; the
# count of suppressed warnings in between is folded into the next line. This
# stops an unreadable per-tick flood when the sim is consistently heavy.
WATCHDOG_LOG_INTERVAL_S: float = 5.0

# --- Save / load --------------------------------------------------------
SAVE_PATH: str = "save_state.json"
STATS_EXPORT_PATH: str = "statistics.json"

# --- Observatory (browser UI) -------------------------------------------
OBSERVATORY_HOST: str = "127.0.0.1"
OBSERVATORY_PORT: int = 8765
OBSERVATORY_WS_HZ: float = 30.0     # snapshot pushes per second (client interpolates between them)
OBSERVATORY_SIM_HZ: float = 60.0    # target simulation ticks per second (headless)
# How often the sim thread rebuilds the published snapshot (dict + JSON).
# The WebSocket just forwards the latest prebuilt JSON, so neither the sim
# lock nor JSON encoding ever runs on the asyncio event loop.
SNAPSHOT_HZ: float = 30.0
