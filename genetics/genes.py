"""Definitions of the 170-gene catalog.

Every gene stores a normalized value in [0.0, 1.0]. The catalog maps the
gene name to its real-world conversion range so derived stats can be
computed without scattering magic numbers across the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class GeneSpec:
    name: str
    real_min: float
    real_max: float
    category: str


# Order matters: it defines the index of each gene inside Genome.values.
# Adding a new gene = append a GeneSpec entry. Existing genome arrays remain
# valid (extra slots will be filled with random values during loading).
GENE_CATALOG: List[GeneSpec] = [
    # A. Physical
    GeneSpec("body_size",              0.4,   2.0, "physical"),
    GeneSpec("muscle_mass",            0.3,   2.0, "physical"),
    GeneSpec("bone_density",           0.3,   1.5, "physical"),
    GeneSpec("max_health",            40.0, 200.0, "physical"),
    GeneSpec("regeneration_rate",      0.0,   0.6, "physical"),
    GeneSpec("movement_speed",         0.5,   4.0, "physical"),
    GeneSpec("acceleration",           0.2,   1.5, "physical"),
    GeneSpec("stamina",               20.0, 200.0, "physical"),
    GeneSpec("energy_capacity",       60.0, 240.0, "physical"),
    GeneSpec("hunger_resistance",      0.0,   1.0, "physical"),
    GeneSpec("cold_resistance",        0.0,   1.0, "physical"),
    GeneSpec("heat_resistance",        0.0,   1.0, "physical"),
    GeneSpec("poison_resistance",      0.0,   1.0, "physical"),
    GeneSpec("disease_resistance",     0.0,   1.0, "physical"),
    GeneSpec("vision_range",           4.0,  18.0, "physical"),
    GeneSpec("hearing_range",          2.0,  16.0, "physical"),
    GeneSpec("smell_range",            2.0,  14.0, "physical"),
    GeneSpec("fertility_strength",     0.1,   1.0, "physical"),
    GeneSpec("pregnancy_cost",         0.1,   0.5, "physical"),
    GeneSpec("birth_energy_cost",     10.0,  60.0, "physical"),
    GeneSpec("lifespan",             500.0,5000.0, "physical"),
    GeneSpec("aging_speed",            0.5,   2.0, "physical"),
    GeneSpec("physical_stability",     0.0,   1.0, "physical"),
    GeneSpec("wound_resistance",       0.0,   1.0, "physical"),
    GeneSpec("carrying_capacity",      0.0,  10.0, "physical"),

    # B. Metabolic
    GeneSpec("base_energy_consumption", 0.02, 0.20, "metabolic"),
    GeneSpec("movement_energy_cost",    0.02, 0.30, "metabolic"),
    GeneSpec("attack_energy_cost",      0.5,  3.0,  "metabolic"),
    GeneSpec("reproduction_energy_cost",10.0, 80.0, "metabolic"),
    GeneSpec("digestion_efficiency",    0.4,  1.4,  "metabolic"),
    GeneSpec("food_search_efficiency",  0.0,  1.0,  "metabolic"),
    GeneSpec("starvation_damage_rate",  0.2,  1.5,  "metabolic"),
    GeneSpec("energy_absorption",       0.5,  1.6,  "metabolic"),
    GeneSpec("sleep_need",              0.0,  1.0,  "metabolic"),
    GeneSpec("fatigue_growth",          0.0,  1.0,  "metabolic"),
    GeneSpec("fatigue_recovery",        0.0,  1.0,  "metabolic"),
    GeneSpec("resource_greed",          0.0,  1.0,  "metabolic"),
    GeneSpec("food_storage_ability",    0.0,  1.0,  "metabolic"),
    GeneSpec("water_need",              0.0,  1.0,  "metabolic"),
    GeneSpec("dehydration_resistance",  0.0,  1.0,  "metabolic"),
    GeneSpec("metabolism_speed",        0.5,  1.8,  "metabolic"),
    GeneSpec("rest_efficiency",         0.0,  1.0,  "metabolic"),
    GeneSpec("immune_energy_cost",      0.0,  1.0,  "metabolic"),
    GeneSpec("growth_energy_cost",      0.0,  1.0,  "metabolic"),
    GeneSpec("survival_threshold",      0.05, 0.4,  "metabolic"),

    # C. Intelligence / perception
    GeneSpec("intelligence",            0.0, 1.0, "intellect"),
    GeneSpec("memory_capacity",         0.0, 1.0, "intellect"),
    GeneSpec("learning_speed",          0.0, 1.0, "intellect"),
    GeneSpec("decision_depth",          0.0, 1.0, "intellect"),
    GeneSpec("curiosity",               0.0, 1.0, "intellect"),
    GeneSpec("risk_analysis",           0.0, 1.0, "intellect"),
    GeneSpec("pattern_recognition",     0.0, 1.0, "intellect"),
    GeneSpec("planning_ability",        0.0, 1.0, "intellect"),
    GeneSpec("exploration_drive",       0.0, 1.0, "intellect"),
    GeneSpec("innovation_chance",       0.0, 1.0, "intellect"),
    GeneSpec("tool_usage_potential",    0.0, 1.0, "intellect"),
    GeneSpec("social_prediction",       0.0, 1.0, "intellect"),
    GeneSpec("enemy_prediction",        0.0, 1.0, "intellect"),
    GeneSpec("territory_memory",        0.0, 1.0, "intellect"),
    GeneSpec("mate_selection_logic",    0.0, 1.0, "intellect"),
    GeneSpec("food_location_memory",    0.0, 1.0, "intellect"),
    GeneSpec("threat_memory",           0.0, 1.0, "intellect"),
    GeneSpec("clan_loyalty_memory",     0.0, 1.0, "intellect"),
    GeneSpec("betrayal_memory",         0.0, 1.0, "intellect"),
    GeneSpec("navigation_skill",        0.0, 1.0, "intellect"),
    GeneSpec("adaptability",            0.0, 1.0, "intellect"),
    GeneSpec("patience",                0.0, 1.0, "intellect"),
    GeneSpec("impulsiveness",           0.0, 1.0, "intellect"),
    GeneSpec("strategic_thinking",      0.0, 1.0, "intellect"),
    GeneSpec("problem_solving",         0.0, 1.0, "intellect"),

    # D. Instincts
    GeneSpec("reproduction_drive",      0.0, 1.0, "instinct"),
    GeneSpec("self_preservation",       0.0, 1.0, "instinct"),
    GeneSpec("aggression",              0.0, 1.0, "instinct"),
    GeneSpec("fear",                    0.0, 1.0, "instinct"),
    GeneSpec("territoriality",          0.0, 1.0, "instinct"),
    GeneSpec("pack_instinct",           0.0, 1.0, "instinct"),
    GeneSpec("loneliness_tolerance",    0.0, 1.0, "instinct"),
    GeneSpec("dominance_drive",         0.0, 1.0, "instinct"),
    GeneSpec("submission_tendency",     0.0, 1.0, "instinct"),
    GeneSpec("migration_drive",         0.0, 1.0, "instinct"),
    GeneSpec("parental_instinct",       0.0, 1.0, "instinct"),
    GeneSpec("revenge_instinct",        0.0, 1.0, "instinct"),
    GeneSpec("protection_instinct",     0.0, 1.0, "instinct"),
    GeneSpec("hunting_instinct",        0.0, 1.0, "instinct"),
    GeneSpec("hiding_instinct",         0.0, 1.0, "instinct"),
    GeneSpec("cooperation_instinct",    0.0, 1.0, "instinct"),
    GeneSpec("curiosity_instinct",      0.0, 1.0, "instinct"),
    GeneSpec("comfort_seeking",         0.0, 1.0, "instinct"),
    GeneSpec("conflict_avoidance",      0.0, 1.0, "instinct"),
    GeneSpec("expansion_drive",         0.0, 1.0, "instinct"),

    # E. Social
    GeneSpec("trust",                   0.0, 1.0, "social"),
    GeneSpec("empathy",                 0.0, 1.0, "social"),
    GeneSpec("loyalty",                 0.0, 1.0, "social"),
    GeneSpec("betrayal_chance",         0.0, 1.0, "social"),
    GeneSpec("leadership",              0.0, 1.0, "social"),
    GeneSpec("obedience",               0.0, 1.0, "social"),
    GeneSpec("diplomacy",               0.0, 1.0, "social"),
    GeneSpec("negotiation_skill",       0.0, 1.0, "social"),
    GeneSpec("social_bonding",          0.0, 1.0, "social"),
    GeneSpec("clan_creation_chance",    0.0, 1.0, "social"),
    GeneSpec("clan_joining_chance",     0.0, 1.0, "social"),
    GeneSpec("hierarchy_acceptance",    0.0, 1.0, "social"),
    GeneSpec("hierarchy_resistance",    0.0, 1.0, "social"),
    GeneSpec("altruism",                0.0, 1.0, "social"),
    GeneSpec("selfishness",             0.0, 1.0, "social"),
    GeneSpec("group_defense_priority",  0.0, 1.0, "social"),
    GeneSpec("outsider_tolerance",      0.0, 1.0, "social"),
    GeneSpec("same_species_preference", 0.0, 1.0, "social"),
    GeneSpec("mixed_species_acceptance",0.0, 1.0, "social"),
    GeneSpec("alliance_preference",     0.0, 1.0, "social"),

    # F. Combat
    GeneSpec("attack_power",            2.0, 30.0, "combat"),
    GeneSpec("defense_power",           0.0, 20.0, "combat"),
    GeneSpec("dodge_chance",            0.0,  0.5, "combat"),
    GeneSpec("attack_speed",            0.5,  2.0, "combat"),
    GeneSpec("critical_chance",         0.0,  0.3, "combat"),
    GeneSpec("intimidation",            0.0,  1.0, "combat"),
    GeneSpec("pain_tolerance",          0.0,  1.0, "combat"),
    GeneSpec("retreat_threshold",       0.05, 0.6, "combat"),
    GeneSpec("rage_growth",             0.0,  1.0, "combat"),
    GeneSpec("calmness_under_attack",   0.0,  1.0, "combat"),
    GeneSpec("revenge_priority",        0.0,  1.0, "combat"),
    GeneSpec("group_attack_bonus",      0.0,  1.0, "combat"),
    GeneSpec("solo_fight_confidence",   0.0,  1.0, "combat"),
    GeneSpec("ambush_chance",           0.0,  0.5, "combat"),
    GeneSpec("territory_defense_bonus", 0.0,  1.0, "combat"),
    GeneSpec("enemy_memory_strength",   0.0,  1.0, "combat"),
    GeneSpec("weapon_like_behavior",    0.0,  1.0, "combat"),
    GeneSpec("combat_learning",         0.0,  1.0, "combat"),
    GeneSpec("injury_penalty_resistance",0.0, 1.0, "combat"),
    GeneSpec("victory_confidence_gain", 0.0,  0.4, "combat"),

    # G. Reproduction
    GeneSpec("fertility",               0.1,  1.0, "reproduction"),
    GeneSpec("mate_selectiveness",      0.0,  1.0, "reproduction"),
    GeneSpec("attraction_strength",     0.0,  1.0, "reproduction"),
    GeneSpec("genetic_compatibility_range",0.1,1.0,"reproduction"),
    GeneSpec("minimum_energy_for_mating",0.3, 0.85,"reproduction"),
    GeneSpec("minimum_age_for_mating",  40.0, 300.0,"reproduction"),
    GeneSpec("offspring_count_min",     1.0,  3.0, "reproduction"),
    GeneSpec("offspring_count_max",     1.0,  5.0, "reproduction"),
    GeneSpec("offspring_care_duration", 0.0,200.0, "reproduction"),
    GeneSpec("parental_energy_investment",0.0, 0.5,"reproduction"),
    GeneSpec("pair_bond_strength",      0.0,  1.0, "reproduction"),
    GeneSpec("mating_cooldown",        60.0,300.0, "reproduction"),
    GeneSpec("pregnancy_duration",     30.0,150.0, "reproduction"),
    GeneSpec("child_survival_bonus",    0.0,  1.0, "reproduction"),
    GeneSpec("incest_avoidance",        0.0,  1.0, "reproduction"),
    GeneSpec("hybridization_chance",    0.0,  1.0, "reproduction"),
    GeneSpec("mutation_inheritance_strength",0.0,1.0,"reproduction"),
    GeneSpec("dominant_gene_preference",0.0,  1.0, "reproduction"),
    GeneSpec("reproductive_risk_tolerance",0.0,1.0,"reproduction"),
    GeneSpec("mate_protection_drive",   0.0,  1.0, "reproduction"),

    # H. Mutation / stability
    GeneSpec("mutation_rate",           0.005, 0.20, "mutation"),
    GeneSpec("mutation_strength",       0.01,  0.25, "mutation"),
    GeneSpec("mutation_resistance",     0.0,   1.0,  "mutation"),
    GeneSpec("beneficial_mutation_chance",0.0, 1.0, "mutation"),
    GeneSpec("harmful_mutation_chance", 0.0,   1.0,  "mutation"),
    GeneSpec("gene_expression_noise",   0.0,   1.0,  "mutation"),
    GeneSpec("dormant_gene_chance",     0.0,   1.0,  "mutation"),
    GeneSpec("new_trait_chance",        0.0,   1.0,  "mutation"),
    GeneSpec("genetic_stability",       0.0,   1.0,  "mutation"),
    GeneSpec("hybrid_instability",      0.0,   1.0,  "mutation"),

    # I. Appearance / identity
    GeneSpec("color_r",                 0.0, 1.0, "appearance"),
    GeneSpec("color_g",                 0.0, 1.0, "appearance"),
    GeneSpec("color_b",                 0.0, 1.0, "appearance"),
    GeneSpec("pattern_type",            0.0, 1.0, "appearance"),
    GeneSpec("pattern_intensity",       0.0, 1.0, "appearance"),
    GeneSpec("body_shape",              0.0, 1.0, "appearance"),
    GeneSpec("size_visual_modifier",    0.6, 1.6, "appearance"),
    GeneSpec("glow_or_marking",         0.0, 1.0, "appearance"),
    GeneSpec("species_signature",       0.0, 1.0, "appearance"),
    GeneSpec("clan_color_affinity",     0.0, 1.0, "appearance"),
]


GENE_COUNT: int = len(GENE_CATALOG)
GENE_INDEX: Dict[str, int] = {spec.name: i for i, spec in enumerate(GENE_CATALOG)}
GENE_RANGES: Tuple[Tuple[float, float], ...] = tuple(
    (spec.real_min, spec.real_max) for spec in GENE_CATALOG
)


def real_value(name: str, normalized: float) -> float:
    """Convert a normalized gene value (0..1) into its real-world scale."""
    idx = GENE_INDEX[name]
    lo, hi = GENE_RANGES[idx]
    return lo + (hi - lo) * normalized


def gene_index(name: str) -> int:
    return GENE_INDEX[name]


def clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
