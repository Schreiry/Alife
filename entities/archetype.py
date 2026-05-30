"""Creature archetypes, per CLAUDE.md §9.

An archetype is a *derived* tag — it isn't stored in the genome, it's
computed from genome values at spawn. Five archetypes:

  FORAGER   — high food_search_efficiency, low aggression, high curiosity
  PREDATOR  — high aggression / hunting_instinct / attack_power
  SOCIAL    — high cooperation_instinct / social_bonding / leadership
  EXPLORER  — high exploration_drive / curiosity / migration_drive
  HYBRID    — set explicitly when parents are different species

The chosen archetype amplifies the matching brain-facing scalars on the
Creature (already set by attach_phenotype) by small multipliers. That
way `HybridBrain.decide` doesn't need a separate scoring path — the
existing baseline scorer already reads those scalars, but they've been
nudged up to reflect the archetype.

Amplification stays small (≤ +25%) so it shifts behavior style without
breaking baseline survival rules. Per §9: "must not be hardcoded
if-else chaos" — this whole module is a small enum + a derivation
function + a multiplier table.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple

from genetics.genome import Genome


class Archetype(str, Enum):
    FORAGER = "forager"
    PREDATOR = "predator"
    SOCIAL = "social"
    EXPLORER = "explorer"
    HYBRID = "hybrid"


# Per-archetype trait amplifiers. Keys = Creature attribute names set by
# attach_phenotype. Each value is the multiplier applied at archetype
# assignment. Missing keys = no change. Values capped so the archetype
# never raises a normalized scalar above ~1.0.
_BIAS: Dict[Archetype, Dict[str, float]] = {
    Archetype.FORAGER: {
        "food_search_efficiency": 1.20,
        "curiosity": 1.10,
        "fear": 1.05,
        "aggression": 0.80,
    },
    Archetype.PREDATOR: {
        "aggression": 1.20,
        "hunting_instinct": 1.20,
        "fear": 0.80,
        "self_preservation": 0.85,
        "territoriality": 1.10,
    },
    Archetype.SOCIAL: {
        "cooperation": 1.20,
        "social_bonding": 1.20,
        "trust": 1.10,
        "leadership": 1.10,
        "clan_creation_chance_n": 1.15,
        "clan_joining_chance_n": 1.15,
        "altruism": 1.15,
    },
    Archetype.EXPLORER: {
        "curiosity": 1.25,
        "expansion_drive": 1.20,
        "impulsiveness": 1.10,
        "risk_analysis": 0.90,
    },
    Archetype.HYBRID: {
        # Hybrids get a small everything-bump and accept that some traits
        # may conflict — evolution sorts winners out.
        "curiosity": 1.10,
        "aggression": 1.05,
        "cooperation": 1.05,
        "fear": 0.95,
    },
}


def classify(genome: Genome, is_hybrid: bool = False) -> Archetype:
    """Pick the archetype whose signature genes dominate this genome.

    Hybrids (parents from different species) are flagged directly; for
    everyone else we score the four base archetypes and pick the
    maximum. Ties broken by enum order (Forager > Predator > Social >
    Explorer)."""
    if is_hybrid:
        return Archetype.HYBRID

    n = genome.normalized
    forager = (
        0.6 * n("food_search_efficiency")
        + 0.4 * n("curiosity")
        + 0.3 * (1.0 - n("aggression"))
    )
    predator = (
        0.6 * n("aggression")
        + 0.5 * n("hunting_instinct")
        + 0.3 * (1.0 - n("fear"))
    )
    social = (
        0.5 * n("cooperation_instinct")
        + 0.5 * n("social_bonding")
        + 0.3 * n("leadership")
        + 0.2 * n("trust")
    )
    explorer = (
        0.6 * n("curiosity")
        + 0.5 * n("expansion_drive")
        + 0.3 * n("migration_drive")
    )

    best = max(
        ((forager, Archetype.FORAGER),
         (predator, Archetype.PREDATOR),
         (social, Archetype.SOCIAL),
         (explorer, Archetype.EXPLORER)),
        key=lambda t: t[0],
    )
    return best[1]


def amplify_traits(creature, archetype: Archetype) -> None:
    """Multiply the brain-facing scalars on `creature` in place, per the
    archetype's bias table. Caps each adjusted scalar at 1.0 since
    BaselineScoreBrain.score reads many of them as normalized [0..1]."""
    table = _BIAS.get(archetype)
    if not table:
        return
    for attr, mult in table.items():
        current = getattr(creature, attr, None)
        if current is None:
            continue
        new_val = current * mult
        # Cap normalized scalars; raw stats (fertility, retreat_threshold,
        # etc.) are bounded by their genome ranges already so no extra cap.
        if 0.0 <= current <= 1.0:
            new_val = min(1.0, max(0.0, new_val))
        setattr(creature, attr, new_val)
