"""Camera: world-to-screen transform.

The minimum simulation just centers the world on the screen at TILE_SIZE
without panning, but the API leaves room for zoom/pan in the future.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Camera:
    tile_size: int
    offset_x: int = 0
    offset_y: int = 0

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        return (
            int(x * self.tile_size) + self.offset_x,
            int(y * self.tile_size) + self.offset_y,
        )
