"""Pluggable brain interface, per CLAUDE.md §8.

Three concrete implementations are envisioned:

  * BaselineScoreBrain  — handcrafted scoring rules. Stable, fast, always
                          available. Defined in behavior/brain.py.
  * HybridBrain         — baseline scoring + genome-derived bias on each
                          action score. Defined in behavior/brain.py.
  * EvolvableNeuralBrain — neural network whose weights are encoded in the
                          genome. Placeholder here; spec marks it future
                          work (§8, §6 evolvable brain genome).

The interface is intentionally narrow: each brain has to convert a
(creature, world) pair into a single action that it then executes. The
heavy work of perception and action handling can be shared between
implementations — see behavior/brain.py for the canonical action
dispatch table.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from entities.creature import Creature


class BrainInterface(ABC):
    """Per-simulation brain. Stateless w.r.t. individual creatures; any
    per-creature state lives on the creature or in the genome."""

    @abstractmethod
    def step(self, creature: Creature, world) -> None:
        """Pick and execute one action for `creature` this tick."""

    # ---- Optional methods kept abstract-by-convention so concrete brains
    # surface the spec API even if internal implementation overlaps. ----

    def perceive(self, creature: Creature, world):
        """Sensor pass. Default delegates to behavior.perception.perceive."""
        from .perception import perceive
        return perceive(creature, world)

    def decide(self, creature: Creature, perception, world):
        """Returns the chosen Action. Default = score_actions baseline."""
        raise NotImplementedError

    def produce_action(self, creature: Creature, perception, action, world) -> None:
        """Execute the chosen Action against the world."""
        raise NotImplementedError

    # ---- Persistence -------------------------------------------------
    def serialize(self) -> Dict[str, Any]:
        return {"kind": self.__class__.__name__}

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "BrainInterface":
        # Concrete brains may override. Default: re-instantiate without args.
        return cls()


def make_brain(kind: str, rng) -> BrainInterface:
    """Factory used by Simulation/SimRunner. Keeps the rest of the code
    agnostic of which brain implementation is active."""
    # Local import to avoid cyclic load (brain.py imports from this file).
    from .brain import BaselineScoreBrain, HybridBrain
    kind = (kind or "baseline").lower()
    if kind in ("baseline", "score", "default"):
        return BaselineScoreBrain(rng)
    if kind in ("hybrid",):
        return HybridBrain(rng)
    if kind in ("neural", "evolvable"):
        # Not implemented yet; fall back to baseline so the sim runs.
        return BaselineScoreBrain(rng)
    raise ValueError(f"unknown brain kind: {kind!r}")
