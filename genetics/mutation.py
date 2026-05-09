"""Mutation operations for genomes."""

from __future__ import annotations

import numpy as np

from .genome import Genome


def mutate_inplace(
    genome: Genome,
    rng: np.random.Generator,
    rate: float,
    strength: float,
) -> int:
    """Mutate genome in place. Returns number of genes that changed."""
    if rate <= 0.0 or strength <= 0.0:
        return 0

    mask = rng.random(genome.values.shape) < rate
    if not mask.any():
        return 0

    deltas = (rng.random(genome.values.shape).astype(np.float32) * 2.0 - 1.0) * strength
    genome.values[mask] = np.clip(genome.values[mask] + deltas[mask], 0.0, 1.0)
    return int(mask.sum())
