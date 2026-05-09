"""Central configuration for the ALife simulation.

All tunable constants live here. Avoid scattering magic numbers
across the codebase.
"""

from __future__ import annotations


# --- World ---------------------------------------------------------------
WORLD_WIDTH: int = 3000
WORLD_HEIGHT: int = 3000
TILE_SIZE: int = 3
SPATIAL_HASH_CELL: int = 8

# --- Window / UI ---------------------------------------------------------
UI_PANEL_WIDTH: int = 320
WINDOW_WIDTH: int = WORLD_WIDTH * TILE_SIZE + UI_PANEL_WIDTH
WINDOW_HEIGHT: int = WORLD_HEIGHT * TILE_SIZE
FPS: int = 60
WINDOW_TITLE: str = "ALife Simulation"

# --- Population ---------------------------------------------------------
INITIAL_CREATURES: int = 200
MAX_CREATURES: int = 3000
INITIAL_FOOD: int = 1200
MAX_FOOD: int = 3500
FOOD_SPAWN_PER_TICK: int = 25
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
LOCAL_DENSITY_LIMIT: int = 14            # within REPRODUCTION_DENSITY_RADIUS
REPRODUCTION_DENSITY_RADIUS: float = 6.0

# --- Mutation defaults --------------------------------------------------
DEFAULT_MUTATION_RATE: float = 0.05      # probability per gene
DEFAULT_MUTATION_STRENGTH: float = 0.08  # max delta per gene
HYBRID_MUTATION_BONUS: float = 0.04

# --- Combat --------------------------------------------------------------
COMBAT_RANGE: float = 1.6
ATTACK_RANDOM_FACTOR_MIN: float = 0.7
ATTACK_RANDOM_FACTOR_MAX: float = 1.3
DEFENSE_MODIFIER: float = 0.8
MIN_DAMAGE: float = 0.0
COMBAT_ENERGY_GAIN_FRACTION: float = 0.25  # share of victim energy that winner absorbs

# --- Speciation / clans -------------------------------------------------
SPECIES_DISTANCE_THRESHOLD: float = 0.45  # genome distance above which mating is blocked
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
AGE_DAMAGE_START_FRACTION: float = 0.85   # start dying of old age past this fraction of lifespan
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

# Decoupled main loop: cap on simulation steps the loop will try to run
# in a single rendered frame, regardless of speed multiplier. Prevents the
# UI from freezing when the sim falls behind real time.
MAX_STEPS_PER_FRAME: int = 16

# --- Update intervals (every Nth tick) ----------------------------------
# Cheap things run every tick. Anything that doesn't change behavior much
# tick-to-tick gets throttled.
PERCEPTION_INTERVAL: int = 1
REPRODUCTION_INTERVAL: int = 3
COMBAT_INTERVAL: int = 1
TERRITORY_DECAY_INTERVAL: int = 10
DIPLOMACY_INTERVAL: int = 30
STATISTICS_INTERVAL: int = 15
SPECIES_RESYNC_INTERVAL: int = 250
RENDER_DEBUG_INTERVAL: int = 6

# --- Save / load --------------------------------------------------------
SAVE_PATH: str = "save_state.json"
STATS_EXPORT_PATH: str = "statistics.json"
