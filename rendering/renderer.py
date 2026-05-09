"""Pygame renderer.

Two performance ideas matter most here:

  1. The territory layer is a 1-pixel-per-tile surface that is only
     re-drawn when `world.territory_dirty` is set. Most ticks just blit
     the cached surface (and do a single `pygame.transform.scale` per
     frame, which is cheap relative to filling 9 million tiles by hand).

  2. Food is drawn with a single `pygame.draw.circle` per item, but only
     for items that fall inside the viewport — at large world sizes most
     food and most creatures are off-screen and skipping them costs O(1)
     per skipped item.

The viewport is optional. If the world is small enough to fit, it
behaves identically to the original full-world view.
"""

from __future__ import annotations

import numpy as np
import pygame

import config
from rendering.camera import Camera
from ui.debug_overlay import DebugOverlay


# Cap the rendered world rect so we never try to scale a massive surface.
_MAX_VIEWPORT_PX = 1280


class Renderer:
    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.camera = Camera(tile_size=config.TILE_SIZE)
        self._world_rect = pygame.Rect(
            0, 0,
            min(_MAX_VIEWPORT_PX, config.WORLD_WIDTH * config.TILE_SIZE),
            min(_MAX_VIEWPORT_PX, config.WORLD_HEIGHT * config.TILE_SIZE),
        )
        self._panel_rect = pygame.Rect(
            self._world_rect.right, 0,
            config.UI_PANEL_WIDTH, config.WINDOW_HEIGHT,
        )
        # Visible portion of the world (in tile coordinates). The cached
        # territory surface is sized to this — never to the full world.
        self._visible_tiles_w = min(
            config.WORLD_WIDTH, self._world_rect.width // config.TILE_SIZE,
        )
        self._visible_tiles_h = min(
            config.WORLD_HEIGHT, self._world_rect.height // config.TILE_SIZE,
        )
        self._territory_surf = pygame.Surface(
            (self._visible_tiles_w, self._visible_tiles_h)
        )
        self._territory_cache_valid: bool = False
        # Bounded debounce: even if the world keeps marking dirty, we don't
        # rebuild on every frame. Keeps tail latency capped.
        self._territory_min_rebuild_interval: int = 30
        self._territory_last_rebuild_frame: int = -10_000
        self.debug = DebugOverlay(self._panel_rect)

        # Frame counter for debug-text throttling.
        self._frame_idx: int = 0

    def draw(self, simulation) -> None:
        prof = simulation.profiler
        prof.start_section("render")
        self.surface.fill(config.COLOR_BG)

        prof.start_section("render_territory")
        self._draw_territory(simulation.world)
        prof.end_section("render_territory")

        prof.start_section("render_food")
        self._draw_food(simulation.world)
        prof.end_section("render_food")

        prof.start_section("render_creatures")
        self._draw_creatures(simulation.world)
        prof.end_section("render_creatures")

        prof.start_section("render_overlay")
        self.debug.draw(self.surface, simulation, self._frame_idx)
        prof.end_section("render_overlay")

        self._frame_idx += 1
        prof.end_section("render")

    # ---------- layers ------------------------------------------------------
    def _draw_territory(self, world) -> None:
        # Debounced rebuild: only redraw when dirty AND enough frames have
        # passed since the last redraw. With WORLD=3000 the cost of a
        # rebuild is non-trivial; the visual difference between back-to-
        # back rebuilds is minor.
        frames_since = self._frame_idx - self._territory_last_rebuild_frame
        needs_rebuild = (
            not self._territory_cache_valid
            or (world.territory_dirty
                and frames_since >= self._territory_min_rebuild_interval)
        )
        if needs_rebuild:
            self._rebuild_territory_surface(world)
            world.territory_dirty = False
            self._territory_cache_valid = True
            self._territory_last_rebuild_frame = self._frame_idx

        scaled = pygame.transform.scale(self._territory_surf, self._world_rect.size)
        self.surface.blit(scaled, self._world_rect.topleft)

    def _rebuild_territory_surface(self, world) -> None:
        # Process only the visible sub-rect, not the full world. At
        # WORLD=3000 the off-screen 95% would be wasted work.
        vw, vh = self._visible_tiles_w, self._visible_tiles_h
        owners = world.territory.owner[:vw, :vh]
        strength = world.territory.strength[:vw, :vh]
        clans = world.clans

        if not clans:
            # No claimed territory anywhere — fill BG and return.
            rgb = np.empty((vw, vh, 3), dtype=np.uint8)
            rgb[..., 0] = config.COLOR_BG[0]
            rgb[..., 1] = config.COLOR_BG[1]
            rgb[..., 2] = config.COLOR_BG[2]
            pygame.surfarray.blit_array(self._territory_surf, rgb)
            return

        # Build a clan-color lookup table. Index 0 means unowned (-1 + 1);
        # all other slots are clan_id + 1. Clan ids are sequential, so the
        # table size is bounded by max active clan id + 2.
        max_id = max(clans.keys())
        lut = np.empty((max_id + 2, 3), dtype=np.uint8)
        lut[0] = config.COLOR_BG
        # Default unknown slots to BG (in case there are gaps in clan ids).
        lut[1:] = config.COLOR_BG
        for cid, clan in clans.items():
            lut[cid + 1] = clan.color

        # Single fancy-index pass over the visible region.
        idx = np.clip(owners + 1, 0, max_id + 1)
        clan_rgb = lut[idx]  # shape (vw, vh, 3), uint8

        # Strength-weighted blend with background. Vectorized in float, then
        # cast back to uint8.
        a = (strength * 0.55)[..., None].astype(np.float32)  # shape (vw, vh, 1)
        bg = np.array(config.COLOR_BG, dtype=np.float32)
        blended = bg * (1.0 - a) + clan_rgb.astype(np.float32) * a
        rgb = blended.astype(np.uint8)

        pygame.surfarray.blit_array(self._territory_surf, rgb)

    def _draw_food(self, world) -> None:
        ts = self.camera.tile_size
        ox, oy = self.camera.offset_x, self.camera.offset_y
        color = config.COLOR_FOOD
        f = world.food_store
        max_x = self._visible_tiles_w
        max_y = self._visible_tiles_h
        # Fast path: gather alive food coordinates as numpy arrays, mask
        # by viewport, then draw.
        alive_idx = np.flatnonzero(f.alive)
        if alive_idx.size == 0:
            return
        fx = f.x[alive_idx]
        fy = f.y[alive_idx]
        in_view = (fx >= 0) & (fx < max_x) & (fy >= 0) & (fy < max_y)
        if not in_view.any():
            return
        view_x = fx[in_view]
        view_y = fy[in_view]
        size = max(2, ts - 1)
        for x, y in zip(view_x, view_y):
            pygame.draw.rect(self.surface, color,
                             (int(x * ts) + ox, int(y * ts) + oy, size, size))

    def _draw_creatures(self, world) -> None:
        ts = self.camera.tile_size
        max_x = self._visible_tiles_w
        max_y = self._visible_tiles_h
        clans = world.clans
        for c in world.creatures.values():
            cx = c.x
            cy = c.y
            if cx < 0 or cx >= max_x or cy < 0 or cy >= max_y:
                continue
            sx, sy = self.camera.world_to_screen(cx, cy)
            radius = max(2, int(ts * 0.7))
            pygame.draw.circle(self.surface, c.color, (sx, sy), radius)
            clan_id = c.clan_id
            if clan_id is not None:
                clan = clans.get(clan_id)
                if clan is not None:
                    pygame.draw.circle(
                        self.surface, clan.color, (sx, sy), radius + 1, 1,
                    )
