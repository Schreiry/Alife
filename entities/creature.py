"""Creature: an agent with a genome and a slot in the CreatureStore.

The hot fields (x, y, energy, health, age, alive, mating_cooldown, plus
cached derived stats) live in a numpy array inside the CreatureStore and
are proxied here via properties. The cold fields (genome, clan_id,
species_id, parents, color) stay as plain attributes — they're touched
infrequently and don't benefit from SoA layout.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from genetics.genome import Genome


class Creature:
    __slots__ = (
        "_store", "_idx", "id", "genome",
        "parent_a_id", "parent_b_id", "generation",
        "death_cause", "color", "last_action",
        "rage", "confidence", "archetype",
        # Cached normalized gene values used by the brain scoring.
        "aggression", "fear", "territoriality", "expansion_drive",
        "leadership", "social_bonding", "trust", "cooperation",
        "intelligence", "curiosity", "risk_analysis",
        "self_preservation", "reproduction_drive", "food_search_efficiency",
        "same_species_pref", "outsider_tolerance", "pack_instinct",
        "altruism", "hunting_instinct", "parental_instinct",
        "impulsiveness", "clan_creation_chance_n", "clan_joining_chance_n",
        "incest_avoidance", "mate_selectiveness", "fertility",
        "min_energy_repro_fraction", "min_age_repro", "mating_cooldown_ticks",
        "retreat_threshold", "crit_chance", "dodge_chance",
        "digestion_efficiency", "energy_absorption", "repro_energy_cost",
    )

    def __init__(self, store, idx: int, id_: int, genome: Genome):
        self._store = store
        self._idx = idx
        self.id = id_
        self.genome = genome
        self.parent_a_id: Optional[int] = None
        self.parent_b_id: Optional[int] = None
        self.generation: int = 0
        self.death_cause: Optional[str] = None
        self.color: Tuple[int, int, int] = (180, 180, 180)
        self.last_action: str = "idle"
        self.rage: float = 0.0
        self.confidence: float = 0.5
        self.archetype: str = "forager"  # overwritten by World.spawn_creature
        # Brain-side normalized values are filled by attach_phenotype.

    # ---------- store proxies ------------------------------------------
    @property
    def store_idx(self) -> int:
        return self._idx

    @property
    def x(self) -> float:
        return float(self._store.x[self._idx])

    @x.setter
    def x(self, v: float) -> None:
        self._store.x[self._idx] = v

    @property
    def y(self) -> float:
        return float(self._store.y[self._idx])

    @y.setter
    def y(self, v: float) -> None:
        self._store.y[self._idx] = v

    @property
    def energy(self) -> float:
        return float(self._store.energy[self._idx])

    @energy.setter
    def energy(self, v: float) -> None:
        self._store.energy[self._idx] = v

    @property
    def health(self) -> float:
        return float(self._store.health[self._idx])

    @health.setter
    def health(self, v: float) -> None:
        self._store.health[self._idx] = v

    @property
    def age(self) -> int:
        return int(self._store.age[self._idx])

    @age.setter
    def age(self, v: int) -> None:
        self._store.age[self._idx] = v

    @property
    def mating_cooldown(self) -> int:
        return int(self._store.mating_cooldown[self._idx])

    @mating_cooldown.setter
    def mating_cooldown(self, v: int) -> None:
        self._store.mating_cooldown[self._idx] = v

    @property
    def is_alive(self) -> bool:
        return bool(self._store.alive[self._idx])

    @property
    def alive(self) -> bool:
        return bool(self._store.alive[self._idx])

    @property
    def sex(self) -> int:
        return int(self._store.sex[self._idx])

    @sex.setter
    def sex(self, v: int) -> None:
        self._store.sex[self._idx] = v

    @property
    def species_id(self) -> int:
        return int(self._store.species_id[self._idx])

    @species_id.setter
    def species_id(self, v: int) -> None:
        self._store.species_id[self._idx] = v

    @property
    def clan_id(self) -> Optional[int]:
        v = int(self._store.clan_id[self._idx])
        return None if v < 0 else v

    @clan_id.setter
    def clan_id(self, v: Optional[int]) -> None:
        self._store.clan_id[self._idx] = -1 if v is None else int(v)

    @property
    def is_hybrid(self) -> bool:
        return bool(self._store.is_hybrid[self._idx])

    @is_hybrid.setter
    def is_hybrid(self, v: bool) -> None:
        self._store.is_hybrid[self._idx] = bool(v)

    # Cached derived stats — proxy direct array slots so brain logic that
    # reads e.g. `creature.move_speed` keeps working unchanged.
    @property
    def max_health(self) -> float: return float(self._store.max_health[self._idx])
    @property
    def max_energy(self) -> float: return float(self._store.max_energy[self._idx])
    @property
    def vision_range(self) -> float: return float(self._store.vision_range[self._idx])
    @property
    def move_speed(self) -> float: return float(self._store.move_speed[self._idx])
    @property
    def attack_power_real(self) -> float: return float(self._store.attack_power[self._idx])
    @property
    def defense_power_real(self) -> float: return float(self._store.defense_power[self._idx])
    @property
    def base_energy_cost(self) -> float: return float(self._store.base_energy_cost[self._idx])
    @property
    def move_energy_cost(self) -> float: return float(self._store.move_energy_cost[self._idx])
    @property
    def attack_energy_cost(self) -> float: return float(self._store.attack_energy_cost[self._idx])
    @property
    def starvation_damage(self) -> float: return float(self._store.starvation_damage[self._idx])
    @property
    def regen_rate(self) -> float: return float(self._store.regen_rate[self._idx])
    @property
    def lifespan(self) -> int: return int(self._store.lifespan[self._idx])
    @property
    def aging_speed(self) -> float: return float(self._store.aging_speed[self._idx])

    # ---------- behavior helpers --------------------------------------
    def attach_phenotype(self, rng=None) -> None:
        """Compute cached real-valued stats from the genome and write them
        into the store. Called once at spawn and after any mutation.

        If `gene_expression_noise` > 0, the phenotype is computed from a
        jittered copy of the genome — so genetically-identical siblings
        end up slightly different. The heritable genome itself is NOT
        touched."""
        g = self.genome
        s = self._store
        i = self._idx

        noise = g.normalized("gene_expression_noise")
        if noise > 0.0 and rng is not None:
            from genetics.mutation import expression_noise
            from genetics.genes import GENE_INDEX, GENE_RANGES
            noisy = expression_noise(g.values, rng, noise)

            def real_of(name: str) -> float:
                idx = GENE_INDEX[name]
                lo, hi = GENE_RANGES[idx]
                return lo + (hi - lo) * float(noisy[idx])

            def norm_of(name: str) -> float:
                return float(noisy[GENE_INDEX[name]])
        else:
            real_of = g.real
            norm_of = g.normalized

        s.max_health[i] = real_of("max_health")
        s.max_energy[i] = real_of("energy_capacity")
        s.move_speed[i] = real_of("movement_speed")
        s.vision_range[i] = real_of("vision_range")
        s.attack_power[i] = real_of("attack_power")
        s.defense_power[i] = real_of("defense_power")
        s.base_energy_cost[i] = real_of("base_energy_consumption")
        s.move_energy_cost[i] = real_of("movement_energy_cost")
        s.attack_energy_cost[i] = real_of("attack_energy_cost")
        s.starvation_damage[i] = real_of("starvation_damage_rate")
        s.regen_rate[i] = real_of("regeneration_rate")
        s.lifespan[i] = int(real_of("lifespan"))
        s.aging_speed[i] = real_of("aging_speed")

        # Brain-facing normalized scalars.
        self.aggression = norm_of("aggression")
        self.fear = norm_of("fear")
        self.territoriality = norm_of("territoriality")
        self.expansion_drive = norm_of("expansion_drive")
        self.leadership = norm_of("leadership")
        self.social_bonding = norm_of("social_bonding")
        self.trust = norm_of("trust")
        self.cooperation = norm_of("cooperation_instinct")
        self.intelligence = norm_of("intelligence")
        self.curiosity = norm_of("curiosity")
        self.risk_analysis = norm_of("risk_analysis")
        self.self_preservation = norm_of("self_preservation")
        self.reproduction_drive = norm_of("reproduction_drive")
        self.food_search_efficiency = norm_of("food_search_efficiency")
        self.same_species_pref = norm_of("same_species_preference")
        self.outsider_tolerance = norm_of("outsider_tolerance")
        self.pack_instinct = norm_of("pack_instinct")
        self.altruism = norm_of("altruism")
        self.hunting_instinct = norm_of("hunting_instinct")
        self.parental_instinct = norm_of("parental_instinct")
        self.impulsiveness = norm_of("impulsiveness")
        self.clan_creation_chance_n = norm_of("clan_creation_chance")
        self.clan_joining_chance_n = norm_of("clan_joining_chance")
        self.incest_avoidance = norm_of("incest_avoidance")
        self.mate_selectiveness = norm_of("mate_selectiveness")
        self.fertility = real_of("fertility")
        self.min_energy_repro_fraction = real_of("minimum_energy_for_mating")
        self.min_age_repro = int(real_of("minimum_age_for_mating"))
        self.mating_cooldown_ticks = int(real_of("mating_cooldown"))
        self.retreat_threshold = real_of("retreat_threshold")
        self.crit_chance = real_of("critical_chance")
        self.dodge_chance = real_of("dodge_chance")
        self.digestion_efficiency = real_of("digestion_efficiency")
        self.energy_absorption = real_of("energy_absorption")
        self.repro_energy_cost = real_of("reproduction_energy_cost")

    def kill(self, cause: str) -> None:
        self._store.alive[self._idx] = False
        self._store.health[self._idx] = 0.0
        self.death_cause = cause
