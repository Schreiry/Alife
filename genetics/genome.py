"""Genome: a numpy-backed array of normalized gene values.

The Genome is intentionally dumb — it stores values in [0, 1] and exposes
real-world conversions. Inheritance and mutation live in their own modules
so this class stays focused on representation.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from .genes import GENE_CATALOG, GENE_COUNT, GENE_INDEX, GENE_RANGES, clamp01


class Genome:
    __slots__ = ("values",)

    def __init__(self, values: np.ndarray):
        if values.shape != (GENE_COUNT,):
            raise ValueError(
                f"Genome must have {GENE_COUNT} values, got {values.shape}"
            )
        self.values = np.clip(values.astype(np.float32, copy=False), 0.0, 1.0)

    # ---------- Construction ------------------------------------------------
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

    # ---------- Access ------------------------------------------------------
    def normalized(self, name: str) -> float:
        return float(self.values[GENE_INDEX[name]])

    def real(self, name: str) -> float:
        idx = GENE_INDEX[name]
        lo, hi = GENE_RANGES[idx]
        return lo + (hi - lo) * float(self.values[idx])

    def set_normalized(self, name: str, value: float) -> None:
        self.values[GENE_INDEX[name]] = clamp01(value)

    # ---------- Comparison --------------------------------------------------
    def distance(self, other: "Genome") -> float:
        """Mean absolute distance between two genomes (0..1)."""
        return float(np.mean(np.abs(self.values - other.values)))

    # ---------- Serialisation ----------------------------------------------
    def to_dict(self) -> Dict[str, float]:
        return {spec.name: float(self.values[i]) for i, spec in enumerate(GENE_CATALOG)}

    def copy(self) -> "Genome":
        return Genome(self.values.copy())
