"""Crossover two parent genomes into a child genome, then mutate.

  child_gene = a_gene * w_a + b_gene * w_b      (w_a + w_b == 1.0)

A per-gene weight is drawn in [0.35, 0.65] so children jitter around the
midpoint, not always landing on it. A *dominance coefficient* nudges the
result toward whichever parent has the more pronounced trait (further
from 0.5), with strength controlled by each parent's own
`dominant_gene_preference` gene.

Mutation rate / strength derive from the parents' mutation genes
(averaged), with `mutation_resistance` reducing the rate and
`hybrid_instability` (per-individual) plus the global HYBRID bonus
increasing it for cross-species pairings. `genetic_stability` is passed
into `mutate_inplace` to dampen the destructive tiers.
"""

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
    Returns (child_genome, number_of_genes_mutated)."""
    a = parent_a.values
    b = parent_b.values

    weights_a = rng.uniform(0.35, 0.65, size=a.shape).astype(np.float32)
    weights_b = 1.0 - weights_a

    # Dominance: parents with stronger `dominant_gene_preference` push
    # their more-pronounced traits through. Magnitude = how far the gene
    # is from 0.5; the more extreme value wins a bit more weight.
    dom_a = parent_a.normalized("dominant_gene_preference")
    dom_b = parent_b.normalized("dominant_gene_preference")
    if dom_a > 0.0 or dom_b > 0.0:
        extremity_a = np.abs(a - 0.5)
        extremity_b = np.abs(b - 0.5)
        # `bias` ∈ [-1, 1]: +1 means A's value is far more extreme; -1 means B's.
        diff = extremity_a - extremity_b
        denom = extremity_a + extremity_b + 1e-6
        bias = diff / denom
        # Half the parents' average dominance preference scales the shift.
        shift = bias * (0.5 * (dom_a + dom_b)) * 0.25
        weights_a = np.clip(weights_a + shift.astype(np.float32), 0.0, 1.0)
        weights_b = 1.0 - weights_a

    blended = a * weights_a + b * weights_b
    child = Genome(blended)

    # Mutation rate from parents' genes, dampened by mutation_resistance.
    resistance = 0.5 * (parent_a.normalized("mutation_resistance")
                        + parent_b.normalized("mutation_resistance"))
    rate = max(
        0.001,
        0.5 * (parent_a.real("mutation_rate") + parent_b.real("mutation_rate"))
        - resistance * DEFAULT_MUTATION_RATE,
    )
    strength = max(
        0.005,
        0.5 * (parent_a.real("mutation_strength") + parent_b.real("mutation_strength")),
    )

    # Hybridity bonus: global constant + per-individual hybrid_instability gene.
    if is_hybrid:
        hybrid_gene_avg = 0.5 * (
            parent_a.normalized("hybrid_instability")
            + parent_b.normalized("hybrid_instability")
        )
        rate = min(0.5, rate + HYBRID_MUTATION_BONUS + 0.05 * hybrid_gene_avg)
        strength = min(0.5, strength + HYBRID_MUTATION_BONUS + 0.05 * hybrid_gene_avg)

    if rate < 1e-4:
        rate = DEFAULT_MUTATION_RATE
    if strength < 1e-4:
        strength = DEFAULT_MUTATION_STRENGTH

    # Stability is the child's own genetic_stability (averaged from parents
    # via blend above).
    stability = float(child.normalized("genetic_stability"))
    mutated = mutate_inplace(child, rng, rate, strength, stability=stability)
    return child, mutated
