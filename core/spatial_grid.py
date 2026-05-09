"""Numpy-backed spatial grid built via counting sort.

Designed to be rebuilt every tick from a positions array — far cheaper
than incremental updates once the population is large because:
  - rebuild is O(N) with three numpy passes (cell_id, sort, cumsum)
  - query returns a numpy array of indices, ready for vectorized math
  - no Python objects allocated per query

Usage:
    grid = SpatialGrid(width, height, cell_size)
    grid.rebuild(positions_x, positions_y, alive_mask)
    indices = grid.query_indices(x, y, radius)  # np.ndarray[int32]
"""

from __future__ import annotations

import numpy as np


class SpatialGrid:
    def __init__(self, width: int, height: int, cell_size: int):
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = cell_size
        self.cells_x = (width + cell_size - 1) // cell_size
        self.cells_y = (height + cell_size - 1) // cell_size
        self.n_cells = self.cells_x * self.cells_y
        self.sorted_indices = np.zeros(0, dtype=np.int32)
        self.cell_offsets = np.zeros(self.n_cells + 1, dtype=np.int64)
        self.last_query_count: int = 0

    def rebuild(
        self,
        x: np.ndarray,
        y: np.ndarray,
        alive: np.ndarray,
    ) -> None:
        """Rebuild the grid from raw position arrays.

        `x`, `y` are full-capacity arrays; `alive` is a bool mask of the
        same length. Only alive entries are indexed.
        """
        if alive.any():
            alive_idx = np.flatnonzero(alive).astype(np.int32, copy=False)
            cs = self.cell_size
            cx = np.clip(
                (x[alive_idx] / cs).astype(np.int32),
                0, self.cells_x - 1,
            )
            cy = np.clip(
                (y[alive_idx] / cs).astype(np.int32),
                0, self.cells_y - 1,
            )
            cell_id = cy * self.cells_x + cx

            order = np.argsort(cell_id, kind="stable")
            self.sorted_indices = alive_idx[order]
            sorted_cells = cell_id[order]

            counts = np.bincount(sorted_cells, minlength=self.n_cells)
            offsets = np.empty(self.n_cells + 1, dtype=np.int64)
            offsets[0] = 0
            np.cumsum(counts, out=offsets[1:])
            self.cell_offsets = offsets
        else:
            self.sorted_indices = np.zeros(0, dtype=np.int32)
            self.cell_offsets = np.zeros(self.n_cells + 1, dtype=np.int64)
        self.last_query_count = 0

    def query_indices(self, x: float, y: float, radius: float) -> np.ndarray:
        """Return indices of items in cells overlapping (x, y, radius).

        Caller is expected to do an exact-distance filter on the result;
        the grid is conservative.
        """
        cs = self.cell_size
        cx = int(x // cs)
        cy = int(y // cs)
        span = int(radius // cs) + 1

        x0 = max(0, cx - span)
        x1 = min(self.cells_x - 1, cx + span)
        y0 = max(0, cy - span)
        y1 = min(self.cells_y - 1, cy + span)

        if x1 < x0 or y1 < y0:
            return np.zeros(0, dtype=np.int32)

        # Concatenate per-row slices. Rows are contiguous in cell_id order
        # (cells in the same y-row sit next to each other in offsets), so a
        # single slice per y-row spans (x0..x1).
        offsets = self.cell_offsets
        sorted_indices = self.sorted_indices
        rows = []
        for yy in range(y0, y1 + 1):
            row_start = yy * self.cells_x + x0
            row_end = yy * self.cells_x + x1
            s = int(offsets[row_start])
            e = int(offsets[row_end + 1])
            if e > s:
                rows.append(sorted_indices[s:e])
        if not rows:
            return np.zeros(0, dtype=np.int32)
        result = rows[0] if len(rows) == 1 else np.concatenate(rows)
        self.last_query_count += int(result.size)
        return result

    def stats(self) -> dict:
        nonzero = int(np.count_nonzero(np.diff(self.cell_offsets)))
        max_bucket = int(np.diff(self.cell_offsets).max()) if self.n_cells else 0
        return {
            "total_buckets": self.n_cells,
            "occupied_buckets": nonzero,
            "max_bucket_size": max_bucket,
            "last_query_total_neighbors": self.last_query_count,
        }
