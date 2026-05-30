"""2D grid storing per-tile territory ownership and claim strength.

Beyond raw ownership the grid also tracks "maturation" state used purely by
the observation layer (border-type rendering + territory history): how long
the current owner has held a tile, how assimilated it is, recent contest
pressure, and the previous owner. These auxiliary fields never feed back into
creature behavior — they only enrich what the map can show.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

import config


# Cached disk stencils keyed by radius: (mask, falloff). The geometry never
# changes, so we build it once instead of recomputing arange/sqrt on every
# claim (claims run inside the hot per-creature brain loop).
_DISK_STENCILS: dict[int, tuple] = {}


def _disk_stencil(radius: int) -> tuple:
    s = _DISK_STENCILS.get(radius)
    if s is None:
        ax = np.arange(-radius, radius + 1, dtype=np.float32)
        d2 = ax[:, None] ** 2 + ax[None, :] ** 2
        mask = d2 <= float(radius * radius)
        fall = np.maximum(0.3, 1.0 - 0.7 * np.sqrt(d2) / float(radius)).astype(np.float32)
        fall *= mask  # 0 outside the disk
        s = (mask, fall)
        _DISK_STENCILS[radius] = s
    return s


class TerritoryGrid:
    """Stores owner_clan_id and claim_strength for each tile.

    -1 means unowned. claim_strength is in [0, 1].

    Auxiliary (view-only) per-tile state:
      last_owner       previous owner clan id (-1 if none) — territory history
      occupation_age   update-ticks the current owner has held the tile
      assimilation     [0,1] how settled the tile is under its owner
      conflict         [0,1] recent contest pressure (decays over time)
    """

    def __init__(self, width: int, height: int):
        self.width: int = width
        self.height: int = height
        self.owner: np.ndarray = np.full((width, height), -1, dtype=np.int32)
        self.strength: np.ndarray = np.zeros((width, height), dtype=np.float32)

        # --- view-only maturation state ---
        self.last_owner: np.ndarray = np.full((width, height), -1, dtype=np.int32)
        self.occupation_age: np.ndarray = np.zeros((width, height), dtype=np.int32)
        self.assimilation: np.ndarray = np.zeros((width, height), dtype=np.float32)
        self.conflict: np.ndarray = np.zeros((width, height), dtype=np.float32)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def reinforce(self, x: int, y: int, clan_id: int, amount: float) -> None:
        if not self.in_bounds(x, y):
            return
        current_owner = int(self.owner[x, y])
        current_strength = float(self.strength[x, y])
        if current_owner == clan_id:
            # Reinforcing already-held ground: just strengthen the claim.
            self.strength[x, y] = min(1.0, current_strength + amount)
        elif current_owner == -1:
            # Fresh claim on empty ground: a new occupation begins.
            self.owner[x, y] = clan_id
            self.strength[x, y] = min(1.0, current_strength + amount)
            self.occupation_age[x, y] = 0
            self.assimilation[x, y] = 0.0
        else:
            # Contested by a rival clan — register pressure either way.
            self._bump_conflict(x, y)
            new_strength = current_strength - amount
            if new_strength <= 0.0:
                # Capture: ownership flips; the tile is freshly occupied.
                self.last_owner[x, y] = current_owner
                self.owner[x, y] = clan_id
                self.strength[x, y] = min(1.0, -new_strength + amount * 0.5)
                self.occupation_age[x, y] = 0
                self.assimilation[x, y] = 0.0
            else:
                self.strength[x, y] = new_strength

    def _bump_conflict(self, x: int, y: int) -> None:
        self.conflict[x, y] = min(
            1.0, float(self.conflict[x, y]) + config.TERRITORY_CONFLICT_BUMP
        )

    def reinforce_area(self, cx: int, cy: int, clan_id: int, amount: float, radius: int) -> None:
        """Stamp a claim over a disk of `radius` tiles around (cx, cy).

        Same semantics as `reinforce` but applied to a neighborhood, with the
        claim falling off toward the edge. This is what makes a clan's holdings
        grow as connected regions (overlapping stamps from nearby members
        merge) instead of isolated single-tile dots. Vectorized over the small
        window, so it stays cheap even with many claimers per tick.
        """
        if radius <= 0:
            self.reinforce(cx, cy, clan_id, amount)
            return
        x0 = max(0, cx - radius); x1 = min(self.width, cx + radius + 1)
        y0 = max(0, cy - radius); y1 = min(self.height, cy + radius + 1)
        if x1 <= x0 or y1 <= y0:
            return

        ow = self.owner[x0:x1, y0:y1]
        st = self.strength[x0:x1, y0:y1]
        la = self.last_owner[x0:x1, y0:y1]
        ag = self.occupation_age[x0:x1, y0:y1]
        asm = self.assimilation[x0:x1, y0:y1]
        cf = self.conflict[x0:x1, y0:y1]

        # Slice the cached stencil to the (possibly border-clipped) window.
        mask_full, fall_full = _disk_stencil(radius)
        sx = x0 - (cx - radius)
        sy = y0 - (cy - radius)
        disk = mask_full[sx:sx + (x1 - x0), sy:sy + (y1 - y0)]
        if not disk.any():
            return
        fall = amount * fall_full[sx:sx + (x1 - x0), sy:sy + (y1 - y0)]

        friendly = disk & ((ow == clan_id) | (ow == -1))
        empty = disk & (ow == -1)
        hostile = disk & (ow >= 0) & (ow != clan_id)

        st[friendly] = np.minimum(1.0, st[friendly] + fall[friendly])
        if empty.any():
            ow[empty] = clan_id
            ag[empty] = 0
            asm[empty] = 0.0

        if hostile.any():
            # Fully vectorized contest/capture (no per-tile Python loop — that
            # loop was what doubled tick time once rival territories collided).
            cf[hostile] = np.minimum(1.0, cf[hostile] + config.TERRITORY_CONFLICT_BUMP)
            new_st = st - fall
            captured = hostile & (new_st <= 0.0)
            contest = hostile & ~captured
            st[contest] = np.maximum(0.0, new_st[contest])
            if captured.any():
                la[captured] = ow[captured]
                ow[captured] = clan_id
                st[captured] = np.minimum(1.0, fall[captured] * 0.5)
                ag[captured] = 0
                asm[captured] = 0.0

    def decay(self, decay_amount: float) -> None:
        if decay_amount <= 0.0:
            return
        # Operate only on tiles that actually have ownership. At large
        # world sizes most of the grid is untouched and a full-grid
        # numpy sweep dominates the tick budget.
        mask = self.owner != -1
        if not mask.any():
            return
        new_strength = self.strength[mask] - decay_amount
        cleared = new_strength <= 0.0
        new_strength[cleared] = 0.0
        self.strength[mask] = new_strength
        if cleared.any():
            owner_indices = np.flatnonzero(mask.ravel())
            cleared_indices = owner_indices[cleared]
            flat_owner = self.owner.ravel()
            flat_last = self.last_owner.ravel()
            flat_age = self.occupation_age.ravel()
            flat_assim = self.assimilation.ravel()
            # Remember who just lost the tile (history), then reset maturation.
            flat_last[cleared_indices] = flat_owner[cleared_indices]
            flat_owner[cleared_indices] = -1
            flat_age[cleared_indices] = 0
            flat_assim[cleared_indices] = 0.0

    def update_dynamics(self) -> None:
        """Advance maturation state one update tick. Vectorized and cheap;
        called from the simulation on TERRITORY_DECAY_INTERVAL. View-only."""
        owned = self.owner != -1
        # Contest pressure always relaxes toward zero.
        self.conflict *= config.TERRITORY_CONFLICT_DECAY
        self.conflict[self.conflict < 1e-3] = 0.0
        if not owned.any():
            return
        self.occupation_age[owned] += 1
        # Settled ground assimilates; active contest slows it down.
        rate = config.TERRITORY_ASSIMILATION_RATE
        gain = rate * (1.0 - self.conflict[owned])
        self.assimilation[owned] = np.minimum(1.0, self.assimilation[owned] + gain)

    def clan_owns(self, x: int, y: int) -> Optional[int]:
        if not self.in_bounds(x, y):
            return None
        owner = int(self.owner[x, y])
        return None if owner == -1 else owner

    def territory_count(self, clan_id: int) -> int:
        return int(np.count_nonzero(self.owner == clan_id))

    def territory_counts_by_clan(self) -> dict:
        """Return {clan_id: tile_count} via a single bincount pass."""
        flat = self.owner.ravel()
        if flat.size == 0:
            return {}
        # bincount needs non-negative ints; treat -1 as a separate bucket.
        valid_mask = flat >= 0
        if not valid_mask.any():
            return {}
        vals = flat[valid_mask]
        counts = np.bincount(vals)
        return {int(i): int(c) for i, c in enumerate(counts) if c > 0}
