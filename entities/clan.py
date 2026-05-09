"""Clan: a named group of creatures with relations to other clans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple


@dataclass
class Clan:
    id: int
    name: str
    leader_id: int
    color: Tuple[int, int, int]
    created_tick: int
    members: Set[int] = field(default_factory=set)
    relations: Dict[int, float] = field(default_factory=dict)  # other_clan_id -> -1..1
    aggression_level: float = 0.5
    ideology: float = 0.5  # 0 = peaceful, 1 = militant
    stability: float = 1.0
    territory_count: int = 0

    def add_member(self, creature_id: int) -> None:
        self.members.add(creature_id)

    def remove_member(self, creature_id: int) -> None:
        self.members.discard(creature_id)

    @property
    def alive(self) -> bool:
        return len(self.members) > 0
