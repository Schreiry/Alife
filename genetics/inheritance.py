"""Cross two parent genomes into a child genome with mutation applied."""

from __future__ import annotations

from typing import Tuple

import numpy as np

from config import (
    DEFAULT_MUTATION_RATE,
    DEFAULT_MUTATION_STRENGTH,
    HYBRID_MUTATION_BONUS,
)

from .genome import Genome
from .mutation import mutate_inplace


def crossover(
    parent_a: Genome,
    parent_b: Genome,
    rng: np.random.Generator,
    is_hybrid: bool = False,
) -> Tuple[Genome, int]:
    """Produce a child genome from two parents and apply mutation.

    Each gene is a weighted average of both parents, with the weight
    drawn per-gene in [0.35, 0.65] so traits jitter around the midpoint
    rather than always landing on it. Mutation rate/strength come from
    the parents' own mutation genes (averaged), with a hybrid bonus.
    Returns (child_genome, number_of_mutated_genes).
    """
    weights_a = rng.uniform(0.35, 0.65, size=parent_a.values.shape).astype(np.float32)
    weights_b = 1.0 - weights_a
    blended = parent_a.values * weights_a + parent_b.values * weights_b

    child = Genome(blended)

    rate = max(
        0.001,
        0.5 * (parent_a.real("mutation_rate") + parent_b.real("mutation_rate"))
        - 0.5
        * (parent_a.normalized("mutation_resistance")
           + parent_b.normalized("mutation_resistance"))
        * DEFAULT_MUTATION_RATE,
    )
    strength = max(
        0.005,
        0.5 * (parent_a.real("mutation_strength") + parent_b.real("mutation_strength")),
    )
    if is_hybrid:
        rate = min(0.5, rate + HYBRID_MUTATION_BONUS)
        strength = min(0.5, strength + HYBRID_MUTATION_BONUS)

    # Fall back to defaults if parents have degenerate mutation genes.
    if rate < 1e-4:
        rate = DEFAULT_MUTATION_RATE
    if strength < 1e-4:
        strength = DEFAULT_MUTATION_STRENGTH

    mutated = mutate_inplace(child, rng, rate, strength)
    return child, mutated
