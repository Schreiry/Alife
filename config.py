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
INITIAL_CREATURES: int = 140
MAX_CREATURES: int = 800
INITIAL_FOOD: int = 500
MAX_FOOD: int = 1500
FOOD_SPAWN_PER_TICK: int = 12
FOOD_ENERGY: float = 30.0

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
SPECIES_DISTANCE_THRESHOLD: float = 0.45
CLAN_CREATE_COOLDOWN: int = 200
CLAN_MIN_LEADERSHIP: float = 0.55
CLAN_MIN_ENERGY_FRACTION: float = 0.6
CLAN_JOIN_DISTANCE: float = 8.0
CLAN_TERRITORY_GAIN: float = 0.15
CLAN_TERRITORY_DECAY: float = 0.005
DIPLOMACY_DECAY: float = 0.0005
DIPLOMACY_KILL_PENALTY: float = 0.18
DIPLOMACY_COEXIST_BONUS: float = 0.0008
WAR_THRESHOLD: float = -0.5
ALLIANCE_THRESHOLD: float = 0.5

# --- Aging / death ------------------------------------------------------
STARVATION_DAMAGE_PER_TICK: float = 0.6
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

# --- Save / load --------------------------------------------------------
SAVE_PATH: str = "save_state.json"
STATS_EXPORT_PATH: str = "statistics.json"

# --- Observatory (browser UI) -------------------------------------------
OBSERVATORY_HOST: str = "127.0.0.1"
OBSERVATORY_PORT: int = 8765
OBSERVATORY_WS_HZ: float = 20.0     # snapshot pushes per second
OBSERVATORY_SIM_HZ: float = 60.0    # target simulation ticks per second (headless)
