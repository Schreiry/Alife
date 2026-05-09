"""Food resource: simple positional energy source."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Food:
    id: int
    x: float
    y: float
    energy: float
