"""Species registry: groups creatures by genome similarity.

Species identity is measured on a *curated heritable subset* of the 170 genes
(`SPECIATION_GENES`), not the full vector. Over the full 170 uniform genes
every pair sits ~0.333 apart (curse of dimensionality), so the full-vector
distance can never produce meaningful clusters. The subset keeps only stable,
inheritable trait genes (body plan, metabolism, core behaviour, the dedicated
`species_signature` marker) and drops appearance/dormant noise, so a drifting
lineage can actually pull apart into a separable cluster.

New species do not arise by online clustering of newborns. Offspring inherit
their parent's species; a new species only appears via **cladogenesis** — when
a species' membership splits into two breeding clusters far enough apart (see
`detect_splits`). That is the only emergence path from a single ancestor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

import config

from .genes import GENE_INDEX
from .genome import Genome


# Heritable trait genes that define species identity. Curated: physical body
# plan + metabolism + core behaviour + the explicit species marker. Appearance
# (color_*) and dormant noise are deliberately excluded so they don't drown the
# signal. Order is irrelevant — only membership matters.
SPECIATION_GENES: Tuple[str, ...] = (
    "body_size", "movement_speed", "vision_range", "lifespan", "max_health",
    "metabolism_speed", "digestion_efficiency",
    "intelligence",
    "aggression", "territoriality", "hunting_instinct", "cooperation_instinct",
    "social_bonding",
    "attack_power", "defense_power",
    "fertility",
    "species_signature",
)
_SIG_IDX: np.ndarray = np.array([GENE_INDEX[n] for n in SPECIATION_GENES], dtype=np.intp)


def signature_subset(values: np.ndarray) -> np.ndarray:
    """Project a full 170-gene vector onto the speciation subset."""
    return values[_SIG_IDX]


def signature_distance(a_values: np.ndarray, b_values: np.ndarray) -> float:
    """Mean-abs distance between two full genome vectors, measured only over
    the speciation subset. In [0, 1]."""
    return float(np.mean(np.abs(a_values[_SIG_IDX] - b_values[_SIG_IDX])))


def make_founder_signature(rng: np.random.Generator) -> np.ndarray:
    """A random point in the speciation subspace (one founder lineage's
    identity). Independent draws sit ~0.33 apart — comfortably above the split
    threshold — so K founders are distinct species by construction."""
    return rng.random(len(SPECIATION_GENES)).astype(np.float32)


def write_signature(
    values: np.ndarray,
    subset_values: np.ndarray,
    rng: Optional[np.random.Generator] = None,
    noise: float = 0.0,
) -> None:
    """In place: stamp the speciation-subset genes of a full 170-gene vector
    with `subset_values` (+ optional uniform jitter), clipped to [0, 1]. Used
    to seed founder lineages; the non-signature genes keep their random draw."""
    v = subset_values.astype(np.float32, copy=True)
    if noise > 0.0 and rng is not None:
        v = v + rng.uniform(-noise, noise, size=v.shape).astype(np.float32)
    values[_SIG_IDX] = np.clip(v, 0.0, 1.0)


@dataclass
class Species:
    id: int
    name: str
    base_color: tuple
    founder_id: int
    created_tick: int
    signature: np.ndarray  # mean *full* genome values for fast distance check
    population_count: int = 0
    parent_species_id: Optional[int] = None  # set when born via cladogenesis


class SpeciesRegistry:
    def __init__(self, distance_threshold: float = 0.45):
        self.distance_threshold = distance_threshold
        self.species: Dict[int, Species] = {}
        self._next_id: int = 1

    def assign(
        self,
        genome: Genome,
        creature_id: int,
        tick: int,
        base_color: tuple,
    ) -> int:
        # Single-ancestor / pure-emergence rule: a parentless creature (world
        # seed or immigration reseed) always joins the *nearest* existing
        # species — it can never found a new one. The only speciation path is
        # cladogenesis (detect_splits). A new species is created here solely to
        # bootstrap the very first creature, when no species exists yet.
        if self.species:
            best = min(
                self.species.values(),
                key=lambda sp: signature_distance(genome.values, sp.signature),
            )
            best.population_count += 1
            return best.id

        sp = self._new_species(
            base_color=base_color,
            founder_id=creature_id,
            created_tick=tick,
            signature=genome.values.copy(),
            population_count=1,
        )
        return sp.id

    def register_member(self, species_id: int) -> None:
        """Bump a species' live count when an offspring inherits it directly
        (offspring don't go through `assign`)."""
        sp = self.species.get(species_id)
        if sp is not None:
            sp.population_count += 1

    def found_species(
        self,
        signature_values: np.ndarray,
        founder_id: int,
        tick: int,
        base_color: tuple,
    ) -> int:
        """Unconditionally create a new species (count starts at 0; members are
        added via `register_member` as they spawn with this species inherited).
        Used only to seed founder lineages at world start."""
        return self._new_species(
            base_color=base_color,
            founder_id=founder_id,
            created_tick=tick,
            signature=signature_values,
            population_count=0,
        ).id

    def _new_species(
        self,
        base_color: tuple,
        founder_id: int,
        created_tick: int,
        signature: np.ndarray,
        population_count: int,
        parent_species_id: Optional[int] = None,
    ) -> Species:
        new_id = self._next_id
        self._next_id += 1
        sp = Species(
            id=new_id,
            name=f"sp_{new_id:04d}",
            base_color=base_color,
            founder_id=founder_id,
            created_tick=created_tick,
            signature=np.asarray(signature, dtype=np.float32).copy(),
            population_count=population_count,
            parent_species_id=parent_species_id,
        )
        self.species[new_id] = sp
        return sp

    def detect_splits(
        self,
        members: Dict[int, Sequence[Tuple[int, np.ndarray, tuple]]],
        tick: int,
    ) -> List[Tuple[int, int, int]]:
        """Cladogenesis. `members` maps species_id -> sequence of
        (creature_id, full_genome_values, color) for its live members.

        For each species big enough to split, project member signatures onto
        their principal axis of variance, cut at the widest gap, and — if the
        two subgroups' centroids are far enough apart and both are viable —
        spin the *diverged* subgroup off as a new species.

        Returns a list of (creature_id, old_species_id, new_species_id)
        reassignments. Species objects and population counts are updated here;
        the caller applies the per-creature reassignments to its stores.
        """
        reassignments: List[Tuple[int, int, int]] = []
        min_pop = config.SPECIATION_MIN_SPLIT_POP
        for sp_id, rows in members.items():
            if len(self.species) >= config.MAX_SPECIES:
                break
            if len(rows) < 2 * min_pop:
                continue
            sp = self.species.get(sp_id)
            if sp is None:
                continue

            full = np.stack([r[1] for r in rows]).astype(np.float64)   # (n, 170)
            sig = full[:, _SIG_IDX]                                     # (n, m)
            centered = sig - sig.mean(axis=0, keepdims=True)
            # Principal axis = eigenvector of the largest eigenvalue of the
            # (m x m) covariance. m ~ 17 so this is trivially cheap.
            cov = centered.T @ centered
            _evals, evecs = np.linalg.eigh(cov)
            axis = evecs[:, -1]
            proj = centered @ axis
            order = np.argsort(proj)
            gaps = np.diff(proj[order])
            if gaps.size == 0:
                continue
            cut = int(np.argmax(gaps))           # split after position `cut`
            left_n = cut + 1
            right_n = len(rows) - left_n
            if left_n < min_pop or right_n < min_pop:
                continue

            left = order[: cut + 1]
            right = order[cut + 1:]
            c_left = sig[left].mean(axis=0)
            c_right = sig[right].mean(axis=0)
            if float(np.mean(np.abs(c_left - c_right))) < config.SPECIATION_SPLIT_THRESHOLD:
                continue

            # Split off whichever subgroup is farther from the whole-species
            # centroid (the diverged offshoot); the bulk keeps the old id.
            full_c = sig.mean(axis=0)
            d_left = float(np.mean(np.abs(c_left - full_c)))
            d_right = float(np.mean(np.abs(c_right - full_c)))
            move = left if d_left >= d_right else right
            keep = right if d_left >= d_right else left

            move_rows = [rows[i] for i in move]
            new_sig = full[move].mean(axis=0)
            founder_cid, _vals, founder_color = move_rows[0]
            new_sp = self._new_species(
                base_color=founder_color,
                founder_id=founder_cid,
                created_tick=tick,
                signature=new_sig,
                population_count=len(move_rows),
                parent_species_id=sp_id,
            )
            # Re-center the parent species on the members it kept.
            sp.signature = full[keep].mean(axis=0).astype(np.float32)
            sp.population_count = max(0, sp.population_count - len(move_rows))
            for cid, _v, _c in move_rows:
                reassignments.append((int(cid), sp_id, new_sp.id))

        return reassignments

    def remove_member(self, species_id: int) -> None:
        sp = self.species.get(species_id)
        if sp is None:
            return
        sp.population_count = max(0, sp.population_count - 1)

    def update_signatures(self, genomes_by_species: Dict[int, List[Genome]]) -> None:
        """Recompute species signatures by averaging current member genomes."""
        for sp_id, genomes in genomes_by_species.items():
            sp = self.species.get(sp_id)
            if sp is None or not genomes:
                continue
            stacked = np.stack([g.values for g in genomes])
            sp.signature = stacked.mean(axis=0).astype(np.float32)

    def alive_species(self) -> List[Species]:
        return [s for s in self.species.values() if s.population_count > 0]
