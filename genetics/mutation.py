"""Tiered mutation operations.

Three intensities + two rare events, per CLAUDE.md §7:

  small mutation       — most common; |delta| up to `strength`
  medium mutation      — larger jump; |delta| up to 2.5 × strength
  large mutation       — rare; gene reset toward a fresh random value
  dormant activation   — gated by `dormant_gene_chance`; a previously
                          near-zero value snaps into the mid-range,
                          simulating an expressed-from-dormant gene
  expression noise     — applied at PHENOTYPE READ time (see
                          `expression_noise()`), not here; this module
                          touches only the heritable values

`genetic_stability` (0..1) attenuates the destructive tiers (medium /
large) without affecting small jitter, so a stable individual still
drifts but rarely catastrophically.
"""

from __future__ import annotations

import numpy as np

from .genes import GENE_INDEX
from .genome import Genome


_MEDIUM_FRACTION = 0.18
_LARGE_FRACTION = 0.03
_DORMANT_THRESHOLD = 0.05


def mutate_inplace(
    genome: Genome,
    rng: np.random.Generator,
    rate: float,
    strength: float,
    stability: float = 0.5,
) -> int:
    """Apply tiered mutation to `genome` in place. Returns the number of
    genes that changed value."""
    if rate <= 0.0 or strength <= 0.0:
        return 0

    values = genome.values
    n = values.shape[0]
    hit = rng.random(n) < rate
    if not hit.any():
        return 0

    # Stability dampens the heavy tiers, never the small ones.
    s = float(np.clip(stability, 0.0, 1.0))
    medium_p = _MEDIUM_FRACTION * (1.0 - 0.6 * s)
    large_p = _LARGE_FRACTION * (1.0 - 0.8 * s)

    tier_roll = rng.random(n)
    medium = hit & (tier_roll < medium_p)
    large = hit & (tier_roll >= medium_p) & (tier_roll < medium_p + large_p)
    small = hit & ~medium & ~large

    if small.any():
        d = (rng.random(int(small.sum())).astype(np.float32) * 2.0 - 1.0) * strength
        values[small] = np.clip(values[small] + d, 0.0, 1.0)
    if medium.any():
        d = (rng.random(int(medium.sum())).astype(np.float32) * 2.0 - 1.0) * (strength * 2.5)
        values[medium] = np.clip(values[medium] + d, 0.0, 1.0)
    if large.any():
        # Pull toward a fresh random value with strong weight — a real
        # "saltation" event but bounded so it never sets >1 or <0.
        target = rng.random(int(large.sum())).astype(np.float32)
        values[large] = np.clip(0.4 * values[large] + 0.6 * target, 0.0, 1.0)

    # Dormant activation — applies only to genes currently sitting near 0,
    # gated by the per-genome dormant_gene_chance gene.
    dormant_p = float(values[GENE_INDEX["dormant_gene_chance"]]) * rate
    if dormant_p > 0.0:
        dormant_mask = (values < _DORMANT_THRESHOLD) & (rng.random(n) < dormant_p)
        if dormant_mask.any():
            # Wake up to a mid-range value with some jitter.
            wake = 0.45 + rng.random(int(dormant_mask.sum())).astype(np.float32) * 0.3
            values[dormant_mask] = np.clip(wake, 0.0, 1.0)
            hit = hit | dormant_mask

    return int(hit.sum())


def expression_noise(values: np.ndarray, rng: np.random.Generator,
                     noise_gene: float) -> np.ndarray:
    """Return a NEW array of expressed values (does not mutate heritable
    genome). `noise_gene` is the genome's `gene_expression_noise` value:
    at 0.0 nothing changes, at 1.0 expression jitters up to ±0.05."""
    if noise_gene <= 0.0:
        return values
    amplitude = 0.05 * float(noise_gene)
    delta = (rng.random(values.shape[0]).astype(np.float32) * 2.0 - 1.0) * amplitude
    return np.clip(values + delta, 0.0, 1.0)
