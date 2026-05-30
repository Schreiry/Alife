"""Genome: a numpy-backed array of 170 normalized gene values.

The Genome is the single source of truth for an individual's heritable
state. Functions that live elsewhere (inheritance.crossover,
mutation.mutate_inplace, rendering.colors.genome_to_color) are also
exposed here as instance methods so callers can write the spec-natural
`child = a.inherit_from(b, rng)` instead of remembering where each helper
lives. The underlying implementations are *not* duplicated — the methods
delegate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Tuple

import numpy as np

from .genes import GENE_CATALOG, GENE_COUNT, GENE_INDEX, GENE_RANGES, clamp01

if TYPE_CHECKING:
    from rendering.colors import Color


class Genome:
    __slots__ = ("values",)

    def __init__(self, values: np.ndarray):
        if values.shape != (GENE_COUNT,):
            raise ValueError(
                f"Genome must have {GENE_COUNT} values, got {values.shape}"
            )
        self.values = np.clip(values.astype(np.float32, copy=False), 0.0, 1.0)

    # ---------- Construction --------------------------------------------
    @classmethod
    def random(cls, rng: Optional[np.random.Generator] = None) -> "Genome":
        rng = rng or np.random.default_rng()
        return cls(rng.random(GENE_COUNT, dtype=np.float32))

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "Genome":
        arr = np.zeros(GENE_COUNT, dtype=np.float32)
        for i, spec in enumerate(GENE_CATALOG):
            v = data.get(spec.name)
            arr[i] = clamp01(float(v)) if v is not None else float(np.random.random())
        return cls(arr)

    # ---------- Access --------------------------------------------------
    def normalized(self, name: str) -> float:
        return float(self.values[GENE_INDEX[name]])

    def real(self, name: str) -> float:
        idx = GENE_INDEX[name]
        lo, hi = GENE_RANGES[idx]
        return lo + (hi - lo) * float(self.values[idx])

    def set_normalized(self, name: str, value: float) -> None:
        self.values[GENE_INDEX[name]] = clamp01(value)

    # ---------- Comparison ----------------------------------------------
    def distance(self, other: "Genome") -> float:
        """Mean absolute distance in [0, 1]."""
        return float(np.mean(np.abs(self.values - other.values)))

    def compatibility(self, other: "Genome") -> float:
        """Is `other` close enough to mate with? Returns 1.0 if fully
        compatible, 0.0 if completely incompatible. Uses each parent's
        own `genetic_compatibility_range` (averaged) as the threshold."""
        window = 0.5 * (
            self.real("genetic_compatibility_range")
            + other.real("genetic_compatibility_range")
        )
        if window <= 0.0:
            return 0.0
        d = self.distance(other)
        if d >= window:
            return 0.0
        return float(1.0 - d / window)

    def signature(self) -> np.ndarray:
        """Per-individual species-signature vector. Right now it's just
        the raw gene values — the SpeciesRegistry averages signatures of
        members to derive the species centroid. Kept as a separate method
        so a future evolution can return a hashed or reduced fingerprint
        without changing call sites."""
        return self.values.copy()

    # ---------- Color / phenotype ---------------------------------------
    def to_color(self) -> "Color":
        # Local import avoids cyclic genetics<->rendering pull at import time.
        from rendering.colors import genome_to_color
        return genome_to_color(self)

    def derive_traits(self) -> Dict[str, float]:
        """Real-valued phenotype dict for all genes. Wrapper around
        `real()` that the inspector / experiment runner / save format can
        emit without knowing the gene names up front."""
        return {spec.name: self.real(spec.name) for spec in GENE_CATALOG}

    # ---------- Inheritance --------------------------------------------
    def inherit_from(
        self,
        other: "Genome",
        rng: np.random.Generator,
        is_hybrid: bool = False,
    ) -> Tuple["Genome", int]:
        """Spec-natural alias for `inheritance.crossover(self, other, rng)`.

        Returns `(child_genome, num_mutated_genes)`."""
        from .inheritance import crossover
        return crossover(self, other, rng, is_hybrid=is_hybrid)

    def mutate(
        self,
        rng: np.random.Generator,
        rate: Optional[float] = None,
        strength: Optional[float] = None,
    ) -> int:
        """In-place mutation. If `rate`/`strength` are None, uses this
        genome's own mutation_rate / mutation_strength genes."""
        from .mutation import mutate_inplace
        r = self.real("mutation_rate") if rate is None else rate
        s = self.real("mutation_strength") if strength is None else strength
        return mutate_inplace(self, rng, r, s,
                              stability=self.normalized("genetic_stability"))

    # ---------- Serialisation -------------------------------------------
    def to_dict(self) -> Dict[str, float]:
        return {spec.name: float(self.values[i]) for i, spec in enumerate(GENE_CATALOG)}

    def serialize(self) -> Dict[str, float]:
        """Alias for `to_dict` matching the spec name."""
        return self.to_dict()

    @classmethod
    def deserialize(cls, data: Dict[str, float]) -> "Genome":
        return cls.from_dict(data)

    def copy(self) -> "Genome":
        return Genome(self.values.copy())
